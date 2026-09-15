"""Result fusion algorithms for combining multiple retrieval sources."""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class RRFFusion:
    """Reciprocal Rank Fusion for combining ranked lists.

    RRF is a simple but effective algorithm for merging ranked results
    from multiple retrieval systems. Unlike score-based fusion, it only
    considers rank positions, making it robust to different score scales.

    RRF score = sum over retrievers of (1 / (k + rank_i))

    Where k is a constant (typically 60) that controls rank decay.
    """

    def __init__(self, k: int = 60):
        """Initialize RRF fusion.

        Args:
            k: Rank decay constant. Higher k = flatter scores.
               Typical values: 60 (standard), 30 (faster decay), 100 (flatter)
        """
        self.k = k
        logger.info("RRFFusion initialized with k=%d", k)

    def fuse(
        self,
        *result_lists: list[dict],
        weights: Optional[tuple[float, ...]] = None,
    ) -> list[dict]:
        """Fuse multiple ranked result lists using RRF.

        Args:
            *result_lists: Variable number of result lists, each a list of
                          {id, content, score, metadata} dicts
            weights: Optional weights for each result list. Must match number
                    of lists. If None, all weighted equally.

        Returns:
            Single fused and ranked list of dicts
        """
        if not result_lists:
            return []

        # Default to equal weights
        if weights is None:
            weights = tuple(1.0 for _ in result_lists)

        if len(weights) != len(result_lists):
            raise ValueError(
                f"Number of weights ({len(weights)}) must match number of result lists ({len(result_lists)})"
            )

        # Compute RRF scores
        doc_scores: dict[str, float] = {}
        doc_map: dict[str, dict] = {}
        doc_ranks: dict[str, dict[int, int]] = {}  # doc_id -> {list_idx: rank}

        for list_idx, docs in enumerate(result_lists):
            weight = weights[list_idx]

            for rank, doc in enumerate(docs):
                doc_id = doc.get("id", f"unknown_{list_idx}_{rank}")

                # RRF contribution
                rrf_contrib = weight / (self.k + rank + 1)
                doc_scores[doc_id] = doc_scores.get(doc_id, 0.0) + rrf_contrib

                # Store document (keep highest-scoring version)
                if doc_id not in doc_map:
                    doc_map[doc_id] = doc.copy()
                    doc_map[doc_id]["rrf_score"] = 0.0

                # Track ranks from each retriever
                if doc_id not in doc_ranks:
                    doc_ranks[doc_id] = {}
                doc_ranks[doc_id][list_idx] = rank + 1

        # Sort by RRF score descending
        sorted_ids = sorted(doc_scores.keys(), key=lambda x: doc_scores[x], reverse=True)

        # Build result
        fused = []
        for doc_id in sorted_ids:
            doc = doc_map[doc_id].copy()
            doc["rrf_score"] = doc_scores[doc_id]
            doc["ranks"] = doc_ranks.get(doc_id, {})
            doc["fusion_method"] = "rrf"
            fused.append(doc)

        logger.debug("RRF fusion: %d lists -> %d unique documents",
                      len(result_lists), len(fused))

        return fused

    def weighted_fuse(
        self,
        dense_results: list[dict],
        sparse_results: list[dict],
        alpha: float = 0.5,
    ) -> list[dict]:
        """Convenience method for weighted dense+sparse fusion.

        Args:
            dense_results: Dense retrieval results
            sparse_results: Sparse retrieval results
            alpha: Weight of dense results (0-1). 0=all sparse, 1=all dense

        Returns:
            Fused ranked list
        """
        return self.fuse(dense_results, sparse_results, weights=(alpha, 1.0 - alpha))

    def score_fusion(
        self,
        *result_lists: list[dict],
        method: str = "normalized_sum",
    ) -> list[dict]:
        """Fuse results by combining normalized scores (alternative to RRF).

        Args:
            *result_lists: Result lists to fuse
            method: "normalized_sum", "max", or "reciprocal"

        Returns:
            Fused ranked list
        """
        if not result_lists:
            return []

        doc_scores: dict[str, float] = {}
        doc_map: dict[str, dict] = {}

        for docs in result_lists:
            if not docs:
                continue

            # Normalize scores within each list
            max_score = max(doc.get("score", 0.0) for doc in docs) if docs else 1.0

            for doc in docs:
                doc_id = doc.get("id", str(hash(doc.get("content", ""))))
                norm_score = doc.get("score", 0.0) / max_score if max_score > 0 else 0.0

                if doc_id not in doc_map:
                    doc_map[doc_id] = doc.copy()
                    doc_map[doc_id]["score"] = 0.0

                if method == "normalized_sum":
                    doc_scores[doc_id] = doc_scores.get(doc_id, 0.0) + norm_score
                elif method == "max":
                    doc_scores[doc_id] = max(doc_scores.get(doc_id, 0.0), norm_score)
                elif method == "reciprocal":
                    doc_scores[doc_id] = doc_scores.get(doc_id, 0.0) + norm_score
                else:
                    doc_scores[doc_id] = doc_scores.get(doc_id, 0.0) + norm_score

        # Sort and return
        sorted_ids = sorted(doc_scores.keys(), key=lambda x: doc_scores[x], reverse=True)
        fused = []
        for doc_id in sorted_ids:
            doc = doc_map[doc_id].copy()
            doc["score"] = doc_scores[doc_id]
            doc["fusion_method"] = f"score_{method}"
            fused.append(doc)

        return fused
