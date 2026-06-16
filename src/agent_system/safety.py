"""
Safety guardrails for the agent system.

Provides:
- Step limit enforcement
- Loop detection
- Content filtering
- Tool permission checking
- Resource usage monitoring
"""

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class SafetyCheck:
    """Result of a safety check."""
    passed: bool
    reason: str = ""
    details: dict = field(default_factory=dict)


class SafetyGuard:
    """Safety guardrails to prevent runaway or harmful agent behavior.

    Args:
        max_steps: Maximum number of agent actions per run (default 15).
        loop_threshold: Consecutive identical actions before loop detection (default 3).
        content_filter: Optional callable(text) -> (is_safe: bool, filtered_text: str).
        resource_limits: Dict of resource limits (e.g., {"max_tokens": 100000}).
        blocked_tools: List of tool names that are always blocked.
    """

    def __init__(
        self,
        max_steps: int = 15,
        loop_threshold: int = 3,
        content_filter: Callable | None = None,
        resource_limits: dict | None = None,
        blocked_tools: list[str] | None = None,
    ):
        self.max_steps = max_steps
        self.loop_threshold = loop_threshold
        self._content_filter = content_filter
        self._resource_limits = resource_limits or {}
        self._blocked_tools = set(blocked_tools or [])

        # Runtime state
        self._action_history: list[dict] = []
        self._steps_executed = 0
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._start_time = 0.0
        self._violations: list[dict] = []

    # ------------------------------------------------------------------
    # Step limits
    # ------------------------------------------------------------------

    def check_steps(self, current_step: int) -> SafetyCheck:
        """Check if the agent has exceeded the maximum steps.

        Args:
            current_step: The current step count.

        Returns:
            SafetyCheck with passed flag and reason.
        """
        if current_step > self.max_steps:
            self._record_violation("max_steps", f"Exceeded max steps: {current_step}/{self.max_steps}")
            return SafetyCheck(
                passed=False,
                reason=f"Maximum steps ({self.max_steps}) exceeded.",
                details={"current_step": current_step, "max_steps": self.max_steps},
            )
        return SafetyCheck(passed=True)

    # ------------------------------------------------------------------
    # Loop detection
    # ------------------------------------------------------------------

    def detect_loop(self, action_history: list) -> SafetyCheck:
        """Detect if the agent is stuck in an action loop.

        Checks for consecutive identical actions exceeding the threshold.
        Also detects alternating patterns (A, B, A, B, ...).

        Args:
            action_history: List of recent action names or descriptions.

        Returns:
            SafetyCheck with loop detection result.
        """
        self._action_history = [
            {"action": a, "timestamp": time.time()}
            for a in action_history[-50:]  # Keep last 50
        ]

        if len(action_history) < self.loop_threshold:
            return SafetyCheck(passed=True)

        recent = action_history[-self.loop_threshold:]
        unique_actions = set(str(a)[:50] for a in recent)  # Truncate for comparison

        # All recent actions are identical
        if len(unique_actions) == 1:
            self._record_violation("loop_detected", f"Loop: {list(unique_actions)[0]}")
            return SafetyCheck(
                passed=False,
                reason=f"Agent is stuck in a loop: {list(unique_actions)[0]}.",
                details={"repeated_action": list(unique_actions)[0], "count": self.loop_threshold},
            )

        # Alternating pattern (A, B, A, B)
        if len(action_history) >= self.loop_threshold * 2:
            pattern = [str(a)[:50] for a in action_history[-self.loop_threshold * 2:]]
            half = self.loop_threshold
            if pattern[:half] == pattern[half:]:
                self._record_violation("loop_detected", f"Alternating loop pattern: {pattern[:half]}")
                return SafetyCheck(
                    passed=False,
                    reason=f"Agent is stuck in an alternating loop: {pattern[:half]}.",
                    details={"pattern": pattern[:half]},
                )

        return SafetyCheck(passed=True)

    # ------------------------------------------------------------------
    # Content filtering
    # ------------------------------------------------------------------

    async def filter_content(self, text: str) -> tuple[bool, str]:
        """Filter content for safety and policy violations.

        Args:
            text: The text content to check.

        Returns:
            Tuple of (is_safe: bool, filtered_or_original_text: str).
        """
        if self._content_filter:
            try:
                result = self._content_filter(text)
                if asyncio and hasattr(result, "__await__"):
                    is_safe, filtered = await result
                elif isinstance(result, tuple):
                    is_safe, filtered = result
                else:
                    is_safe, filtered = bool(result), text
            except Exception as e:
                logger.warning("Content filter failed: %s", e)
                return True, text

            if not is_safe:
                self._record_violation("content_filter", f"Unsafe content blocked")
                return False, filtered

        # Built-in basic checks
        unsafe_patterns = [
            # Personal information patterns (basic)
            (r'\b(?:\d{3}-\d{2}-\d{4})\b', 'SSN-like'),
            (r'\b(?:\d{4}[- ]\d{4}[- ]\d{4}[- ]\d{4})\b', 'credit_card-like'),
        ]

        for pattern, label in unsafe_patterns:
            if re.search(pattern, text):
                self._record_violation("content_filter", f"Detected {label}")
                filtered_text = re.sub(pattern, f'[REDACTED:{label}]', text)
                return False, filtered_text

        return True, text

    # ------------------------------------------------------------------
    # Tool permission checking
    # ------------------------------------------------------------------

    def check_tool_permission(self, tool_name: str, user_role: str = "agent") -> SafetyCheck:
        """Check if a tool is permitted for execution.

        Args:
            tool_name: The name of the tool.
            user_role: The role of the calling user/agent.

        Returns:
            SafetyCheck with permission result.
        """
        if tool_name in self._blocked_tools:
            self._record_violation("blocked_tool", f"Blocked tool: {tool_name}")
            return SafetyCheck(
                passed=False,
                reason=f"Tool '{tool_name}' is permanently blocked.",
                details={"tool": tool_name, "role": user_role},
            )

        # Check resource limits
        if tool_name == "web_fetch" or tool_name == "file_operations":
            max_calls = self._resource_limits.get("max_file_ops", 50)
            file_ops = sum(1 for a in self._action_history if a["action"] in ("web_fetch", "file_operations"))
            if file_ops >= max_calls:
                return SafetyCheck(
                    passed=False,
                    reason=f"Maximum file/web operations ({max_calls}) reached.",
                    details={"current": file_ops, "max": max_calls},
                )

        if tool_name == "web_search":
            max_calls = self._resource_limits.get("max_search_calls", 20)
            search_ops = sum(1 for a in self._action_history if a["action"] == "web_search")
            if search_ops >= max_calls:
                return SafetyCheck(
                    passed=False,
                    reason=f"Maximum search operations ({max_calls}) reached.",
                    details={"current": search_ops, "max": max_calls},
                )

        return SafetyCheck(passed=True)

    # ------------------------------------------------------------------
    # Resource tracking
    # ------------------------------------------------------------------

    def track_tokens(self, input_tokens: int = 0, output_tokens: int = 0) -> None:
        """Track token usage for resource limits.

        Args:
            input_tokens: Number of input tokens used.
            output_tokens: Number of output tokens used.
        """
        self._total_input_tokens += input_tokens
        self._total_output_tokens += output_tokens

        max_tokens = self._resource_limits.get("max_tokens")
        if max_tokens and self._total_input_tokens + self._total_output_tokens > max_tokens:
            self._record_violation(
                "token_limit",
                f"Token budget exceeded: {self._total_input_tokens + self._total_output_tokens}/{max_tokens}",
            )

    def check_resources(self) -> SafetyCheck:
        """Check if any resource limits have been exceeded.

        Returns:
            SafetyCheck with resource status.
        """
        # Token budget
        max_tokens = self._resource_limits.get("max_tokens")
        if max_tokens:
            total = self._total_input_tokens + self._total_output_tokens
            if total > max_tokens:
                return SafetyCheck(
                    passed=False,
                    reason=f"Token budget exceeded ({total}/{max_tokens}).",
                    details={"used": total, "limit": max_tokens},
                )

        # Time budget
        max_time = self._resource_limits.get("max_time_seconds")
        if max_time and self._start_time > 0:
            elapsed = time.time() - self._start_time
            if elapsed > max_time:
                return SafetyCheck(
                    passed=False,
                    reason=f"Time budget exceeded ({elapsed:.1f}s/{max_time}s).",
                    details={"elapsed": elapsed, "limit": max_time},
                )

        return SafetyCheck(passed=True)

    # ------------------------------------------------------------------
    # Violation tracking
    # ------------------------------------------------------------------

    def _record_violation(self, violation_type: str, description: str) -> None:
        """Record a safety violation."""
        self._violations.append({
            "type": violation_type,
            "description": description,
            "timestamp": time.time(),
        })
        logger.warning("SAFETY VIOLATION: [%s] %s", violation_type, description)

    def get_violations(self) -> list[dict]:
        """Get all recorded safety violations."""
        return self._violations

    def reset(self) -> None:
        """Reset all runtime counters and history."""
        self._action_history.clear()
        self._steps_executed = 0
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._start_time = 0.0
        self._violations.clear()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def has_violations(self) -> bool:
        """Whether any safety violations have occurred."""
        return len(self._violations) > 0

    @property
    def token_usage(self) -> dict:
        """Return current token usage stats."""
        return {
            "input_tokens": self._total_input_tokens,
            "output_tokens": self._total_output_tokens,
            "total_tokens": self._total_input_tokens + self._total_output_tokens,
            "limit": self._resource_limits.get("max_tokens"),
        }

    def __repr__(self) -> str:
        return (
            f"SafetyGuard(max_steps={self.max_steps}, "
            f"violations={len(self._violations)}, "
            f"tokens={self._total_input_tokens + self._total_output_tokens})"
        )
