"""Lost-in-the-Middle reordering for document/context placement.

Combats the well-documented "lost in the middle" phenomenon (Liu et al., 2023)
where LLMs attend poorly to content in the middle of the context window.

Strategy: interleave documents by importance so the most relevant items
appear at the beginning AND end of the context, where attention is strongest.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class LostInMiddleReorder:
    """Reorder documents to combat the LLM "lost in the middle" effect.

    Based on research by Liu et al. (2023) showing that transformer-based
    LLMs allocate attention most strongly to the beginning and end of context
    windows, with a significant drop in the middle positions.

    This implementation reorders a list of scored documents so that the most
    important ones are placed at the extremes, while less important ones
    fill the middle.

    Usage::

        reorder = LostInMiddleReorder()
        docs = [
            {"content": "...", "score": 0.95},
            {"content": "...", "score": 0.30},
        ]
        reordered = reorder.reorder(docs)
    """

    # Position-based attention weight estimates.
    # Based on empirical observations from the paper: attention is highest
    # at the first 20% and last 10% of context.
    ATTENTION_PEAK_BEGIN: float = 0.20  # First 20% gets peak attention
    ATTENTION_PEAK_END: float = 0.10    # Last 10% gets peak attention
    ATTENTION_VALLEY: float = 0.30      # Middle 40-70% gets lowest attention

    def __init__(self, score_key: str = "score") -> None:
        """Initialize the reorder.

        Args:
            score_key: Key in document dicts to use for relevance score (0.0-1.0).
        """
        self.score_key = score_key

    def reorder(self, documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Reorder documents to place important ones at extremes.

        Algorithm:
        1. Sort documents by score descending.
        2. Interleave: highest score to front, next to back, next to second-front, etc.
        3. This ensures relevance peaks at both ends of the context.

        Args:
            documents: List of document dicts, each with a score under `score_key`.

        Returns:
            Reordered document list (same length, different order).
        """
        if len(documents) <= 2:
            return list(documents)

        # Sort by score descending
        scored = sorted(
            documents,
            key=lambda d: d.get(self.score_key, 0.0),
            reverse=True,
        )

        # Interleave: front/back alternation
        front: list[dict[str, Any]] = []
        back: list[dict[str, Any]] = []

        for i, doc in enumerate(scored):
            if i % 2 == 0:
                front.append(doc)
            else:
                back.append(doc)

        # Back is built in descending order; reverse so that the higher-scored
        # items in back appear at the very end (last position gets attention too)
        back.reverse()

        return front + back

    def reorder_with_attention_weights(
        self,
        documents: list[dict[str, Any]],
    ) -> list[tuple[dict[str, Any], float]]:
        """Reorder documents and return position-aware attention weights.

        Each document gets an attention weight estimate based on its final
        position in the reordered list.

        Weight curve: Two peaks (beginning and end) with a U-shaped valley
        in the middle, modeled as:
            weight(pos) = max(peak_begin * exp(-k1 * pos), peak_end * exp(-k2 * (1-pos)))

        Args:
            documents: List of document dicts with score.

        Returns:
            List of (document, attention_weight) tuples.
        """
        if not documents:
            return []

        reordered = self.reorder(documents)

        result: list[tuple[dict[str, Any], float]] = []
        n = len(reordered)

        for i, doc in enumerate(reordered):
            position = i / max(n - 1, 1)

            # U-shaped attention: weighted combination of begin-peak and end-peak
            weight = self._attention_weight(position, n)
            result.append((doc, weight))

        return result

    def rank_by_position_advantage(
        self,
        documents: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Rank documents considering both relevance score and position advantage.

        A less relevant document placed at the beginning might get more
        attention than a more relevant one placed in the middle.

        Args:
            documents: List of document dicts with score.

        Returns:
            Documents sorted by effective relevance (score * position weight).
        """
        scored = self.reorder_with_attention_weights(documents)
        return [
            doc
            for doc, _ in sorted(
                scored,
                key=lambda x: x[0].get(self.score_key, 0.0) * x[1],
                reverse=True,
            )
        ]

    def get_estimated_attention_distribution(
        self,
        num_documents: int,
    ) -> list[float]:
        """Get estimated attention weights for each position without documents.

        Useful for understanding the attention curve before placing content.

        Args:
            num_documents: Number of documents to estimate for.

        Returns:
            List of attention weights, one per position.
        """
        if num_documents <= 0:
            return []

        weights: list[float] = []
        for i in range(num_documents):
            position = i / max(num_documents - 1, 1)
            weight = self._attention_weight(position, num_documents)
            weights.append(weight)

        return weights

    def _attention_weight(self, position: float, total_count: int) -> float:
        """Estimate attention weight for a position using dual-exponential model.

        Models attention as a U-shaped curve with peaks at the beginning and end.
        Uses two declining exponentials:
        - Forward: attention from the beginning (strong at pos=0, weak at pos=1)
        - Backward: attention from the end (weak at pos=0, strong at pos=1)

        Args:
            position: Normalized position (0.0 = first, 1.0 = last).
            total_count: Total number of documents.

        Returns:
            Estimated attention weight (0.0 to 1.0).
        """
        import math

        # Sharpness of attention decay
        k_forward = 3.0   # Forward peak decay rate
        k_backward = 5.0  # Backward peak decay rate (steeper near end)

        # Forward attention (strong at start)
        forward = self.ATTENTION_PEAK_BEGIN * math.exp(-k_forward * position)

        # Backward attention (strong at end)
        backward = self.ATTENTION_PEAK_END * math.exp(-k_backward * (1.0 - position))

        # Combine: max of the two peaks
        weight = max(forward, backward)

        # Small constant baseline attention everywhere
        baseline = 0.05
        weight = max(weight, baseline)

        # Normalize to 0.0-1.0 range
        return min(weight, 1.0)
