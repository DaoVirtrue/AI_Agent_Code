"""OpenAI automatic prompt caching support.

OpenAI provides automatic prefix caching for prompts with prefixes longer
than 1024 tokens. Cached tokens are billed at 50% of standard input price.
The caching is automatic — no API configuration needed.

This module provides estimation and savings calculation for OpenAI's
automatic caching.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class OpenAIPromptCache:
    """Estimate and calculate savings from OpenAI's automatic prefix caching.

    OpenAI automatically caches input prefixes longer than 1024 tokens.
    Cache hits are determined by matching the longest common prefix between
    the current and previous requests. Cached reads are billed at 50% of
    standard input pricing.

    Usage::

        cache = OpenAIPromptCache("gpt-4o")
        hit_rate = cache.estimate_cache_hit(new_messages, previous_messages)
        savings = cache.calculate_savings(5000, 3000)  # 3000 cached out of 5000
    """

    # Minimum prefix length for automatic caching (OpenAI threshold)
    MIN_CACHE_PREFIX_TOKENS: int = 1024

    # Cache discount: 50% of standard input price
    CACHE_DISCOUNT_RATIO: float = 0.50

    def __init__(self, model: str) -> None:
        """Initialize OpenAI cache estimator.

        Args:
            model: OpenAI model identifier.
        """
        self.model = model

    def estimate_cache_hit(
        self,
        messages: list[dict[str, Any]],
        previous_messages: list[dict[str, Any]],
    ) -> float:
        """Estimate what portion of messages will hit the cache.

        Compares the longest common prefix between current and previous
        messages to estimate cache hit rate.

        Args:
            messages: Current messages list.
            previous_messages: Previous messages list.

        Returns:
            Estimated cache hit rate (0.0 to 1.0).
        """
        if not messages or not previous_messages:
            return 0.0

        # Count matching prefix messages
        matching = 0
        for current, previous in zip(messages, previous_messages):
            if self._messages_match(current, previous):
                matching += 1
            else:
                break

        if matching == 0:
            return 0.0

        # Estimate token ratio of matching prefix vs total
        # Rough: matching messages / total messages
        return matching / len(messages) if messages else 0.0

    def estimate_cache_tokens(
        self,
        messages: list[dict[str, Any]],
        previous_messages: list[dict[str, Any]],
        token_counter: Any,
        model: str | None = None,
    ) -> dict[str, int]:
        """Estimate actual cached token counts.

        Args:
            messages: Current messages.
            previous_messages: Previous messages.
            token_counter: TokenCounter instance.
            model: Model for counting (defaults to self.model).

        Returns:
            Dict with estimated_total_tokens, estimated_cached_tokens, estimated_new_tokens.
        """
        effective_model = model if model is not None else self.model

        total = token_counter.count_messages(messages, effective_model)

        if not previous_messages:
            return {
                "estimated_total_tokens": total,
                "estimated_cached_tokens": 0,
                "estimated_new_tokens": total,
            }

        # Find longest common prefix
        matching = 0
        for current, previous in zip(messages, previous_messages):
            if self._messages_match(current, previous):
                matching += 1
            else:
                break

        if matching == 0:
            return {
                "estimated_total_tokens": total,
                "estimated_cached_tokens": 0,
                "estimated_new_tokens": total,
            }

        cached = token_counter.count_messages(messages[:matching], effective_model)
        return {
            "estimated_total_tokens": total,
            "estimated_cached_tokens": cached,
            "estimated_new_tokens": total - cached,
        }

    def calculate_savings(
        self,
        input_tokens: int,
        cached_tokens: int,
        input_price_per_1m: float = 2.50,
    ) -> float:
        """Calculate savings from automatic prefix caching.

        Args:
            input_tokens: Total input tokens.
            cached_tokens: Tokens served from cache.
            input_price_per_1m: Standard input price per 1M tokens.

        Returns:
            Savings in USD.
        """
        if cached_tokens <= 0:
            return 0.0

        input_price_per_token = input_price_per_1m / 1_000_000
        cached_price_per_token = input_price_per_token * self.CACHE_DISCOUNT_RATIO

        cost_without = input_tokens * input_price_per_token
        cost_with = (
            (input_tokens - cached_tokens) * input_price_per_token
            + cached_tokens * cached_price_per_token
        )

        return round(max(0.0, cost_without - cost_with), 6)

    def will_activate_cache(
        self,
        messages: list[dict[str, Any]],
        token_counter: Any,
        model: str | None = None,
    ) -> bool:
        """Check whether OpenAI's automatic caching will activate.

        Requires a prefix of at least MIN_CACHE_PREFIX_TOKENS tokens.

        Args:
            messages: Messages to check.
            token_counter: TokenCounter instance.
            model: Model for counting.

        Returns:
            True if prefix meets the minimum token threshold.
        """
        effective_model = model if model is not None else self.model
        total = token_counter.count_messages(messages, effective_model)
        return total >= self.MIN_CACHE_PREFIX_TOKENS

    def optimize_for_cache(
        self,
        messages: list[dict[str, Any]],
        previous_messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Reorder/restructure messages to maximize cache hits.

        Strategy: Move matching content to the front (prefix position)
        to maximize the common prefix with previous requests.

        Args:
            messages: Current messages to optimize.
            previous_messages: Previous messages to match against.

        Returns:
            Optimized messages list.
        """
        if not previous_messages:
            return list(messages)

        # Identify which messages match previously
        matched_indices: set[int] = set()
        for i, (current, previous) in enumerate(zip(messages, previous_messages)):
            if self._messages_match(current, previous):
                matched_indices.add(i)

        if not matched_indices:
            return list(messages)

        # Identity matched prefix already at front — nothing to do
        max_matched = max(matched_indices)
        if matched_indices == set(range(max_matched + 1)):
            return list(messages)

        # Move matching messages to front
        matched_msgs = [messages[i] for i in sorted(matched_indices)]
        unmatched_msgs = [
            m for i, m in enumerate(messages)
            if i not in matched_indices
        ]

        return matched_msgs + unmatched_msgs

    @staticmethod
    def _messages_match(msg_a: dict[str, Any], msg_b: dict[str, Any]) -> bool:
        """Check if two messages are identical for cache matching purposes.

        Args:
            msg_a: First message dict.
            msg_b: Second message dict.

        Returns:
            True if messages are effectively identical.
        """
        if msg_a.get("role") != msg_b.get("role"):
            return False

        content_a = msg_a.get("content", "")
        content_b = msg_b.get("content", "")

        if isinstance(content_a, str) and isinstance(content_b, str):
            return content_a == content_b
        if isinstance(content_a, list) and isinstance(content_b, list):
            return content_a == content_b

        return str(content_a) == str(content_b)
