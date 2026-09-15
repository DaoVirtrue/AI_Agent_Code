"""Checkpoint recovery + consistency validation（文档第 11.3 节）.

Recovery from a checkpoint must be preceded by a consistency check: context,
idempotency records, locks, transaction state, sandbox and cost accounting
must all be validated before resuming, so a resume never duplicates side
effects or resumes from a half-committed state.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class ConsistencyReport:
    """Result of a recovery consistency check."""

    ok: bool
    issues: list[str] = field(default_factory=list)


@dataclass
class RecoveryResult:
    """Result of a recovery attempt."""

    recovered: bool
    checkpoint_id: str
    report: ConsistencyReport = field(default_factory=lambda: ConsistencyReport(ok=True))


class RecoveryManager:
    """Resumes a run from a checkpoint after validating consistency.

    The consistency checks are pluggable callables returning ``(ok: bool, issue: str)``.
    All must pass for recovery to proceed; otherwise the caller should degrade
    to a fresh run or a manual resolution.
    """

    def __init__(self, checks: Optional[list[Callable[[dict], tuple[bool, str]]]] = None):
        self.checks = checks or []

    def validate(self, checkpoint: dict) -> ConsistencyReport:
        """Run all consistency checks against a checkpoint snapshot."""
        issues = []
        for check in self.checks:
            ok, issue = check(checkpoint)
            if not ok:
                issues.append(issue)
        return ConsistencyReport(ok=len(issues) == 0, issues=issues)

    async def recover(
        self,
        checkpoint: dict,
        resume_fn: Optional[Callable[[dict], Any]] = None,
    ) -> RecoveryResult:
        """Validate the checkpoint, then resume via ``resume_fn`` if consistent.

        Args:
            checkpoint: The snapshot dict to resume from.
            resume_fn: Callable that performs the actual resume.

        Returns:
            RecoveryResult with the outcome.
        """
        report = self.validate(checkpoint)
        if not report.ok:
            logger.warning("Recovery consistency check failed: %s", report.issues)
            return RecoveryResult(
                recovered=False,
                checkpoint_id=checkpoint.get("checkpoint_id", ""),
                report=report,
            )

        if resume_fn is not None:
            result = resume_fn(checkpoint)
            if hasattr(result, "__await__"):
                await result

        return RecoveryResult(
            recovered=True,
            checkpoint_id=checkpoint.get("checkpoint_id", ""),
            report=report,
        )


# ---------------------------------------------------------------------------
# Built-in consistency checks
# ---------------------------------------------------------------------------


def check_context_present(checkpoint: dict) -> tuple[bool, str]:
    """Check that the checkpoint has a non-empty context/state."""
    state = checkpoint.get("state", checkpoint)
    if state is None or state == {}:
        return False, "checkpoint has no state"
    return True, ""


def check_idempotency_complete(checkpoint: dict) -> tuple[bool, str]:
    """Check that idempotency records are present for completed tool calls."""
    tool_calls = checkpoint.get("tool_calls", [])
    for call in tool_calls:
        if not call.get("idempotency_key"):
            return False, "tool call missing idempotency_key"
    return True, ""


def check_cost_not_negative(checkpoint: dict) -> tuple[bool, str]:
    """Check that accumulated cost is non-negative."""
    cost = checkpoint.get("cost_usd", 0.0)
    if cost < 0:
        return False, "negative accumulated cost"
    return True, ""
