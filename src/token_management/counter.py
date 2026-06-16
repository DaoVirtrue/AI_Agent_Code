"""Unified token counter with three-level fallback strategy."""

from __future__ import annotations

import re
from typing import Any

from src.token_management.encoders.huggingface_encoder import HuggingFaceEncoder
from src.token_management.encoders.sentencepiece_encoder import SentencePieceEncoder
from src.token_management.encoders.tiktoken_encoder import TiktokenEncoder


class TokenCounter:
    """Unified token counter with 3-level fallback.

    Resolution order:
        1. Tiktoken (OpenAI / Anthropic models)
        2. SentencePiece (Llama / Mistral / Qwen models)
        3. HuggingFace AutoTokenizer (any HF model)
        4. Character-based heuristic estimate (last resort)
    """

    # CJK Unicode ranges
    _CJK_PATTERN: re.Pattern[str] = re.compile(
        r"[⺀-⻿　-〿㇀-㇯㈀-㋿"
        r"㌀-㏿㐀-䶿一-鿿豈-﫿"
        r"︰-﹏＀-￯ 0-⩭F⩰0-⭳F"
        r"⭴0-⮁F⮂0-⳪F⾀0-⾡F]"
    )

    # Token-per-character ratios
    CJK_CHARS_PER_TOKEN: float = 1.5
    LATIN_CHARS_PER_TOKEN: float = 4.0

    def __init__(self) -> None:
        self.tiktoken = TiktokenEncoder()
        self.sentencepiece = SentencePieceEncoder()
        self.huggingface = HuggingFaceEncoder()

    def count(self, text: str, model: str = "gpt-4o") -> int:
        """Count tokens with automatic encoder selection.

        Args:
            text: Input text to count tokens for.
            model: Model identifier (default: "gpt-4o").

        Returns:
            Token count as integer.
        """
        if not text:
            return 0

        # Level 1: Tiktoken
        if self.tiktoken.supports_model(model):
            try:
                return self.tiktoken.count(text, model)
            except Exception:
                pass

        # Level 2: SentencePiece
        if self.sentencepiece.supports_model(model):
            try:
                return self.sentencepiece.count(text, model)
            except Exception:
                pass

        # Level 3: HuggingFace (attempt if model looks like a HF path)
        if "/" in model:
            try:
                return self.huggingface.count(text, model)
            except Exception:
                pass

        # Level 4: Heuristic estimate
        return self._estimate(text)

    def count_messages(self, messages: list[dict[str, Any]], model: str = "gpt-4o") -> int:
        """Count tokens for a full messages array.

        Args:
            messages: List of message dicts.
            model: Model identifier.

        Returns:
            Total token count.
        """
        if not messages:
            return 0

        # Level 1: Tiktoken with format overhead
        if self.tiktoken.supports_model(model):
            try:
                return self.tiktoken.count_messages(messages, model)
            except Exception:
                pass

        # Level 2: SentencePiece
        if self.sentencepiece.supports_model(model):
            try:
                return self.sentencepiece.count_messages(messages, model)
            except Exception:
                pass

        # Level 3: HuggingFace
        if "/" in model:
            try:
                return self.huggingface.count_messages(messages, model)
            except Exception:
                pass

        # Level 4: Sum individual content estimates
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += self._estimate(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict):
                        text = part.get("text", "") if part.get("type") == "text" else ""
                        total += self._estimate(text)
                    elif isinstance(part, str):
                        total += self._estimate(part)
            else:
                total += self._estimate(str(content))
        return total

    def _estimate(self, text: str) -> int:
        """Character-based heuristic token estimation.

        CJK characters: ~1.5 characters per token (dense meaning per char).
        Latin/other characters: ~4.0 characters per token.

        Formula: int(cjk_chars / 1.5 + latin_chars / 4.0)

        Args:
            text: Input text.

        Returns:
            Estimated token count (minimum 1 for non-empty text).
        """
        if not text:
            return 0

        cjk_chars = len(self._CJK_PATTERN.findall(text))
        latin_chars = len(text) - cjk_chars

        estimate = int(cjk_chars / self.CJK_CHARS_PER_TOKEN + latin_chars / self.LATIN_CHARS_PER_TOKEN)
        return max(1, estimate)

    def estimate_for_model(self, text: str, model: str) -> tuple[int, str]:
        """Count tokens and return which encoder was used.

        Args:
            text: Input text.
            model: Model identifier.

        Returns:
            Tuple of (token_count, encoder_name_used).
        """
        if not text:
            return 0, "none"

        if self.tiktoken.supports_model(model):
            try:
                return self.tiktoken.count(text, model), "tiktoken"
            except Exception:
                pass

        if self.sentencepiece.supports_model(model):
            try:
                return self.sentencepiece.count(text, model), "sentencepiece"
            except Exception:
                pass

        if "/" in model:
            try:
                return self.huggingface.count(text, model), "huggingface"
            except Exception:
                pass

        return self._estimate(text), "heuristic"
