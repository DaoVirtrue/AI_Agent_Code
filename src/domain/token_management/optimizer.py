"""Cost optimization strategies for LLM usage.

Recommends model switches, cache usage decisions, and prompt
optimization to reduce API costs.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from src.domain.token_management.cost import CostTracker, ModelPricing

logger = logging.getLogger(__name__)


class CostOptimizer:
    """Cost optimization engine for LLM interactions.

    Provides:
    - Model switch recommendations based on task type
    - Cache usage decisions
    - Cache savings estimation
    - Prompt truncation to reduce input costs
    """

    # Task-to-model recommendations (cheaper alternatives listed first)
    TASK_MODEL_MAP: dict[str, list[str]] = {
        "classification": ["gpt-4o-mini", "claude-3.5-haiku", "gpt-4o"],
        "extraction": ["gpt-4o-mini", "claude-sonnet-4", "gpt-4o"],
        "summarization": ["gpt-4o-mini", "claude-3.5-haiku", "gpt-4o"],
        "translation": ["gpt-4o-mini", "claude-3.5-haiku"],
        "chat": ["gpt-4o-mini", "claude-sonnet-4", "gpt-4o"],
        "code_generation": ["claude-sonnet-4", "gpt-4o", "deepseek-chat"],
        "reasoning": ["claude-opus-4", "gpt-4o", "deepseek-reasoner"],
        "creative_writing": ["claude-sonnet-4", "gpt-4o"],
        "analysis": ["claude-sonnet-4", "gpt-4o", "deepseek-chat"],
        "rag": ["gpt-4o-mini", "claude-3.5-haiku", "gpt-4o"],
        "tool_use": ["gpt-4o-mini", "claude-sonnet-4", "gpt-4o"],
        "embedding": ["text-embedding-3-small", "text-embedding-3-large"],
        "default": ["gpt-4o-mini", "claude-sonnet-4", "gpt-4o"],
    }

    def __init__(self, cost_tracker: CostTracker | None = None) -> None:
        self.cost_tracker = cost_tracker if cost_tracker is not None else CostTracker()
        self._cache_hit_history: dict[str, int] = {}
        self._model_usage_stats: dict[str, dict[str, Any]] = {}

    def recommend_model_switch(
        self,
        task_type: str,
        current_model: str,
        budget_constraint: float | None = None,
    ) -> str | None:
        """Recommend a cheaper model for the given task type.

        Args:
            task_type: Type of task (classification, extraction, etc.).
            current_model: Currently used model identifier.
            budget_constraint: Optional max cost per 1M tokens.

        Returns:
            Recommended model ID or None if current model is optimal.
        """
        candidates = self.TASK_MODEL_MAP.get(
            task_type.lower(),
            self.TASK_MODEL_MAP["default"],
        )

        current_pricing = self.cost_tracker.get_pricing(current_model)
        if current_pricing is None:
            logger.warning("Unknown model '%s', cannot recommend switch", current_model)
            return None

        current_price = current_pricing.input_price_per_1m

        for candidate in candidates:
            if candidate == current_model:
                continue
            candidate_pricing = self.cost_tracker.get_pricing(candidate)
            if candidate_pricing is None:
                continue
            if budget_constraint is not None and candidate_pricing.input_price_per_1m > budget_constraint:
                continue
            if candidate_pricing.input_price_per_1m < current_price:
                logger.info(
                    "Recommend switching from %s ($%.2f/M) to %s ($%.2f/M) for %s",
                    current_model,
                    current_price,
                    candidate,
                    candidate_pricing.input_price_per_1m,
                    task_type,
                )
                return candidate

        return None

    def should_use_cache(self, model: str, messages_hash: str) -> bool:
        """Determine whether to use prompt caching for a request.

        Decision is based on:
        1. Whether the model supports caching (has cached pricing)
        2. Historical cache hit rate for this messages pattern
        3. The savings potential

        Args:
            model: Model identifier.
            messages_hash: Hash of the messages content.

        Returns:
            True if caching is recommended.
        """
        pricing = self.cost_tracker.get_pricing(model)
        if pricing is None:
            return False

        # No cache pricing = provider doesn't support caching
        if pricing.cached_input_price_per_1m <= 0 and pricing.cached_input_price_per_token <= 0:
            return False

        # If we've seen this pattern before with good hit rate
        hit_count = self._cache_hit_history.get(messages_hash, 0)
        total_lookups = sum(self._cache_hit_history.values()) or 1
        past_hit_rate = self._cache_hit_history.get(
            messages_hash, 0
        ) / max(total_lookups, 1)

        # Use cache if there's any saving potential
        savings_per_token = pricing.input_price_per_token - pricing.cached_input_price_per_token
        if savings_per_token <= 0:
            return False

        # For repeated patterns, definitely cache
        if past_hit_rate > 0.3:
            return True

        # Default: use cache if savings exceed 10% of input price
        return savings_per_token > pricing.input_price_per_token * 0.1

    def record_cache_hit(self, messages_hash: str) -> None:
        """Record a successful cache hit for analysis.

        Args:
            messages_hash: Hash of the cached messages pattern.
        """
        self._cache_hit_history[messages_hash] = (
            self._cache_hit_history.get(messages_hash, 0) + 1
        )

    def estimate_cache_savings(self, model: str, cached_pct: float) -> float:
        """Estimate cost savings from prompt caching.

        Args:
            model: Model identifier.
            cached_pct: Expected percentage of input tokens served from cache (0.0-1.0).

        Returns:
            Estimated savings ratio (e.g., 0.5 = 50% cheaper).
        """
        pricing = self.cost_tracker.get_pricing(model)
        if pricing is None or pricing.input_price_per_token <= 0:
            return 0.0

        cached_price = pricing.cached_input_price_per_token
        if cached_price <= 0:
            return 0.0

        # Without cache: full input price
        # With cache: (1 - cached_pct) * full_price + cached_pct * cached_price
        cost_without_cache = pricing.input_price_per_token
        cost_with_cache = (
            (1 - cached_pct) * pricing.input_price_per_token
            + cached_pct * cached_price
        )

        if cost_without_cache <= 0:
            return 0.0

        savings = 1.0 - (cost_with_cache / cost_without_cache)
        return round(savings, 4)

    def optimize_prompt(
        self,
        messages: list[dict[str, Any]],
        model: str,
        max_tokens: int | None = None,
    ) -> list[dict[str, Any]]:
        """Optimize a prompt by truncating non-essential parts.

        Strategy:
        1. Always preserve system messages.
        2. For long conversations, keep first and last N turns.
        3. Truncate oversized messages to fit token budget.

        Args:
            messages: Original messages list.
            model: Model identifier.
            max_tokens: Target token budget (uses model default if None).

        Returns:
            Optimized (potentially truncated) messages list.
        """
        if not messages:
            return []

        if max_tokens is None:
            from src.domain.token_management.budget import BudgetConfig, TokenBudget

            budget_config = BudgetConfig(
                system_pct=0.15,
                fewshot_pct=0.08,
                history_pct=0.50,
                knowledge_pct=0.15,
                output_pct=0.12,
            )
            budget = TokenBudget(128000, budget_config)
            max_tokens = budget.allocate("history")

        # Find system messages (always preserve)
        system_msgs = [m for m in messages if m.get("role") == "system"]
        non_system = [m for m in messages if m.get("role") != "system"]

        # For small conversations, no optimization needed
        total_tokens = sum(self._rough_count(str(m.get("content", ""))) for m in messages)
        if total_tokens <= max_tokens:
            return messages

        result = list(system_msgs)
        remaining = max_tokens - sum(
            self._rough_count(str(m.get("content", ""))) for m in system_msgs
        )

        # Keep first 2 and last 3 non-system messages, truncate middle
        if len(non_system) <= 5:
            result.extend(non_system)
            return result

        first_n = non_system[:2]
        last_n = non_system[-3:]
        middle = non_system[2:-3]

        for msg in first_n:
            cost = self._rough_count(str(msg.get("content", "")))
            if remaining >= cost:
                result.append(msg)
                remaining -= cost

        if middle:
            result.append({
                "role": "system",
                "content": (
                    f"[{len(middle)} messages omitted for brevity. "
                    f"The conversation continues from where it left off.]"
                ),
            })
            omitted_tokens = self._rough_count(result[-1]["content"])
            remaining -= omitted_tokens

        for msg in last_n:
            cost = self._rough_count(str(msg.get("content", "")))
            if remaining >= cost * 0.5:
                # Permit slight overshoot for the most recent messages
                result.append(msg)
                remaining -= cost

        return result

    def estimate_optimal_prompt_size(
        self,
        model: str,
        task_type: str,
        output_desired: int = 500,
    ) -> tuple[int, float]:
        """Estimate optimal prompt size for a given task and model.

        Args:
            model: Model identifier.
            task_type: Task type.
            output_desired: Desired output tokens.

        Returns:
            Tuple of (optimal_input_tokens, estimated_cost_usd).
        """
        pricing = self.cost_tracker.get_pricing(model)
        if pricing is None:
            return 500, 0.0

        # Simple heuristic: output * 5 for input is typical for many tasks
        input_multipliers: dict[str, float] = {
            "classification": 2.0,
            "extraction": 3.0,
            "summarization": 8.0,
            "translation": 1.5,
            "chat": 4.0,
            "code_generation": 3.0,
            "reasoning": 5.0,
            "creative_writing": 2.0,
            "analysis": 5.0,
            "rag": 6.0,
            "default": 4.0,
        }

        multiplier = input_multipliers.get(task_type.lower(), 4.0)
        optimal_input = int(output_desired * multiplier)

        cost = (
            optimal_input * pricing.input_price_per_token
            + output_desired * pricing.output_price_per_token
        )
        return optimal_input, round(cost, 6)

    @staticmethod
    def _rough_count(text: str) -> int:
        """Very rough token count: 1 token ≈ 4 characters."""
        if not text:
            return 0
        return max(1, len(text) // 4)

    @staticmethod
    def hash_messages(messages: list[dict[str, Any]]) -> str:
        """Generate a deterministic hash for a messages list.

        Args:
            messages: List of message dicts.

        Returns:
            SHA-256 hex digest string.
        """
        canonical = json.dumps(messages, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
