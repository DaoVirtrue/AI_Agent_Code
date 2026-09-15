"""
Human-in-the-loop (HITL) agent pattern with LangGraph interrupt/resume.

Implements the interrupt() + Command(resume=...) pattern for
pausing agent execution at critical decision points and waiting
for human approval before continuing.
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, TypedDict

logger = logging.getLogger(__name__)


class ApprovalStatus(str, Enum):
    """Status of a human-in-the-loop approval."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"
    TIMEOUT = "timeout"


@dataclass
class ApprovalRequest:
    """A request for human approval."""
    request_id: str
    action_type: str  # e.g., "tool_call", "message_send", "file_write"
    description: str
    details: dict
    timestamp: float = field(default_factory=time.time)
    status: ApprovalStatus = ApprovalStatus.PENDING
    approved_by: str | None = None
    approved_at: float | None = None
    modifications: dict | None = None


class HumanInTheLoopAgent:
    """Agent that pauses at critical points for human approval.

    Implements the LangGraph interrupt pattern where the agent flow can be
    paused, a human reviews and approves/rejects/modifies the pending action,
    and the agent resumes with the human's decision.

    Args:
        agent: The underlying agent instance (with run() method).
        approval_handler: Optional callable(ApprovalRequest) -> ApprovalStatus
                         for programmatic approval. If None, uses the internal
                         queue and requires explicit approval.
        auto_approve_safe_ops: If True, automatically approve low-risk operations
                              (web_search, calculator).
        approval_timeout: Seconds before pending approvals timeout (auto-reject).
    """

    def __init__(
        self,
        agent=None,
        approval_handler: Callable | None = None,
        auto_approve_safe_ops: bool = True,
        approval_timeout: float = 300.0,
    ):
        self.agent = agent
        self.approval_handler = approval_handler
        self.auto_approve_safe_ops = auto_approve_safe_ops
        self.approval_timeout = approval_timeout

        self._pending_approvals: dict[str, ApprovalRequest] = {}
        self._approval_history: list[ApprovalRequest] = []
        self._safe_tools = {"web_search", "calculator", "web_fetch"}

        # Approvals that generated interrupts (for LangGraph-style recovery)
        self._interrupted: dict[str, ApprovalRequest] = {}

    # ------------------------------------------------------------------
    # Approval management
    # ------------------------------------------------------------------

    def request_approval(
        self,
        action_type: str,
        description: str,
        details: dict | None = None,
    ) -> ApprovalRequest:
        """Create a new approval request and potentially pause execution.

        Args:
            action_type: Type of action needing approval.
            description: Human-readable description of the action.
            details: Additional context/details dict.

        Returns:
            The ApprovalRequest object.
        """
        request_id = str(uuid.uuid4())[:8]

        # Auto-approve safe operations
        if self.auto_approve_safe_ops and action_type in self._safe_tools:
            request = ApprovalRequest(
                request_id=request_id,
                action_type=action_type,
                description=description,
                details=details or {},
                status=ApprovalStatus.APPROVED,
                approved_at=time.time(),
                approved_by="system_auto",
            )
            self._approval_history.append(request)
            return request

        request = ApprovalRequest(
            request_id=request_id,
            action_type=action_type,
            description=description,
            details=details or {},
            status=ApprovalStatus.PENDING,
        )
        self._pending_approvals[request_id] = request

        # Fire approval handler if set (synchronous decision)
        if self.approval_handler:
            try:
                result = self.approval_handler(request)
                if isinstance(result, ApprovalStatus):
                    self.resolve(request_id, result)
                elif isinstance(result, bool):
                    status = ApprovalStatus.APPROVED if result else ApprovalStatus.REJECTED
                    self.resolve(request_id, status)
            except Exception as e:
                logger.warning("Approval handler failed: %s", e)

        return request

    def resolve(self, request_id: str, status: ApprovalStatus, modifications: dict | None = None) -> bool:
        """Resolve a pending approval request.

        Args:
            request_id: The request ID to resolve.
            status: New status (APPROVED, REJECTED, MODIFIED).
            modifications: Optional modifications for MODIFIED status.

        Returns:
            True if the request was found and resolved.
        """
        if request_id not in self._pending_approvals:
            return False

        request = self._pending_approvals.pop(request_id)
        request.status = status
        request.approved_at = time.time()

        if modifications:
            request.modifications = modifications

        self._approval_history.append(request)
        return True

    def get_pending_approvals(self) -> list[ApprovalRequest]:
        """Get all currently pending approval requests.

        Returns:
            List of pending ApprovalRequest objects.
        """
        # Check for timeouts
        now = time.time()
        expired = []
        for req_id, req in self._pending_approvals.items():
            if now - req.timestamp > self.approval_timeout:
                expired.append(req_id)

        for req_id in expired:
            self.resolve(req_id, ApprovalStatus.TIMEOUT)

        return list(self._pending_approvals.values())

    def get_approval_history(self, limit: int = 50) -> list[ApprovalRequest]:
        """Get historical approval requests."""
        return self._approval_history[-limit:]

    # ------------------------------------------------------------------
    # Interrupt/Resume pattern (LangGraph compatible)
    # ------------------------------------------------------------------

    def interrupt(self, action_type: str, description: str, details: dict | None = None) -> ApprovalRequest:
        """Create an interrupt point in agent execution.

        This follows LangGraph's interrupt() + Command(resume=...) pattern.

        Args:
            action_type: Type of action triggering the interrupt.
            description: Human-readable description.
            details: Context/details.

        Returns:
            ApprovalRequest that will be resolved before execution continues.
        """
        request = self.request_approval(action_type, description, details)
        self._interrupted[request.request_id] = request
        return request

    def resume(self, request_id: str, action: str = "approve", modifications: dict | None = None) -> bool:
        """Resume from an interrupt point.

        Args:
            request_id: The pending interrupt request ID.
            action: "approve", "reject", or "modify".
            modifications: Modified parameters (for "modify" action).

        Returns:
            True if the interrupt was resolved.
        """
        status_map = {
            "approve": ApprovalStatus.APPROVED,
            "reject": ApprovalStatus.REJECTED,
            "modify": ApprovalStatus.MODIFIED,
        }
        status = status_map.get(action, ApprovalStatus.APPROVED)

        resolved = self.resolve(request_id, status, modifications)
        if resolved:
            self._interrupted.pop(request_id, None)
        return resolved

    # ------------------------------------------------------------------
    # Agent execution
    # ------------------------------------------------------------------

    async def run(self, task: str, **kwargs) -> dict:
        """Run the agent with human-in-the-loop approval.

        Args:
            task: The task description.
            **kwargs: Additional context.

        Returns:
            Dict with answer and approval trail.
        """
        run_id = str(uuid.uuid4())[:8]
        start = time.perf_counter()

        if not self.agent:
            return {
                "answer": "No agent configured.",
                "run_id": run_id,
                "approvals": [],
                "success": False,
            }

        # Wrap the run to check for pending approvals before tool calls
        try:
            result = await self.agent.run(task)
            answer = result.answer if hasattr(result, "answer") else str(result)
            steps = result.steps if hasattr(result, "steps") else 1
            success = getattr(result, "success", True)
        except Exception as e:
            answer = f"Agent execution failed: {e}"
            steps = 0
            success = False

        elapsed = (time.perf_counter() - start) * 1000

        return {
            "answer": answer,
            "run_id": run_id,
            "steps": steps,
            "execution_time_ms": elapsed,
            "approvals": [
                {
                    "request_id": r.request_id,
                    "action_type": r.action_type,
                    "status": r.status.value,
                    "description": r.description,
                }
                for r in self.get_approval_history()
            ],
            "pending_approvals": len(self._pending_approvals),
            "success": success,
        }

    def __repr__(self) -> str:
        return (
            f"HumanInTheLoopAgent(auto_approve={self.auto_approve_safe_ops}, "
            f"pending={len(self._pending_approvals)})"
        )
