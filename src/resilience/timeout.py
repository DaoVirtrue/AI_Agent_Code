"""Layered timeout configuration — 分层超时表（文档第 11.1 节）。

Each layer has an explicit timeout, with the invariant that **inner layers are
shorter than outer layers** (so an outer timeout never fires before the inner
layer has had a chance to complete). The default values follow the architecture
doc's recommended table.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

#: Recommended defaults (seconds), from the architecture doc section 11.1.
DEFAULT_TIMEOUTS: dict[str, float] = {
    "mcp_connect": 0.5,
    "mcp_read": 3.0,
    "mcp_total": 5.0,
    "tool_read": 3.0,
    "tool_write": 5.0,
    "sandbox": 10.0,
    "llm_generation": 30.0,
    "sub_agent": 60.0,
    "agent": 300.0,
    "task": 900.0,
    "session_idle": 1800.0,
    "session_max": 86400.0,
    "heartbeat": 30.0,
    "background": 3600.0,
}

#: Layer hierarchy chains (inner -> outer), one per independent family.
#:
#: MCP and tool layers are *siblings* (an agent calls a tool *through* MCP, but
#: they are not a strict parent-child nesting). We therefore model independent
#: monotonic chains, each validated separately.
LAYER_CHAINS: list[list[str]] = [
    # MCP family (inner -> outer)
    ["mcp_connect", "mcp_read", "mcp_total"],
    # Tool / sandbox / LLM / orchestration family (inner -> outer)
    ["tool_read", "tool_write", "sandbox", "llm_generation", "sub_agent", "agent", "task"],
]

#: Backward-compatible alias (the full ordered list).
LAYER_ORDER: list[str] = [layer for chain in LAYER_CHAINS for layer in chain]


@dataclass
class TimeoutPolicy:
    """A layered timeout policy.

    Args:
        timeouts: Layer name -> seconds. Defaults to DEFAULT_TIMEOUTS.
    """

    timeouts: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_TIMEOUTS))

    def get(self, layer: str) -> float:
        """Return the timeout for a layer, raising if unknown."""
        if layer not in self.timeouts:
            raise KeyError(f"Unknown timeout layer '{layer}'. Known: {list(self.timeouts)}")
        return self.timeouts[layer]

    def validate_hierarchy(self) -> list[str]:
        """Verify the inner < outer invariant per family chain.

        Each independent chain in LAYER_CHAINS must be monotonically
        non-decreasing (inner < outer). Returns a list of human-readable
        violation strings (empty if valid).
        """
        violations = []
        for chain in LAYER_CHAINS:
            for i in range(len(chain) - 1):
                inner = chain[i]
                outer = chain[i + 1]
                if inner in self.timeouts and outer in self.timeouts:
                    if self.timeouts[inner] >= self.timeouts[outer]:
                        violations.append(
                            f"{inner}({self.timeouts[inner]}s) >= {outer}({self.timeouts[outer]}s)"
                        )
        return violations

    def remaining(self, layer: str, elapsed: float) -> float:
        """Return the remaining budget for a layer after ``elapsed`` seconds."""
        return max(0.0, self.get(layer) - elapsed)


def build_default_policy() -> TimeoutPolicy:
    """Build a TimeoutPolicy with the architecture doc's recommended values."""
    return TimeoutPolicy()
