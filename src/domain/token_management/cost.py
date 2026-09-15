"""Cost tracking and estimation for LLM API usage."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ModelPricing:
    """Pricing information for a specific model.

    All prices are in USD per 1 million tokens.

    Attributes:
        model_id: Model identifier string.
        input_price_per_1m: USD per 1M input tokens.
        output_price_per_1m: USD per 1M output tokens.
        cached_input_price_per_1m: USD per 1M cached input tokens (default 0.0).
    """

    model_id: str
    input_price_per_1m: float
    output_price_per_1m: float
    cached_input_price_per_1m: float = 0.0

    @property
    def input_price_per_token(self) -> float:
        """Price per single input token."""
        return self.input_price_per_1m / 1_000_000

    @property
    def output_price_per_token(self) -> float:
        """Price per single output token."""
        return self.output_price_per_1m / 1_000_000

    @property
    def cached_input_price_per_token(self) -> float:
        """Price per single cached input token."""
        return self.cached_input_price_per_1m / 1_000_000


class CostTracker:
    """Tracks and estimates costs for LLM API usage.

    Provides per-model pricing data, cost calculation, and estimation
    for message arrays before making API calls.

    Pricing data is sourced from official provider pricing pages and
    should be updated periodically. Dates: June 2026 pricing snapshot.
    """

    PRICING: dict[str, ModelPricing] = {
        # OpenAI
        "gpt-4o": ModelPricing("gpt-4o", 2.50, 10.00, 1.25),
        "gpt-4o-mini": ModelPricing("gpt-4o-mini", 0.15, 0.60, 0.075),
        "gpt-4o-2024-08-06": ModelPricing("gpt-4o-2024-08-06", 2.50, 10.00, 1.25),
        "gpt-4": ModelPricing("gpt-4", 30.00, 60.00),
        "gpt-4-32k": ModelPricing("gpt-4-32k", 60.00, 120.00),
        "gpt-3.5-turbo": ModelPricing("gpt-3.5-turbo", 0.50, 1.50),
        "gpt-3.5-turbo-16k": ModelPricing("gpt-3.5-turbo-16k", 3.00, 4.00),
        "o1": ModelPricing("o1", 15.00, 60.00, 7.50),
        "o1-mini": ModelPricing("o1-mini", 1.10, 4.40, 0.55),
        "o3-mini": ModelPricing("o3-mini", 1.10, 4.40),
        "gpt-4.1": ModelPricing("gpt-4.1", 2.00, 8.00, 0.50),
        "gpt-4.1-mini": ModelPricing("gpt-4.1-mini", 0.40, 1.60, 0.10),
        "gpt-4.1-nano": ModelPricing("gpt-4.1-nano", 0.10, 0.40, 0.025),
        # Anthropic
        "claude-sonnet-4": ModelPricing("claude-sonnet-4", 3.00, 15.00, 0.30),
        "claude-opus-4": ModelPricing("claude-opus-4", 15.00, 75.00, 1.50),
        "claude-3.5-haiku": ModelPricing("claude-3.5-haiku", 0.80, 4.00, 0.08),
        "claude-3-opus": ModelPricing("claude-3-opus", 15.00, 75.00),
        "claude-3-sonnet": ModelPricing("claude-3-sonnet", 3.00, 15.00),
        "claude-3-haiku": ModelPricing("claude-3-haiku", 0.25, 1.25),
        "claude-3.5-sonnet": ModelPricing("claude-3.5-sonnet", 3.00, 15.00, 0.30),
        "claude-3.5-haiku": ModelPricing("claude-3.5-haiku", 0.80, 4.00, 0.08),
        # DeepSeek
        "deepseek-chat": ModelPricing("deepseek-chat", 0.27, 1.10, 0.014),
        "deepseek-reasoner": ModelPricing("deepseek-reasoner", 0.55, 2.19, 0.014),
        # Qwen (Alibaba)
        "qwen-max": ModelPricing("qwen-max", 2.00, 8.00),
        "qwen-plus": ModelPricing("qwen-plus", 0.80, 2.00),
        "qwen-turbo": ModelPricing("qwen-turbo", 0.30, 0.60),
        "qwen3-235b-a22b": ModelPricing("qwen3-235b-a22b", 0.50, 2.00),
        # Google
        "gemini-2.5-pro": ModelPricing("gemini-2.5-pro", 2.50, 15.00),
        "gemini-2.5-flash": ModelPricing("gemini-2.5-flash", 0.30, 1.50),
        "gemini-2.0-flash": ModelPricing("gemini-2.0-flash", 0.10, 0.40),
        "gemini-1.5-pro": ModelPricing("gemini-1.5-pro", 1.25, 5.00),
        "gemini-1.5-flash": ModelPricing("gemini-1.5-flash", 0.075, 0.30),
        # Mistral
        "mistral-large": ModelPricing("mistral-large", 2.00, 6.00),
        "mistral-medium": ModelPricing("mistral-medium", 0.75, 2.30),
        "mistral-small": ModelPricing("mistral-small", 0.20, 0.60),
        "codestral": ModelPricing("codestral", 0.30, 0.90),
        # Meta (via providers)
        "llama-3-8b": ModelPricing("llama-3-8b", 0.0, 0.0),
        "llama-3-70b": ModelPricing("llama-3-70b", 0.0, 0.0),
        "llama-3.1-8b": ModelPricing("llama-3.1-8b", 0.0, 0.0),
        "llama-3.1-70b": ModelPricing("llama-3.1-70b", 0.0, 0.0),
        "llama-3.1-405b": ModelPricing("llama-3.1-405b", 0.0, 0.0),
        # Grok (xAI)
        "grok-3": ModelPricing("grok-3", 5.00, 15.00),
        "grok-3-mini": ModelPricing("grok-3-mini", 0.30, 0.50),
    }

    def __init__(self) -> None:
        self._pricing_lower: dict[str, ModelPricing] = {
            k.lower(): v for k, v in self.PRICING.items()
        }

    def get_pricing(self, model: str) -> ModelPricing | None:
        """Look up pricing data for a model.

        Args:
            model: Model identifier string.

        Returns:
            ModelPricing dataclass or None if not found.
        """
        return self._pricing_lower.get(model.lower())

    def calculate(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cached_input_tokens: int = 0,
    ) -> float:
        """Calculate the USD cost for a completed API call.

        Args:
            model: Model identifier.
            input_tokens: Number of input tokens.
            output_tokens: Number of output tokens.
            cached_input_tokens: Number of cached input tokens (billed at lower rate).

        Returns:
            Cost in USD (float, rounded to 6 decimal places).

        Raises:
            ValueError: If model pricing is unknown.
        """
        pricing = self.get_pricing(model)
        if pricing is None:
            raise ValueError(
                f"No pricing data for model '{model}'. "
                f"Available: {sorted(self.PRICING.keys())}"
            )

        uncached_input = input_tokens - cached_input_tokens
        cost = (
            uncached_input * pricing.input_price_per_token
            + cached_input_tokens * pricing.cached_input_price_per_token
            + output_tokens * pricing.output_price_per_token
        )

        return round(cost, 6)

    def estimate(
        self,
        model: str,
        messages: list[dict[str, Any]],
        expected_output_tokens: int = 500,
    ) -> float:
        """Estimate the cost of a request before making the API call.

        Uses cjk/latin character heuristic if no token_counter is explicitly
        provided. This is a rough estimate; for production use pass the result
        to calculate() with actual tokenizer output.

        Args:
            model: Model identifier.
            messages: Message list to estimate input tokens from.
            expected_output_tokens: Anticipated output token count.

        Returns:
            Estimated cost in USD.

        Raises:
            ValueError: If model pricing is unknown.
        """
        pricing = self.get_pricing(model)
        if pricing is None:
            raise ValueError(
                f"No pricing data for model '{model}'."
            )

        estimated_input = self._estimate_tokens_from_messages(messages)
        cost = (
            estimated_input * pricing.input_price_per_token
            + expected_output_tokens * pricing.output_price_per_token
        )
        return round(cost, 6)

    def estimate_batch(
        self,
        model: str,
        requests: list[dict[str, Any]],
        avg_output_tokens: int = 500,
    ) -> float:
        """Estimate total cost for a batch of requests.

        Args:
            model: Model identifier.
            requests: List of request dicts, each with a 'messages' key.
            avg_output_tokens: Average expected output tokens per request.

        Returns:
            Total estimated cost in USD.
        """
        total = 0.0
        for req in requests:
            messages = req.get("messages", [])
            total += self.estimate(model, messages, avg_output_tokens)
        return round(total, 6)

    def compare_models(
        self,
        messages: list[dict[str, Any]],
        models: list[str],
        expected_output_tokens: int = 500,
    ) -> dict[str, float]:
        """Compare estimated costs across multiple models.

        Args:
            messages: Message list to estimate from.
            models: List of model identifiers to compare.
            expected_output_tokens: Anticipated output tokens.

        Returns:
            Dict mapping model_id to estimated USD cost.
        """
        result: dict[str, float] = {}
        for model in models:
            try:
                result[model] = self.estimate(model, messages, expected_output_tokens)
            except ValueError:
                result[model] = float("inf")
        return dict(sorted(result.items(), key=lambda x: x[1]))

    def _estimate_tokens_from_messages(self, messages: list[dict[str, Any]]) -> int:
        """Quick token estimate from message content without heavy tokenizer."""
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += self._estimate_tokens_from_text(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        total += self._estimate_tokens_from_text(part.get("text", ""))
                    elif isinstance(part, str):
                        total += self._estimate_tokens_from_text(part)
            else:
                total += self._estimate_tokens_from_text(str(content))
        return total

    @staticmethod
    def _estimate_tokens_from_text(text: str) -> int:
        """Character-based token estimate: ~4 chars per token."""
        if not text:
            return 0
        return max(1, len(text) // 4)

    @classmethod
    def register_pricing(cls, pricing: ModelPricing) -> None:
        """Dynamically register pricing for a new model.

        Args:
            pricing: ModelPricing instance.
        """
        cls.PRICING[pricing.model_id] = pricing

    @staticmethod
    def format_cost(cost_usd: float) -> str:
        """Format a cost amount for human display.

        Args:
            cost_usd: Cost in USD.

        Returns:
            Formatted string like "$0.004200".
        """
        if cost_usd < 0.01:
            return f"${cost_usd:.6f}".rstrip("0").rstrip(".")
        if cost_usd < 1.0:
            return f"${cost_usd:.4f}".rstrip("0").rstrip(".")
        return f"${cost_usd:.2f}"
