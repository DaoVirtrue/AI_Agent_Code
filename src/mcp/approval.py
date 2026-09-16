"""Approval gate — 每次授权机制（高危操作需用户明确同意）.

Every sensitive MCP tool call (CLI, file write, OCR result dispatch, etc.)
must be approved by the user BEFORE execution. This module implements a
pending-approval registry: a tool call that requires approval is held until
the user approves or rejects it via the API.

Design (from the architecture doc):
- 高危/不可撤销操作每次都要授权，不能"信任一次就永久放行"。
- 用户拒绝 -> 工具返回拒绝错误，Agent 必须终止该动作。
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ApprovalDenied(Exception):
    """Raised when the user rejects an approval request."""


@dataclass
class ApprovalRequest:
    """A pending approval request for a tool call."""

    request_id: str
    tool_name: str
    arguments: dict
    reason: str
    created_at: float = field(default_factory=time.time)
    status: str = "pending"  # pending | approved | rejected | timeout
    decided_at: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "reason": self.reason,
            "status": self.status,
            "created_at": self.created_at,
        }


class ApprovalGate:
    """Registry of pending approval requests.

    A tool that requires approval registers a request here and blocks until
    the user approves/rejects it (via the API). Unapproved requests time out
    to a rejection by default (fail-closed).

    Args:
        timeout_seconds: Seconds before a pending request auto-rejects.
    """

    def __init__(self, timeout_seconds: float = 300.0):
        self.timeout_seconds = timeout_seconds
        self._pending: dict[str, ApprovalRequest] = {}
        self._history: list[ApprovalRequest] = []

    def request(self, tool_name: str, arguments: dict, reason: str = "") -> ApprovalRequest:
        """Create a pending approval request (blocks the caller)."""
        request_id = str(uuid.uuid4())[:8]
        req = ApprovalRequest(
            request_id=request_id,
            tool_name=tool_name,
            arguments=arguments,
            reason=reason or f"工具 '{tool_name}' 需要授权执行",
        )
        self._pending[request_id] = req
        logger.info("Approval requested: %s (%s)", tool_name, request_id)
        return req

    async def wait_for_decision(self, request_id: str) -> bool:
        """Block until the user decides (approve=True / reject=False).

        Polls the pending registry. On timeout, rejects (fail-closed).
        """
        import asyncio

        deadline = time.time() + self.timeout_seconds
        while time.time() < deadline:
            req = self._pending.get(request_id)
            if req is None:
                # Already resolved and moved to history
                for h in self._history:
                    if h.request_id == request_id:
                        return h.status == "approved"
                return False
            if req.status == "approved":
                return True
            if req.status == "rejected":
                return False
            await asyncio.sleep(0.2)

        # Timeout -> reject
        req = self._pending.pop(request_id, None)
        if req:
            req.status = "timeout"
            req.decided_at = time.time()
            self._history.append(req)
        return False

    def approve(self, request_id: str) -> bool:
        """Approve a pending request."""
        req = self._pending.pop(request_id, None)
        if req is None:
            return False
        req.status = "approved"
        req.decided_at = time.time()
        self._history.append(req)
        logger.info("Approval granted: %s", request_id)
        return True

    def reject(self, request_id: str) -> bool:
        """Reject a pending request."""
        req = self._pending.pop(request_id, None)
        if req is None:
            return False
        req.status = "rejected"
        req.decided_at = time.time()
        self._history.append(req)
        logger.info("Approval rejected: %s", request_id)
        return True

    def list_pending(self) -> list[dict]:
        """List all currently pending requests."""
        return [r.to_dict() for r in self._pending.values()]

    def list_history(self, limit: int = 50) -> list[dict]:
        """List recent approval history."""
        return [r.to_dict() for r in self._history[-limit:]]

    def stats(self) -> dict:
        return {
            "pending": len(self._pending),
            "approved": sum(1 for r in self._history if r.status == "approved"),
            "rejected": sum(1 for r in self._history if r.status == "rejected"),
            "timeout": sum(1 for r in self._history if r.status == "timeout"),
        }
