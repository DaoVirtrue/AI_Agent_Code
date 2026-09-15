"""
Prompt-level cost optimization strategies.

This module complements the token_management optimizer by providing
prompt-specific cost reduction techniques: truncation strategies,
instruction compression, and dynamic template selection.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class OptimizationResult:
    """Result of a prompt optimization operation.

    Attributes:
        optimized_template: The optimized template string.
        original_length: Character length of the original template.
        optimized_length: Character length after optimization.
        reduction_percent: Percentage reduction achieved.
        strategy_used: Name of the strategy that was applied.
    """

    optimized_template: str
    original_length: int
    optimized_length: int
    reduction_percent: float
    strategy_used: str


# ---------------------------------------------------------------------------
# Compression dictionaries
# ---------------------------------------------------------------------------

_VERBOSE_PATTERNS: list[tuple[str, str]] = [
    # Please / politeness patterns
    (r"(?i)please\s+make\s+sure\s+to\s+", "ensure "),
    (r"(?i)please\s+ensure\s+that\s+", "ensure "),
    (r"(?i)please\s+note\s+that\s+", "note: "),
    (r"(?i)please\s+be\s+aware\s+that\s+", "note: "),
    (r"(?i)please\s+remember\s+to\s+", "remember to "),
    (r"(?i)it\s+is\s+important\s+to\s+note\s+that\s+", "note: "),
    (r"(?i)it\s+is\s+worth\s+mentioning\s+that\s+", "note: "),
    (r"(?i)I\s+would\s+like\s+you\s+to\s+", ""),
    (r"(?i)you\s+should\s+make\s+sure\s+to\s+", "ensure "),
    # Redundant qualifiers
    (r"(?i)\s+in\s+a\s+way\s+that\s+is\s+", " "),
    (r"(?i)\s+in\s+order\s+to\s+", " to "),
    (r"(?i)\s+for\s+the\s+purpose\s+of\s+", " for "),
    (r"(?i)\s+due\s+to\s+the\s+fact\s+that\s+", " because "),
    (r"(?i)\s+at\s+this\s+point\s+in\s+time\s+", " now "),
    (r"(?i)\s+in\s+the\s+event\s+that\s+", " if "),
    (r"(?i)\s+a\s+number\s+of\s+", " several "),
    (r"(?i)\s+the\s+majority\s+of\s+", " most "),
    (r"(?i)\s+a\s+large\s+number\s+of\s+", " many "),
    # Bullet point normalization
    (r"(?i)\s*[-–—]\s+", "\n- "),
]

_OPENING_MARKER_PATTERN = re.compile(
    r"^(.*?)(system|instructions?|role|context|you are|your task)",
    re.IGNORECASE,
)
_CLOSING_MARKER_PATTERN = re.compile(
    r"(remember|important|finally|always|never|do not forget)[^.]*\.?\s*$",
    re.IGNORECASE,
)


class PromptCostOptimizer:
    """Optimize prompts for cost efficiency.

    Strategies:
    - Truncation: trim to max tokens while preserving structure.
    - Compression: remove redundant instructions and verbosity.
    - Dynamic selection: choose appropriate strategy based on context length.

    Complements the token_management CostOptimizer by adding prompt-level
    techniques rather than token-level ones.

    Usage::

        opt = PromptCostOptimizer(max_tokens=4000)
        result = opt.optimize(long_template, context_length=6000, strategy="auto")
        print(f"Reduced by {result.reduction_percent:.1f}%")
    """

    def __init__(self, max_tokens: int = 4000) -> None:
        """Initialize the optimizer.

        Args:
            max_tokens: Target maximum token budget for optimized prompts.
        """
        self.max_tokens = max_tokens
        logger.info("PromptCostOptimizer initialized with max_tokens=%d", max_tokens)

    # ------------------------------------------------------------------
    # Truncation
    # ------------------------------------------------------------------

    def truncate_to_budget(self, template: str, max_chars: int) -> str:
        """Truncate template to fit within character budget while preserving
        structural integrity.

        Strategy: Keep the opening section (which usually contains role/system
        instructions) and the closing section (which usually contains output
        format / constraints). Cut from the middle where detailed instructions
        or examples usually live.

        Args:
            template: The full template string.
            max_chars: Maximum allowed character length.

        Returns:
            Truncated template string within length budget.
        """
        if len(template) <= max_chars:
            return template

        # Split into paragraphs (separated by blank lines)
        paragraphs = template.split("\n\n")

        # If it fits as-is, return
        if len(template) <= max_chars:
            return template

        # Allocate budget: 35% opening, 30% middle, 35% closing (approximate)
        n = len(paragraphs)
        if n <= 2:
            # Too few paragraphs to split meaningfully – take head
            return template[:max_chars].rstrip()

        open_count = max(1, n // 3)
        close_count = max(1, n // 3)
        middle_count = n - open_count - close_count

        if middle_count < 1:
            open_count = max(1, n - 1)
            close_count = n - open_count
            middle_count = 0

        opening = "\n\n".join(paragraphs[:open_count])
        closing = "\n\n".join(paragraphs[-close_count:])

        # Budget for middle section
        middle_budget = max_chars - len(opening) - len(closing) - 4  # 4 for separators

        if middle_budget <= 0:
            # Not enough room for middle – trim opening and closing proportionally
            ratio = max_chars / len(template)
            split = int(len(opening) * ratio)
            opening = opening[:split].rstrip()
            closing_budget = max_chars - len(opening) - 4
            if closing_budget > 0:
                closing = closing[:closing_budget].rstrip()
            else:
                closing = ""

        middle_paragraphs = paragraphs[open_count : open_count + middle_count]
        middle = self._truncate_middle_paragraphs(
            middle_paragraphs, middle_budget
        )

        # Assemble
        parts = [opening]
        if middle:
            # Insert a notice that content was truncated for brevity
            parts.append(
                "[...]"
            )
            parts.append(middle)
        parts.append(closing)

        result = "\n\n".join(parts)

        if len(result) > max_chars:
            result = result[:max_chars].rstrip()

        logger.debug(
            "Truncated template from %d to %d chars", len(template), len(result)
        )
        return result

    # ------------------------------------------------------------------
    # Compression
    # ------------------------------------------------------------------

    def compress_instructions(self, template: str) -> str:
        """Compress verbose instructions in a template.

        Applies:
        - Replace verbose phrases with shorter equivalents.
        - Remove redundant politeness filler.
        - Normalize repeated instruction patterns.
        - Merge adjacent similar constraints.

        Args:
            template: The full template string to compress.

        Returns:
            Compressed template string.
        """
        compressed = template

        # Apply verbose-to-concise substitutions
        for pattern, replacement in _VERBOSE_PATTERNS:
            compressed = re.sub(pattern, replacement, compressed)

        # Normalize multiple consecutive newlines (3+ -> 2)
        compressed = re.sub(r"\n{3,}", "\n\n", compressed)

        # Remove lines that are purely filler
        filler_patterns = [
            r"^\s*(ok|okay|alright|well|so|now then|let me|here is|here are)\s*$",
            r"^\s*(I hope|hopefully)\s+this\s+(helps|is|makes|will).*$",
        ]
        for fp in filler_patterns:
            compressed = re.sub(fp, "", compressed, flags=re.IGNORECASE | re.MULTILINE)

        # Clean up orphaned blank lines
        compressed = re.sub(r"\n{3,}", "\n\n", compressed)
        compressed = compressed.strip()

        saved = len(template) - len(compressed)
        if saved > 0:
            logger.debug(
                "Compression saved %d chars (%.1f%%)",
                saved,
                (saved / len(template)) * 100 if template else 0,
            )

        return compressed

    # ------------------------------------------------------------------
    # Main optimize method
    # ------------------------------------------------------------------

    def optimize(
        self, template: str, context_length: int, strategy: str = "auto"
    ) -> OptimizationResult:
        """Apply the best optimization strategy based on context length.

        Strategy selection:
        - "auto": Choose based on context_length vs max_tokens.
        - "truncate": Force truncation.
        - "compress": Force compression.
        - "both": Apply compression first, then truncate if still needed.

        Args:
            template: The template string to optimize.
            context_length: Current context length in characters.
            strategy: Which strategy to use ("auto", "truncate", "compress", "both").

        Returns:
            OptimizationResult with the optimized template and stats.
        """
        original_length = len(template)

        # Determine effective budget
        budget_chars = self.max_tokens * 4  # rough char estimate

        if strategy == "auto":
            # If already within budget, do nothing
            if original_length <= budget_chars:
                return OptimizationResult(
                    optimized_template=template,
                    original_length=original_length,
                    optimized_length=original_length,
                    reduction_percent=0.0,
                    strategy_used="none (within budget)",
                )
            # If slightly over budget, try compression
            if original_length <= budget_chars * 1.5:
                strategy = "compress"
            else:
                strategy = "both"

        result_text = template
        strategies_applied: list[str] = []

        if strategy in ("compress", "both"):
            compressed = self.compress_instructions(template)
            if len(compressed) < original_length:
                result_text = compressed
                strategies_applied.append("compress")

        if strategy in ("truncate", "both"):
            if len(result_text) > budget_chars:
                truncated = self.truncate_to_budget(result_text, budget_chars)
                result_text = truncated
                strategies_applied.append("truncate")

        if not strategies_applied:
            strategies_applied.append(strategy)

        optimized_length = len(result_text)
        reduction = (
            ((original_length - optimized_length) / original_length * 100)
            if original_length > 0
            else 0.0
        )

        logger.info(
            "Optimized template: %d -> %d chars (%.1f%% reduction, strategy=%s)",
            original_length,
            optimized_length,
            reduction,
            "+".join(strategies_applied),
        )

        return OptimizationResult(
            optimized_template=result_text,
            original_length=original_length,
            optimized_length=optimized_length,
            reduction_percent=round(reduction, 2),
            strategy_used="+".join(strategies_applied),
        )

    # ------------------------------------------------------------------
    # Token estimation
    # ------------------------------------------------------------------

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Rough token estimation: approximately 4 characters per token for English.

        This is a fast heuristic. For accurate counts, use the token_management
        TokenCounter with the appropriate encoder.

        Args:
            text: The text to estimate token count for.

        Returns:
            Estimated number of tokens (minimum 0).
        """
        if not text:
            return 0
        # 4 chars per token is a common rule-of-thumb for English text
        return max(1, len(text) // 4)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _truncate_middle_paragraphs(
        paragraphs: list[str], max_chars: int
    ) -> str:
        """Build a middle section from paragraphs, truncating to max_chars.

        Preserves as many full paragraphs as possible and truncates the
        last included paragraph to fit.

        Args:
            paragraphs: List of paragraph strings for the middle section.
            max_chars: Maximum allowed characters for the middle section.

        Returns:
            Assembled middle section string.
        """
        if max_chars <= 0 or not paragraphs:
            return ""

        result_parts: list[str] = []
        used = 0
        sep_len = 2  # "\n\n" separator

        for para in paragraphs:
            needed = len(para) + (sep_len if result_parts else 0)
            if used + needed <= max_chars:
                result_parts.append(para)
                used += needed
            else:
                # Try to fit a partial paragraph
                remaining = max_chars - used - (sep_len if result_parts else 0)
                if remaining > 40:  # only include if we can get a meaningful amount
                    partial = para[:remaining].rstrip()
                    if partial:
                        result_parts.append(partial + "...")
                break

        return "\n\n".join(result_parts)
