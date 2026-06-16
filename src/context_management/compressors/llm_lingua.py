"""LLMLingua-based prompt compression.

Token-level compression that removes low-information tokens from prompts
using a small distilled model. Achieves 3-5x compression while preserving
semantic meaning for downstream LLM consumption.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


class LLMLinguaCompressor:
    """Token-level prompt compression using LLMLingua-2.

    LLMLingua-2 is a BERT-based model fine-tuned for prompt compression.
    It identifies and removes low-information tokens that contribute
    minimally to downstream task performance, achieving 3-5x compression.

    If the llmlingua package is not available, falls back to a rule-based
    compression that removes:
    - Filler phrases ("you know", "kind of", etc.)
    - Redundant whitespace
    - Non-essential punctuation
    - Long repeated patterns

    Usage::

        compressor = LLMLinguaCompressor()
        compressed = await compressor.compress(long_prompt, target_ratio=0.3)
    """

    # Default model for LLMLingua-2
    DEFAULT_MODEL: str = "microsoft/llmlingua-2-bert-base"

    # Filler phrases to remove (rule-based fallback)
    FILLER_PATTERNS: list[re.Pattern[str]] = [
        re.compile(r"\b(you know|kind of|sort of|I mean|like|basically|actually|literally|just|really|very)\b", re.IGNORECASE),
        re.compile(r"\b(um|uh|er|ah|hmm)\b", re.IGNORECASE),
        re.compile(r"\b(in order to|in terms of|the fact that|it is important to note that)\b", re.IGNORECASE),
        re.compile(r"\b(as a matter of fact|at the end of the day|needless to say)\b", re.IGNORECASE),
    ]

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        device: str = "cpu",
    ) -> None:
        """Initialize the compressor.

        Args:
            model_name: HuggingFace model for LLMLingua-2.
            device: Device for inference ('cpu', 'cuda', 'mps').
        """
        self.model_name = model_name
        self.device = device
        self._model: Any = None
        self._llmlingua_available: bool | None = None
        self._sentence_boundary: re.Pattern[str] = re.compile(
            r"(?<=[.!?。！？\n])\s+"
        )

    async def compress(
        self,
        prompt: str,
        target_ratio: float = 0.3,
    ) -> str:
        """Compress a prompt to the target ratio.

        Args:
            prompt: The prompt text to compress.
            target_ratio: Target compression ratio (0.3 = keep 30% of tokens,
                i.e. 3.3x compression). Clamped to 0.1-0.9.

        Returns:
            Compressed prompt string.
        """
        if not prompt:
            return ""

        # Clamp ratio
        target_ratio = max(0.1, min(0.9, target_ratio))

        # Try LLMLingua-2 model first
        if await self._ensure_llmlingua():
            try:
                return await self._compress_with_llmlingua(prompt, target_ratio)
            except Exception as exc:
                logger.warning(
                    "LLMLingua compression failed: %s. Using rule-based fallback.",
                    exc,
                )

        # Rule-based fallback
        return self._compress_rule_based(prompt, target_ratio)

    def estimate_compression_ratio(self, original: str, compressed: str) -> float:
        """Calculate actual compression ratio achieved.

        Args:
            original: Original prompt text.
            compressed: Compressed prompt text.

        Returns:
            Compression ratio (e.g., 3.0 = 3x smaller).
        """
        if not compressed:
            return 1.0

        # Use character count as proxy
        orig_chars = len(original)
        comp_chars = len(compressed)

        if comp_chars == 0:
            return float("inf")

        # Token count estimate (~4 chars per token)
        orig_tokens = max(1, orig_chars // 4)
        comp_tokens = max(1, comp_chars // 4)

        return round(orig_tokens / comp_tokens, 2)

    async def compress_to_tokens(
        self,
        prompt: str,
        max_tokens: int,
    ) -> str:
        """Compress prompt to fit within a specified token budget.

        Args:
            prompt: Prompt text to compress.
            max_tokens: Maximum token budget.

        Returns:
            Compressed prompt.
        """
        if not prompt:
            return ""

        # Estimate current token count
        estimated_tokens = len(prompt) // 4
        if estimated_tokens <= max_tokens:
            return prompt

        target_ratio = max_tokens / estimated_tokens
        return await self.compress(prompt, target_ratio)

    async def _ensure_llmlingua(self) -> bool:
        """Check and lazily load the LLMLingua model."""
        if self._llmlingua_available is not None:
            return self._llmlingua_available

        try:
            from llmlingua import PromptCompressor  # type: ignore[import-untyped]

            self._model = PromptCompressor(
                model_name=self.model_name,
                use_llmlingua2=True,
                device_map=self.device,
            )
            self._llmlingua_available = True
            logger.info("LLMLingua-2 model loaded: %s", self.model_name)
            return True
        except ImportError:
            logger.warning(
                "llmlingua package not installed. "
                "Install with: pip install llmlingua "
                "Using rule-based fallback compression."
            )
            self._llmlingua_available = False
            return False
        except Exception as exc:
            logger.warning(
                "LLMLingua model loading failed: %s. Using rule-based fallback.",
                exc,
            )
            self._llmlingua_available = False
            return False

    async def _compress_with_llmlingua(self, prompt: str, target_ratio: float) -> str:
        """Use LLMLingua-2 model for compression."""
        if self._model is None:
            raise RuntimeError("LLMLingua model not loaded")

        compressed = self._model.compress_prompt(
            prompt,
            rate=target_ratio,
            force_tokens=[
                "!", "?", ".", ",", "\n", ":", ";",
            ],
            chunk_end_tokens=[".", "!", "?", "\n"],
            return_word_label=False,
            drop_consecutive=True,
        )

        if isinstance(compressed, dict):
            return compressed.get("compressed_prompt", prompt)
        return str(compressed) if compressed else prompt

    def _compress_rule_based(self, prompt: str, target_ratio: float) -> str:
        """Rule-based fallback compression.

        Removes:
        1. Filler words and phrases
        2. Redundant whitespace
        3. Sentences by keeping highest-density ones
        """
        text = prompt

        # Remove filler phrases
        for pattern in self.FILLER_PATTERNS:
            text = pattern.sub("", text)

        # Collapse whitespace
        text = re.sub(r"\s+", " ", text)

        # Split into sentences
        sentences = self._sentence_boundary.split(text)
        sentences = [s.strip() for s in sentences if s.strip()]

        if len(sentences) <= 1:
            return text.strip()

        # Keep top N% sentences ranked by information density
        num_to_keep = max(1, int(len(sentences) * target_ratio))

        # Score sentences by "information density":
        # - Longer sentences with more unique words likely carry more info
        # - Penalize very short sentences
        scored = []
        for sent in sentences:
            words = sent.split()
            if not words:
                scored.append((sent, -1.0))
                continue

            unique_ratio = len(set(words)) / len(words) if words else 0
            length_score = min(len(words) / 20.0, 1.0)  # Cap at 20 words

            # Combine scores
            info_score = unique_ratio * 0.6 + length_score * 0.4
            scored.append((sent, info_score))

        # Sort by score descending, keep top N
        scored.sort(key=lambda x: x[1], reverse=True)
        kept = [sent for sent, _ in scored[:num_to_keep]]

        # Preserve original sentence order
        kept_set = set(kept)
        ordered = [s for s in sentences if s in kept_set]

        return " ".join(ordered).strip()

    def get_compression_info(
        self,
        original: str,
        compressed: str,
    ) -> dict[str, Any]:
        """Get detailed compression statistics.

        Args:
            original: Original text.
            compressed: Compressed text.

        Returns:
            Dict with compression stats.
        """
        orig_words = len(original.split())
        comp_words = len(compressed.split())
        orig_chars = len(original)
        comp_chars = len(compressed)

        return {
            "original_chars": orig_chars,
            "compressed_chars": comp_chars,
            "original_words": orig_words,
            "compressed_words": comp_words,
            "char_ratio": round(comp_chars / orig_chars, 3) if orig_chars > 0 else 1.0,
            "word_ratio": round(comp_words / orig_words, 3) if orig_words > 0 else 1.0,
            "estimated_token_ratio": self.estimate_compression_ratio(original, compressed),
            "method": "llmlingua" if self._llmlingua_available else "rule-based",
        }
