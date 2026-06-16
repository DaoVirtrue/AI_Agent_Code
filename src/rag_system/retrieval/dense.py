"""Dense vector retrieval using embedding similarity."""

import logging
from typing import Any, Optional

import numpy as np

from ..indexing.vector_store import BaseVectorStore, VectorDocument

logger = logging.getLogger(__name__)


class DenseRetriever:
    """Dense retrieval using embedding similarity search.

    Uses a vector store for storage and an embedder for query encoding.
    Supports filtering and score thresholding.
    """

    def __init__(
        self,
        vector_store: BaseVectorStore,
        embedder,
        top_k: int = 10,
        similarity_threshold: float = 0.0,
    ):
        """Initialize dense retriever.

        Args:
            vector_store: Vector store backend (Milvus, Chroma, FAISS, etc.)
            embedder: Embedder with embed_query() method
            top_k: Default number of results to return
            similarity_threshold: Minimum similarity score (0-1)
        """
        self.vector_store = vector_store
        self.embedder = embedder
        self.top_k = top_k
        self.similarity_threshold = similarity_threshold
        logger.info("DenseRetriever: top_k=%d, threshold=%.2f", top_k, similarity_threshold)

    async def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        filters: Optional[dict] = None,
    ) -> list[dict]:
        """Retrieve documents by embedding similarity.

        Args:
            query: Query text
            top_k: Number of results (overrides default)
            filters: Metadata filters for vector store

        Returns:
            List of {id, content, score, metadata} dicts
        """
        if top_k is None:
            top_k = self.top_k

        # Embed query
        query_embedding = await self.embedder.embed_query(query)

        # Search vector store
        results = await self.vector_store.search(
            query_embedding=query_embedding,
            top_k=top_k,
            filters=filters,
        )

        # Apply threshold and convert to dicts
        documents = []
        for doc in results:
            if doc.score >= self.similarity_threshold:
                documents.append(doc.to_dict())

        logger.debug("Dense retrieval: %d results for query '%s...'", len(documents), query[:50])
        return documents

    async def retrieve_with_scores(
        self, query: str, top_k: int = 10, **kwargs
    ) -> list[tuple[dict, float]]:
        """Retrieve documents with their similarity scores."""
        docs = await self.retrieve(query, top_k=top_k, **kwargs)
        return [(doc, doc.get("score", 0.0)) for doc in docs]

    async def batch_retrieve(
        self, queries: list[str], top_k: int = 10, **kwargs
    ) -> list[list[dict]]:
        """Batch retrieve for multiple queries."""
        results = []
        for query in queries:
            docs = await self.retrieve(query, top_k=top_k, **kwargs)
            results.append(docs)
        return results
