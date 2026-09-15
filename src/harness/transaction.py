"""Business transaction manager — Prepare / Commit / Abort with idempotency.

From the architecture doc (section 2.3): multi-step agent execution must have
business transactions + idempotency, so a half-completed agent run does not
leave dirty state. Heterogeneous resources (tools, DB, external APIs) can only
achieve *eventual* consistency, so we track a rollback stack for operations
that declare ``undo_supported``.

Key concepts:

- ``idempotency_key`` — a caller-supplied key so retries don't duplicate side effects.
- ``prepare`` — record intent before executing a step.
- ``commit`` — mark a step as durably applied.
- ``abort`` — roll back applied steps in reverse order (only ``undo_supported``).
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class TransactionError(Exception):
    """Raised on transaction consistency failures."""


@dataclass
class Operation:
    """A single undoable operation recorded in the rollback stack."""

    name: str
    args: dict = field(default_factory=dict)
    undo: Optional[Callable] = None
    undo_supported: bool = False


@dataclass
class TransactionResult:
    """Result of a transaction lifecycle operation."""

    transaction_id: str
    status: str  # prepared | committed | aborted
    applied: list[str] = field(default_factory=list)


class TransactionManager:
    """Manages business transactions for a single agent run.

    Args:
        transaction_id: Optional caller-supplied id (idempotency key).
    """

    def __init__(self, transaction_id: Optional[str] = None):
        self.transaction_id = transaction_id or str(uuid.uuid4())
        self._operations: list[Operation] = []
        self._status = "prepared"

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def prepare(self, name: str, args: Optional[dict] = None) -> Operation:
        """Record an operation before executing it.

        Args:
            name: Operation name (e.g. tool name).
            args: Operation arguments (for audit / undo).

        Returns:
            The recorded Operation.
        """
        op = Operation(name=name, args=args or {})
        self._operations.append(op)
        return op

    def commit(self) -> TransactionResult:
        """Mark the transaction as committed (all operations durably applied)."""
        self._status = "committed"
        return TransactionResult(
            transaction_id=self.transaction_id,
            status="committed",
            applied=[op.name for op in self._operations],
        )

    async def abort(self) -> TransactionResult:
        """Roll back applied operations in reverse order.

        Only operations with ``undo_supported=True`` and a valid ``undo``
        callable are rolled back. Operations without undo support are left as
        audit markers (eventual consistency / manual resolution).
        """
        rolled_back = []
        for op in reversed(self._operations):
            if op.undo_supported and op.undo is not None:
                try:
                    result = op.undo(**op.args)
                    if hasattr(result, "__await__"):
                        await result
                    rolled_back.append(op.name)
                except Exception as exc:  # noqa: BLE001 - log and continue
                    logger.error("Undo failed for '%s': %s", op.name, exc)

        self._status = "aborted"
        return TransactionResult(
            transaction_id=self.transaction_id,
            status="aborted",
            applied=rolled_back,
        )

    # ------------------------------------------------------------------
    # Idempotency
    # ------------------------------------------------------------------

    @property
    def idempotency_key(self) -> str:
        return self.transaction_id

    @property
    def status(self) -> str:
        return self._status

    @property
    def operation_count(self) -> int:
        return len(self._operations)
