"""Anthropic prompt caching with configurable strategies.

Implements Anthropic's prompt caching mechanism, which allows marking
cacheable content blocks with cache_control breakpoints. Cached content
is billed at 10% of the standard input price for reads.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class CacheStrategy(Enum):
    """Strategies for what to cache in Anthropic prompts.

    Attributes:
        FULL_PROMPT: Cache the entire prompt. Simplest, but no dynamic content.
        PREFIX: Cache a specific prefix (system prompt typically).
        SEGMENT: Cache individual segments with boundaries.
        DYNAMIC_TAIL: Cache system + fewshot, leave final user message uncached.
            Best for multi-turn conversations with varying queries.
    """

    FULL_PROMPT = "full_prompt"
    PREFIX = "prefix"
    SEGMENT = "segment"
    DYNAMIC_TAIL = "dynamic_tail"


class AnthropicPromptCache:
    """Build Anthropic API requests with cache_control breakpoints.

    Anthropic caches content up to each cache_control breakpoint. The cache
    key is the full prefix of the prompt — changing any cached segment
    invalidates the cache for that point onward.

    Cached reads are billed at 10% of standard input price.

    Usage::

        cache = AnthropicPromptCache("claude-sonnet-4", 3.00, 0.30)
        request = cache.build_cached_request(
            system_prompt="You are a helpful assistant.",
            fewshot_examples=[...],
            user_message="What is the weather?",
            strategy=CacheStrategy.DYNAMIC_TAIL,
        )
    """

    def __init__(
        self,
        model: str,
        full_price: float,
        cached_price: float,
    ) -> None:
        """Initialize the Anthropic prompt cache builder.

        Args:
            model: Anthropic model identifier.
            full_price: Full input price per 1M tokens (USD).
            cached_price: Cached input price per 1M tokens (USD).
        """
        self.model = model
        self.full_price = full_price
        self.cached_price = cached_price

    def build_cached_request(
        self,
        system_prompt: str,
        fewshot_examples: list[dict[str, Any]],
        user_message: str,
        strategy: CacheStrategy = CacheStrategy.DYNAMIC_TAIL,
    ) -> dict[str, Any]:
        """Build an API request with appropriate cache_control breakpoints.

        Args:
            system_prompt: System-level instruction text.
            fewshot_examples: List of example message dicts.
            user_message: The actual user query (uncached for DYNAMIC_TAIL).
            strategy: Caching strategy to use.

        Returns:
            Dict suitable for Anthropic Messages API with cache_control.
        """
        if strategy == CacheStrategy.FULL_PROMPT:
            return self._build_full_prompt_cache(system_prompt, fewshot_examples, user_message)
        elif strategy == CacheStrategy.PREFIX:
            return self._build_prefix_cache(system_prompt, fewshot_examples, user_message)
        elif strategy == CacheStrategy.SEGMENT:
            return self._build_segment_cache(system_prompt, fewshot_examples, user_message)
        elif strategy == CacheStrategy.DYNAMIC_TAIL:
            return self._build_dynamic_tail_cache(system_prompt, fewshot_examples, user_message)
        else:
            logger.warning("Unknown strategy '%s', falling back to DYNAMIC_TAIL", strategy)
            return self._build_dynamic_tail_cache(system_prompt, fewshot_examples, user_message)

    def calculate_savings(self, usage: dict[str, Any]) -> float:
        """Calculate savings from prompt caching based on API usage response.

        Args:
            usage: Usage dict from Anthropic API response.
                Expected keys: input_tokens, cache_creation_input_tokens,
                cache_read_input_tokens.

        Returns:
            Savings in USD.
        """
        cache_creation = usage.get("cache_creation_input_tokens", 0)
        cache_read = usage.get("cache_read_input_tokens", 0)
        regular_input = usage.get("input_tokens", 0)

        # Cache creation is billed at full price
        # Cache reads are billed at cached price
        cost_without_cache = (
            (cache_creation + cache_read + regular_input) * self.full_price / 1_000_000
        )
        cost_with_cache = (
            (cache_creation + regular_input) * self.full_price / 1_000_000
            + cache_read * self.cached_price / 1_000_000
        )

        savings = cost_without_cache - cost_with_cache
        return round(max(0.0, savings), 6)

    def estimate_savings(
        self,
        estimated_input_tokens: int,
        estimated_cached_tokens: int,
        estimated_requests: int = 1,
    ) -> dict[str, float]:
        """Estimate savings for a given token distribution.

        Args:
            estimated_input_tokens: Total input tokens per request.
            estimated_cached_tokens: Tokens expected to be cached per request.
            estimated_requests: Number of requests.

        Returns:
            Dict with cost_without_cache, cost_with_cache, savings_usd, savings_pct.
        """
        uncached = estimated_input_tokens - estimated_cached_tokens

        cost_without = (
            estimated_input_tokens * self.full_price / 1_000_000 * estimated_requests
        )
        cost_with = (
            (uncached * self.full_price + estimated_cached_tokens * self.cached_price)
            / 1_000_000
            * estimated_requests
        )

        savings = cost_without - cost_with
        savings_pct = (savings / cost_without * 100) if cost_without > 0 else 0.0

        return {
            "cost_without_cache": round(cost_without, 6),
            "cost_with_cache": round(cost_with, 6),
            "savings_usd": round(savings, 6),
            "savings_pct": round(savings_pct, 1),
        }

    def _should_cache(self, content: str, hit_rate: float) -> bool:
        """Decide whether to cache a piece of content.

        Args:
            content: Content string.
            hit_rate: Expected cache hit rate (0.0 to 1.0).

        Returns:
            True if caching is beneficial.
        """
        if not content:
            return False

        # Minimum content length to warrant caching (tokens ~= chars/4)
        min_chars = 200  # ~50 tokens minimum
        if len(content) < min_chars:
            return False

        # Only cache if there's meaningful savings
        savings_ratio = 1.0 - (self.cached_price / self.full_price if self.full_price > 0 else 0)
        expected_benefit = hit_rate * savings_ratio

        # Cache if expected benefit exceeds 5%
        return expected_benefit >= 0.05

    def _make_cache_control(self) -> dict[str, dict[str, str]]:
        """Create a cache_control dict for Anthropic API."""
        return {"cache_control": {"type": "ephemeral"}}

    def _build_full_prompt_cache(
        self,
        system_prompt: str,
        fewshot_examples: list[dict[str, Any]],
        user_message: str,
    ) -> dict[str, Any]:
        """Cache entire prompt."""
        system_block = (
            {"type": "text", "text": system_prompt, **self._make_cache_control()}
            if system_prompt
            else None
        )

        messages = []

        # Build few-shot as cached messages
        for example in fewshot_examples:
            msg = dict(example)
            if messages or system_block:
                # Only first content block needs cache_control
                pass
            messages.append(msg)

        # User message
        messages.append({"role": "user", "content": user_message, **self._make_cache_control()})

        request: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
        }

        if system_block:
            if isinstance(system_block, dict) and "cache_control" not in system_block:
                system_block["cache_control"] = {"type": "ephemeral"}
            request["system"] = system_block

        return request

    def _build_prefix_cache(
        self,
        system_prompt: str,
        fewshot_examples: list[dict[str, Any]],
        user_message: str,
    ) -> dict[str, Any]:
        """Cache only the system prompt prefix."""
        request: dict[str, Any] = {
            "model": self.model,
            "messages": [],
        }

        if system_prompt:
            request["system"] = [
                {
                    "type": "text",
                    "text": system_prompt,
                    **self._make_cache_control(),
                }
            ]

        # Fewshot examples and user message remain uncached
        messages = list(fewshot_examples)
        messages.append({"role": "user", "content": user_message})
        request["messages"] = messages

        return request

    def _build_segment_cache(
        self,
        system_prompt: str,
        fewshot_examples: list[dict[str, Any]],
        user_message: str,
    ) -> dict[str, Any]:
        """Cache system prompt and each fewshot segment independently."""
        request: dict[str, Any] = {
            "model": self.model,
            "messages": [],
        }

        if system_prompt:
            request["system"] = [
                {
                    "type": "text",
                    "text": system_prompt,
                    **self._make_cache_control(),
                }
            ]

        messages: list[dict[str, Any]] = []
        for i, example in enumerate(fewshot_examples):
            msg = dict(example)
            if i < len(fewshot_examples) - 1:
                # Cache each example individually
                content = msg.get("content", "")
                if isinstance(content, str):
                    msg["content"] = [
                        {"type": "text", "text": content, **self._make_cache_control()}
                    ]
                elif isinstance(content, list):
                    # Add cache to last content block
                    if content:
                        content[-1] = {**content[-1], **self._make_cache_control()}
                    msg["content"] = content
            messages.append(msg)

        messages.append({"role": "user", "content": user_message})
        request["messages"] = messages

        return request

    def _build_dynamic_tail_cache(
        self,
        system_prompt: str,
        fewshot_examples: list[dict[str, Any]],
        user_message: str,
    ) -> dict[str, Any]:
        """Cache system + fewshot but NOT the final user message.

        This is the best strategy for multi-turn conversations where
        the user query changes each time.
        """
        request: dict[str, Any] = {
            "model": self.model,
            "messages": [],
        }

        # System prompt with cache breakpoint
        if system_prompt:
            request["system"] = [
                {
                    "type": "text",
                    "text": system_prompt,
                    **self._make_cache_control(),
                }
            ]

        # Fewshot examples: add cache breakpoint to the LAST fewshot
        messages: list[dict[str, Any]] = []
        if fewshot_examples:
            for example in fewshot_examples[:-1]:
                messages.append(dict(example))

            # Last fewshot gets cache breakpoint
            last_fewshot = dict(fewshot_examples[-1])
            content = last_fewshot.get("content", "")
            if isinstance(content, str):
                last_fewshot["content"] = [
                    {"type": "text", "text": content, **self._make_cache_control()}
                ]
            elif isinstance(content, list) and content:
                content[-1] = {**content[-1], **self._make_cache_control()}
                last_fewshot["content"] = content
            messages.append(last_fewshot)

        # User message is NOT cached (dynamic tail)
        messages.append({"role": "user", "content": user_message})

        request["messages"] = messages
        return request
