"""Token budget allocation and tracking for context windows."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class BudgetConfig:
    """Configuration for token budget allocation percentages.

    All percentages should sum to approximately 1.0. The safety_margin
    reduces the effective context window to avoid edge-case overflows.

    Attributes:
        system_pct: Share for system prompt and instructions.
        fewshot_pct: Share for few-shot examples.
        history_pct: Share for conversation history.
        knowledge_pct: Share for retrieved knowledge / RAG context.
        output_pct: Share reserved for model output.
        safety_margin: Multiplier applied to total window (e.g. 0.95 = 95%).
    """

    system_pct: float = 0.15
    fewshot_pct: float = 0.08
    history_pct: float = 0.50
    knowledge_pct: float = 0.15
    output_pct: float = 0.12
    safety_margin: float = 0.95

    def validate(self) -> list[str]:
        """Validate configuration and return warnings."""
        warnings: list[str] = []
        total = (
            self.system_pct
            + self.fewshot_pct
            + self.history_pct
            + self.knowledge_pct
            + self.output_pct
        )
        if abs(total - 1.0) > 0.05:
            warnings.append(
                f"Budget allocation percentages sum to {total:.2f}, expected ~1.0"
            )
        if not 0.5 <= self.safety_margin <= 1.0:
            warnings.append(
                f"Safety margin {self.safety_margin} is outside recommended range [0.5, 1.0]"
            )
        return warnings


class TokenBudget:
    """Manages token allocation and consumption within a context window.

    Tracks actual token usage per component and warns when a component
    exceeds its allocation.

    Usage::

        budget = TokenBudget(128000, BudgetConfig())
        system_tokens = budget.allocate("system")      # -> 19200
        budget.consume("system", 15000)
        print(budget.remaining("system"))               # -> 4200
        if budget.is_exceeded():
            print(budget.report())
    """

    VALID_COMPONENTS: frozenset[str] = frozenset({
        "system", "fewshot", "history", "knowledge", "output",
    })

    def __init__(
        self,
        context_window: int,
        config: BudgetConfig | None = None,
    ) -> None:
        self.context_window = context_window
        self.config = config if config is not None else BudgetConfig()

        # Derive the effective window after safety margin
        self._effective_window = int(context_window * self.config.safety_margin)

        # Quotas per component
        self._quotas: dict[str, int] = {
            "system": int(self._effective_window * self.config.system_pct),
            "fewshot": int(self._effective_window * self.config.fewshot_pct),
            "history": int(self._effective_window * self.config.history_pct),
            "knowledge": int(self._effective_window * self.config.knowledge_pct),
            "output": int(self._effective_window * self.config.output_pct),
        }

        # Consumption tracking
        self._consumed: dict[str, int] = {
            "system": 0,
            "fewshot": 0,
            "history": 0,
            "knowledge": 0,
            "output": 0,
        }

    def allocate(self, component: str) -> int:
        """Return the token quota allocated to a component.

        Args:
            component: One of 'system', 'fewshot', 'history', 'knowledge', 'output'.

        Returns:
            Token quota for the component.

        Raises:
            ValueError: If component is not valid.
        """
        self._validate_component(component)
        return self._quotas[component]

    def consume(self, component: str, tokens: int) -> None:
        """Record token consumption for a component.

        Args:
            component: The component being consumed.
            tokens: Number of tokens used.

        Raises:
            ValueError: If component is not valid.
        """
        self._validate_component(component)
        self._consumed[component] += tokens

    def remaining(self, component: str) -> int:
        """Return remaining tokens for a component.

        Args:
            component: The component to check.

        Returns:
            Remaining token count (may be negative if over budget).
        """
        self._validate_component(component)
        return self._quotas[component] - self._consumed[component]

    def is_exceeded(self) -> bool:
        """Check whether any component has exceeded its quota.

        Returns:
            True if any component is over budget.
        """
        total_consumed = sum(self._consumed.values())
        if total_consumed > self._effective_window:
            return True
        return any(rem < 0 for rem in self._all_remaining().values())

    def total_consumed(self) -> int:
        """Return total tokens consumed across all components."""
        return sum(self._consumed.values())

    def total_remaining(self) -> int:
        """Return total remaining tokens in the effective window."""
        return max(0, self._effective_window - self.total_consumed())

    def report(self) -> dict:
        """Generate a full budget report with per-component breakdown.

        Returns:
            Dict with quotas, consumption, percentages, and warnings.
        """
        warnings_list: list[str] = []
        components: dict[str, dict[str, int | float | str]] = {}

        for comp in sorted(self.VALID_COMPONENTS):
            quota = self._quotas[comp]
            consumed = self._consumed[comp]
            remaining = quota - consumed
            pct_used = (consumed / quota * 100) if quota > 0 else 0.0

            status = "ok"
            if remaining < 0:
                status = "exceeded"
                warnings_list.append(
                    f"{comp}: exceeded by {-remaining} tokens "
                    f"({pct_used:.1f}% of quota)"
                )
            elif pct_used > 90:
                status = "warning"
                warnings_list.append(
                    f"{comp}: {pct_used:.1f}% of quota used, "
                    f"{remaining} tokens remaining"
                )

            components[comp] = {
                "quota": quota,
                "consumed": consumed,
                "remaining": remaining,
                "pct_used": round(pct_used, 1),
                "status": status,
            }

        total_consumed = self.total_consumed()
        total_pct = (
            (total_consumed / self._effective_window * 100)
            if self._effective_window > 0
            else 0.0
        )

        return {
            "context_window": self.context_window,
            "effective_window": self._effective_window,
            "safety_margin": self.config.safety_margin,
            "total_consumed": total_consumed,
            "total_remaining": self.total_remaining(),
            "total_pct_used": round(total_pct, 1),
            "is_exceeded": self.is_exceeded(),
            "components": components,
            "warnings": warnings_list,
        }

    def reset(self) -> None:
        """Reset all consumption counters to zero."""
        for key in self._consumed:
            self._consumed[key] = 0

    def resize(self, new_context_window: int) -> None:
        """Resize the budget for a new context window, preserving ratios.

        Args:
            new_context_window: New context window size in tokens.
        """
        self.context_window = new_context_window
        self._effective_window = int(new_context_window * self.config.safety_margin)
        for comp in self.VALID_COMPONENTS:
            pct = getattr(self.config, f"{comp}_pct")
            self._quotas[comp] = int(self._effective_window * pct)

    def _validate_component(self, component: str) -> None:
        if component not in self.VALID_COMPONENTS:
            raise ValueError(
                f"Invalid component '{component}'. "
                f"Must be one of: {sorted(self.VALID_COMPONENTS)}"
            )

    def _all_remaining(self) -> dict[str, int]:
        return {comp: self.remaining(comp) for comp in self.VALID_COMPONENTS}
