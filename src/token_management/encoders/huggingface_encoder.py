"""HuggingFace AutoTokenizer-based encoder for any HF model."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class HuggingFaceEncoder:
    """Token counting using HuggingFace AutoTokenizer for arbitrary models.

    This is the most general encoder but also the slowest due to tokenizer
    loading. Use as a fallback when tiktoken and sentencepiece cannot handle
    the model.
    """

    def __init__(self) -> None:
        self._tokenizer_cache: dict[str, Any] = {}

    def _get_tokenizer(self, model_name: str) -> Any:
        """Lazily load and cache a HuggingFace tokenizer."""
        if model_name not in self._tokenizer_cache:
            try:
                from transformers import AutoTokenizer  # type: ignore[import-untyped]

                self._tokenizer_cache[model_name] = AutoTokenizer.from_pretrained(
                    model_name,
                    trust_remote_code=True,
                )
            except Exception as exc:
                logger.error(
                    "Failed to load tokenizer for '%s': %s",
                    model_name,
                    exc,
                )
                raise RuntimeError(
                    f"Could not load HuggingFace tokenizer for {model_name}"
                ) from exc

        return self._tokenizer_cache[model_name]

    def count(self, text: str, model_name: str) -> int:
        """Count tokens using the model's HuggingFace tokenizer.

        Args:
            text: Input text to tokenize.
            model_name: HF model identifier (e.g. "google/gemma-2b").

        Returns:
            Integer token count.
        """
        if not text:
            return 0
        tokenizer = self._get_tokenizer(model_name)
        tokens = tokenizer.encode(text)
        return len(tokens)

    def count_messages(self, messages: list[dict[str, Any]], model_name: str) -> int:
        """Count tokens for a messages array using the chat template.

        Uses the tokenizer's apply_chat_template if available, otherwise
        falls back to manual token counting.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            model_name: HF model identifier.

        Returns:
            Total token count.
        """
        tokenizer = self._get_tokenizer(model_name)

        if hasattr(tokenizer, "apply_chat_template") and tokenizer.chat_template:
            try:
                formatted = tokenizer.apply_chat_template(
                    messages,
                    tokenize=True,
                    add_generation_prompt=True,
                )
                return len(formatted) if isinstance(formatted, list) else 0
            except Exception:
                logger.warning(
                    "apply_chat_template failed for %s, falling back to manual count",
                    model_name,
                )

        # Manual fallback: encode each message individually
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            role = msg.get("role", "user")

            if isinstance(content, str):
                total += len(tokenizer.encode(content))
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        total += len(tokenizer.encode(part.get("text", "")))
                    elif isinstance(part, str):
                        total += len(tokenizer.encode(part))
            else:
                total += len(tokenizer.encode(str(content)))

        return total

    def supports_model(self, model_name: str) -> bool:
        """HuggingFace encoder can attempt any model name."""
        return True

    def clear_cache(self) -> None:
        """Release all cached tokenizers to free memory."""
        self._tokenizer_cache.clear()
