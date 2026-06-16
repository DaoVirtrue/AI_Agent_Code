"""Tiktoken-based token encoder for OpenAI and Anthropic models."""

from __future__ import annotations

import logging
from typing import Any

import tiktoken

logger = logging.getLogger(__name__)


class TiktokenEncoder:
    """Token counting via tiktoken for OpenAI and compatible models.

    Supports GPT-4o, GPT-4, GPT-3.5, Claude 3/4 (via cl100k_base), and
    any model listed in ENCODING_MAP. Falls back to cl100k_base for
    unknown model names.
    """

    ENCODING_MAP: dict[str, str] = {
        "gpt-4o": "o200k_base",
        "gpt-4o-mini": "o200k_base",
        "gpt-4": "cl100k_base",
        "gpt-4-32k": "cl100k_base",
        "gpt-3.5-turbo": "cl100k_base",
        "gpt-3.5-turbo-16k": "cl100k_base",
        "gpt-3.5-turbo-instruct": "cl100k_base",
        "claude-3-opus": "cl100k_base",
        "claude-3-sonnet": "cl100k_base",
        "claude-3-haiku": "cl100k_base",
        "claude-sonnet-4": "cl100k_base",
        "claude-opus-4": "cl100k_base",
        "claude-3.5-haiku": "cl100k_base",
        "text-embedding-3-small": "cl100k_base",
        "text-embedding-3-large": "cl100k_base",
        "text-embedding-ada-002": "cl100k_base",
    }

    # Per-message overhead tokens (OpenAI convention)
    MESSAGE_OVERHEAD: int = 4

    # Priming token overhead per conversation
    PRIMING_OVERHEAD: int = 2

    def __init__(self) -> None:
        self._encoding_cache: dict[str, tiktoken.Encoding] = {}

    def _get_encoding(self, model: str) -> tiktoken.Encoding:
        """Resolve and cache the tiktoken encoding for a model."""
        encoding_name = self.ENCODING_MAP.get(
            model,
            self._fallback_encoding_name(model),
        )

        if encoding_name not in self._encoding_cache:
            try:
                self._encoding_cache[encoding_name] = tiktoken.get_encoding(encoding_name)
            except Exception:
                logger.warning(
                    "Failed to load encoding '%s' for model '%s', falling back to cl100k_base",
                    encoding_name,
                    model,
                )
                encoding_name = "cl100k_base"
                self._encoding_cache[encoding_name] = tiktoken.get_encoding(encoding_name)

        return self._encoding_cache[encoding_name]

    def _fallback_encoding_name(self, model: str) -> str:
        """Guess encoding name when model is not in ENCODING_MAP."""
        if model.startswith("gpt-4o"):
            return "o200k_base"
        if model.startswith("gpt-4") or model.startswith("gpt-3"):
            return "cl100k_base"
        if model.startswith("claude"):
            return "cl100k_base"
        return "cl100k_base"

    def count(self, text: str, model: str) -> int:
        """Count tokens in a single text string for the given model.

        Args:
            text: The text to count tokens for.
            model: Model identifier (e.g. "gpt-4o", "claude-sonnet-4").

        Returns:
            Integer token count.
        """
        if not text:
            return 0
        encoding = self._get_encoding(model)
        return len(encoding.encode(text))

    def count_messages(self, messages: list[dict[str, Any]], model: str) -> int:
        """Count tokens for a full messages array using OpenAI's formula.

        Each message costs MESSAGE_OVERHEAD tokens, and the conversation
        has a PRIMING_OVERHEAD. Content tokens are computed per-message.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            model: Model identifier.

        Returns:
            Total token count for the conversation.
        """
        encoding = self._get_encoding(model)
        total = 0

        for msg in messages:
            total += self.MESSAGE_OVERHEAD
            content = msg.get("content", "")
            role = msg.get("role", "user")

            if isinstance(content, str):
                total += len(encoding.encode(content))
            elif isinstance(content, list):
                # Handle multimodal content arrays
                for part in content:
                    if isinstance(part, dict):
                        if part.get("type") == "text":
                            total += len(encoding.encode(part.get("text", "")))
                        elif part.get("type") == "image_url":
                            # Image tokens estimated at ~85 for low-res, more for detail
                            detail = part.get("image_url", {}).get("detail", "auto")
                            if detail == "high":
                                total += 765
                            else:
                                total += 85
                    elif isinstance(part, str):
                        total += len(encoding.encode(part))
            else:
                total += len(encoding.encode(str(content)))

            # Add role-specific tokens
            if role == "system":
                total += 0  # Already counted in overhead
            elif role == "function" or role == "tool":
                total += 0

        # Every reply is primed with <|start|>assistant<|message|>
        total += self.PRIMING_OVERHEAD

        return total

    def supports_model(self, model: str) -> bool:
        """Check whether this encoder can handle the given model."""
        return model in self.ENCODING_MAP or any(
            model.startswith(prefix) for prefix in ("gpt-4o", "gpt-4", "gpt-3", "claude")
        )
