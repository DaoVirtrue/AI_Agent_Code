"""Hybrid retrieval combining dense and sparse approaches."""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

from .dense import DenseRetriever
from .sparse import SparseRetriever
from .fusion import RRFFusion


class HybridRetriever:
    """Combines dense and sparse retrieval for better recall.

    Strategy:
    1. Run dense and sparse retrieval in parallel
    2. Fuse results using Reciprocal Rank Fusion (RRF)
    3. Optional: weight the contribution of each retriever
    4. Return fused ranked list

    This approach captures both semantic similarity (dense) and
    keyword matching (sparse), complementing each other's weaknesses.
    """

    def __init__(
        self,
        dense_retriever: DenseRetriever,
        sparse_retriever: SparseRetriever,
        alpha: float = 0.5,  # Weight of dense vs sparse
        fusion_k: int = 60,
        top_k: int = 10,
    ):
        """Initialize hybrid retriever.

        Args:
            dense_retriever: Dense retriever instance
            sparse_retriever: Sparse retriever instance
            alpha: Weight for dense results (0-1). 0=all sparse, 1=all dense
            fusion_k: RRF k parameter (controls rank decay)
            top_k: Final number of results
        """
        self.dense = dense_retriever
        self.sparse = sparse_retriever
        self.alpha = alpha
        self.top_k = top_k

        self.fusion = RRFFusion(k=fusion_k)
        logger.info("HybridRetriever: alpha=%.2f, k=%d, top_k=%d", alpha, fusion_k, top_k)

    async def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        filters: Optional[dict] = None,
    ) -> list[dict]:
        """Retrieve using both dense and sparse, then fuse results.

        Args:
            query: Query text
            top_k: Final number of results
            filters: Metadata filters

        Returns:
            Fused and ranked list of {id, content, score, metadata} dicts
        """
        if top_k is None:
            top_k = self.top_k

        # Query expansion for sparse (helps with keyword matching)
        expanded_query = self._expand_query(query)

        # Run both retrievers
        dense_results = await self.dense.retrieve(query, top_k=top_k * 2, filters=filters)
        sparse_results = await self.sparse.retrieve(expanded_query, top_k=top_k * 2, filters=filters)

        logger.debug("Hybrid: dense=%d, sparse=%d results", len(dense_results), len(sparse_results))

        # Fuse using RRF with alpha weighting
        fused = self.fusion.fuse(
            dense_results,
            sparse_results,
            weights=(self.alpha, 1.0 - self.alpha),
        )

        return fused[:top_k]

    def _expand_query(self, query: str) -> str:
        """Simple query expansion for sparse retrieval.
        Adds common synonyms and handles abbreviations."""
        # Basic expansion: repeat key terms for BM25 emphasis
        words = query.split()
        if len(words) <= 3:
            # Short query: expand with related terms
            return query + " " + " ".join(words)
        return query

    async def retrieve_with_debug(
        self, query: str, top_k: int = 10, **kwargs
    ) -> dict:
        """Retrieve with detailed debug information about each step."""
        dense_results = await self.dense.retrieve(query, top_k=top_k * 2, **kwargs)
        sparse_results = await self.sparse.retrieve(query, top_k=top_k * 2, **kwargs)
        fused = self.fusion.fuse(dense_results, sparse_results, (self.alpha, 1.0 - self.alpha))

        return {
            "query": query,
            "dense_results": dense_results[:top_k],
            "sparse_results": sparse_results[:top_k],
            "fused_results": fused[:top_k],
            "alpha": self.alpha,
        }
