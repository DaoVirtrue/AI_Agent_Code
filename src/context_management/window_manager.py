"""Context window size database for all supported models."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ContextWindowManager:
    """Central registry of context window sizes for supported models.

    Provides lookup, validation of context fit, and listing of all
    known model windows.

    Usage::

        mgr = ContextWindowManager()
        window = mgr.get_window("gpt-4o")  # 128000
        fits = mgr.is_within_window(messages, "gpt-4o", counter)
    """

    MODEL_WINDOWS: dict[str, int] = {
        # OpenAI
        "gpt-4o": 128_000,
        "gpt-4o-mini": 128_000,
        "gpt-4o-2024-08-06": 128_000,
        "gpt-4": 8_192,
        "gpt-4-32k": 32_768,
        "gpt-3.5-turbo": 16_385,
        "gpt-3.5-turbo-16k": 16_385,
        "gpt-3.5-turbo-instruct": 4_096,
        "o1": 200_000,
        "o1-mini": 128_000,
        "o3-mini": 200_000,
        "gpt-4.1": 1_000_000,
        "gpt-4.1-mini": 1_000_000,
        "gpt-4.1-nano": 1_000_000,
        # Anthropic
        "claude-sonnet-4": 200_000,
        "claude-opus-4": 200_000,
        "claude-3.5-haiku": 200_000,
        "claude-3-opus": 200_000,
        "claude-3-sonnet": 200_000,
        "claude-3-haiku": 200_000,
        "claude-3.5-sonnet": 200_000,
        "claude-3.5-haiku": 200_000,
        # DeepSeek
        "deepseek-chat": 128_000,
        "deepseek-reasoner": 128_000,
        # Qwen (Alibaba)
        "qwen-max": 32_768,
        "qwen-plus": 131_072,
        "qwen-turbo": 1_000_000,
        "qwen3-235b-a22b": 131_072,
        # Google
        "gemini-2.5-pro": 1_000_000,
        "gemini-2.5-flash": 1_000_000,
        "gemini-2.0-flash": 1_000_000,
        "gemini-1.5-pro": 2_000_000,
        "gemini-1.5-flash": 1_000_000,
        # Mistral
        "mistral-large": 131_072,
        "mistral-medium": 32_768,
        "mistral-small": 32_768,
        "codestral": 32_768,
        # Open-weight
        "llama-3-8b": 8_192,
        "llama-3-70b": 8_192,
        "llama-3.1-8b": 131_072,
        "llama-3.1-70b": 131_072,
        "llama-3.1-405b": 131_072,
        "mistral-7b": 32_768,
        "mixtral-8x7b": 32_768,
        # xAI Grok
        "grok-3": 1_000_000,
        "grok-3-mini": 1_000_000,
        # Alibaba
        "qwen-2-7b": 32_768,
        "qwen-2-72b": 32_768,
    }

    def __init__(self) -> None:
        self._windows_lower: dict[str, int] = {
            k.lower(): v for k, v in self.MODEL_WINDOWS.items()
        }

    def get_window(self, model: str) -> int:
        """Get the context window size for a model.

        Args:
            model: Model identifier.

        Returns:
            Context window size in tokens. Defaults to 4096 for unknown models.

        Raises:
            No exception — returns a safe default of 4096.
        """
        size = self._windows_lower.get(model.lower())
        if size is None:
            logger.warning("Unknown model '%s', defaulting to 4096 token window", model)
            return 4_096
        return size

    def get_all_windows(self) -> dict[str, int]:
        """Return all known model context windows.

        Returns:
            Dict mapping model IDs to window sizes (sorted by size descending).
        """
        return dict(
            sorted(self.MODEL_WINDOWS.items(), key=lambda x: x[1], reverse=True)
        )

    def get_models_by_window(self, min_tokens: int | None = None, max_tokens: int | None = None) -> dict[str, int]:
        """Filter models by context window range.

        Args:
            min_tokens: Minimum context window size.
            max_tokens: Maximum context window size.

        Returns:
            Filtered dict of model_id -> window_size.
        """
        result: dict[str, int] = {}
        for model, size in self.MODEL_WINDOWS.items():
            if min_tokens is not None and size < min_tokens:
                continue
            if max_tokens is not None and size > max_tokens:
                continue
            result[model] = size
        return dict(sorted(result.items(), key=lambda x: x[1], reverse=True))

    def is_within_window(
        self,
        messages: list[dict[str, Any]],
        model: str,
        token_counter: Any,
    ) -> bool:
        """Check whether messages fit within the model's context window.

        Args:
            messages: List of message dicts.
            model: Model identifier.
            token_counter: TokenCounter instance for counting.

        Returns:
            True if messages fit within the window.
        """
        window = self.get_window(model)
        token_count = token_counter.count_messages(messages, model)
        return token_count <= window

    def get_fill_percentage(
        self,
        messages: list[dict[str, Any]],
        model: str,
        token_counter: Any,
    ) -> float:
        """Get percentage of context window used by messages.

        Args:
            messages: List of message dicts.
            model: Model identifier.
            token_counter: TokenCounter instance.

        Returns:
            Percentage (0.0 to 100.0+).
        """
        window = self.get_window(model)
        if window <= 0:
            return 0.0
        token_count = token_counter.count_messages(messages, model)
        return round((token_count / window) * 100, 1)

    def recommend_model_for_tokens(
        self,
        required_tokens: int,
        exclude_models: list[str] | None = None,
    ) -> str | None:
        """Recommend a model that can handle the required token count.

        Args:
            required_tokens: Minimum context window needed.
            exclude_models: Models to exclude from consideration.

        Returns:
            Model ID or None if no model fits.
        """
        exclude = set(m.lower() for m in (exclude_models or []))
        best_model: str | None = None
        best_window: int = 0

        for model, window in self.MODEL_WINDOWS.items():
            if model.lower() in exclude:
                continue
            if window >= required_tokens:
                if best_window == 0 or window < best_window:
                    best_model = model
                    best_window = window

        return best_model

    def register_window(self, model: str, window: int) -> None:
        """Register or update a model's context window dynamically.

        Args:
            model: Model identifier.
            window: Context window size in tokens.
        """
        self.MODEL_WINDOWS[model] = window
        self._windows_lower[model.lower()] = window
