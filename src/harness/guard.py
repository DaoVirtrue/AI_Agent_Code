"""Harness guardrails — 用工程确定性驾驭模型不确定性。

Aggregates the agent safety guardrails into a single enforcement point:

- 最大迭代 / 循环保护（复用 ``agents.safety.SafetyGuard``）
- Token 成本上限（预算熔断，防刷爆账单）
- 高危工具拦截（写操作 / 不可 undo 操作需审批）
- 输出校验钩子（独立校验器，禁止 LLM 自判）

The guard is *orchestrational*: it wraps an agent loop and raises a
``HarnessViolation`` when a hard limit is hit, so the caller can stop
execution cleanly instead of letting the agent run away.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

# Deferred import to break the harness <-> agents import cycle:
# agents.pev imports harness.guard; harness.guard uses agents.safety.
# Importing safety lazily inside __init__ avoids a partially-initialized module.
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.agents.safety import SafetyGuard, SafetyCheck

logger = logging.getLogger(__name__)


class HarnessViolation(Exception):
    """Raised when a Harness hard limit is breached."""

    def __init__(self, reason: str, details: Optional[dict] = None):
        super().__init__(reason)
        self.reason = reason
        self.details = details or {}


@dataclass
class HarnessConfig:
    """Configuration for the Harness guard.

    Attributes:
        max_steps: Hard limit on agent reasoning steps.
        loop_threshold: Consecutive identical actions before loop detection.
        max_cost_usd: Hard budget on estimated cost (0 = unlimited).
        max_tokens: Hard budget on cumulative tokens (0 = unlimited).
        blocked_tools: Tool names that are always rejected.
        require_approval_for: Tool names that require human approval.
        output_validator: Optional callable(answer: str) -> (bool, reason).
    """

    max_steps: int = 25
    loop_threshold: int = 3
    max_cost_usd: float = 0.0
    max_tokens: int = 0
    blocked_tools: list[str] = field(default_factory=list)
    require_approval_for: list[str] = field(default_factory=list)
    output_validator: Optional[Callable[[str], tuple[bool, str]]] = None


class Harness:
    """Enforcement wrapper around an agent loop.

    Usage::

        harness = Harness(HarnessConfig(max_cost_usd=0.5))
        async for event in harness.run(agent, task):
            ...
    """

    def __init__(self, config: Optional[HarnessConfig] = None):
        from src.agents.safety import SafetyGuard

        self.config = config or HarnessConfig()
        self.safety = SafetyGuard(
            max_steps=self.config.max_steps,
            loop_threshold=self.config.loop_threshold,
            blocked_tools=self.config.blocked_tools,
        )
        self._cumulative_tokens = 0
        self._cumulative_cost = 0.0
        self._step_count = 0

    # ------------------------------------------------------------------
    # Enforcement checks
    # ------------------------------------------------------------------

    def check_step(self, step_count: int) -> "SafetyCheck":
        """Check the step count against the max-steps limit."""
        self._step_count = step_count
        return self.safety.check_steps(step_count)

    def check_loop(self, action_history: list) -> "SafetyCheck":
        """Check for an action loop."""
        return self.safety.detect_loop(action_history)

    def check_tool(self, tool_name: str, **kwargs) -> "SafetyCheck":
        """Check whether a tool is permitted to execute."""
        from src.agents.safety import SafetyCheck

        if tool_name in self.config.require_approval_for:
            return SafetyCheck(
                passed=False,
                reason=f"Tool '{tool_name}' requires human approval",
                details={"tool": tool_name, "requires_approval": True},
            )
        return self.safety.check_tool_permission(tool_name)

    def track_tokens(self, input_tokens: int = 0, output_tokens: int = 0) -> None:
        """Accumulate token usage and enforce the token budget."""
        self._cumulative_tokens += input_tokens + output_tokens
        self.safety.track_tokens(input_tokens, output_tokens)

        if self.config.max_tokens > 0 and self._cumulative_tokens > self.config.max_tokens:
            raise HarnessViolation(
                "Token budget exceeded",
                {"used": self._cumulative_tokens, "limit": self.config.max_tokens},
            )

    def track_cost(self, cost_usd: float) -> None:
        """Accumulate cost and enforce the cost budget."""
        self._cumulative_cost += cost_usd
        if self.config.max_cost_usd > 0 and self._cumulative_cost > self.config.max_cost_usd:
            raise HarnessViolation(
                "Cost budget exceeded",
                {"used": round(self._cumulative_cost, 6), "limit": self.config.max_cost_usd},
            )

    def validate_output(self, answer: str) -> tuple[bool, str]:
        """Run the independent output validator (if configured).

        This is the "Verify" gate — deliberately NOT an LLM self-assessment.
        The validator is an injected deterministic callable (e.g. schema check,
        safety classifier, or a separate evaluation service).
        """
        if self.config.output_validator is None:
            return True, "no validator configured"
        return self.config.output_validator(answer)

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def cumulative_tokens(self) -> int:
        return self._cumulative_tokens

    @property
    def cumulative_cost(self) -> float:
        return self._cumulative_cost

    @property
    def violations(self) -> list[dict]:
        return self.safety.get_violations()

    def reset(self) -> None:
        """Reset runtime counters for reuse."""
        self._cumulative_tokens = 0
        self._cumulative_cost = 0.0
        self._step_count = 0
        self.safety.reset()
