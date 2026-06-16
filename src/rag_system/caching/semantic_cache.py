"""L2 Cache: Semantic similarity cache.

Finds cached answers for semantically similar (not identical) queries
using embedding similarity.
"""

import time
import logging
from typing import Any, Optional

import numpy as np

logger = logging.getLogger(__name__)


class SemanticCache:
    """L2 cache - semantic similarity matching.

    Uses embedding similarity to find cached answers for queries that
    are semantically similar to previously answered questions.

    Properties:
    - Embedding-based similarity matching
    - Configurable similarity threshold
    - Fallback when no embedder available
    - TTL + LRU eviction
    """

    def __init__(
        self,
        embedder=None,
        similarity_threshold: float = 0.92,
        max_size: int = 5000,
        ttl_seconds: int = 7200,
    ):
        """Initialize semantic cache.

        Args:
            embedder: Embedder with embed_query() method
            similarity_threshold: Minimum cosine similarity for a hit (0-1)
            max_size: Maximum entries
            ttl_seconds: Entry TTL
        """
        self.embedder = embedder
        self.similarity_threshold = similarity_threshold
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds

        self._entries: list[dict] = []  # [{query, embedding, result, timestamp}]
        self._hits = 0
        self._misses = 0

        logger.info("SemanticCache: threshold=%.2f, max_size=%d", similarity_threshold, max_size)

    async def get(self, query: str) -> Optional[dict]:
        """Get cached result for a semantically similar query.

        Args:
            query: Query text

        Returns:
            Cached result or None
        """
        if not self._entries:
            self._misses += 1
            return None

        # Embed query
        query_embedding = await self._embed(query)
        if query_embedding is None:
            self._misses += 1
            return None

        best_similarity = 0.0
        best_entry = None

        now = time.time()
        valid_entries = []

        for entry in self._entries:
            # Skip expired entries
            if now - entry["timestamp"] > self.ttl_seconds:
                continue

            valid_entries.append(entry)

            if entry.get("embedding") is not None:
                similarity = self._cosine_similarity(query_embedding, entry["embedding"])
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_entry = entry

        # Clean up expired entries
        self._entries = valid_entries

        if best_entry and best_similarity >= self.similarity_threshold:
            self._hits += 1
            logger.debug("SemanticCache HIT (similarity=%.3f)", best_similarity)
            return best_entry["result"]

        self._misses += 1
        return None

    async def set(self, query: str, result: dict) -> None:
        """Cache a result with its query embedding."""
        query_embedding = await self._embed(query)

        if len(self._entries) >= self.max_size:
            self._evict_oldest()

        entry = {
            "query": query,
            "embedding": query_embedding,
            "result": result.copy(),
            "timestamp": time.time(),
        }
        self._entries.append(entry)

    async def _embed(self, text: str) -> Optional[np.ndarray]:
        """Embed text, with fallback."""
        if self.embedder:
            try:
                return await self.embedder.embed_query(text)
            except Exception as e:
                logger.warning("SemanticCache embed error: %s", e)

        # Fallback: bag-of-words vector
        return self._fallback_embed(text)

    def _fallback_embed(self, text: str, dim: int = 128) -> np.ndarray:
        """Simple fallback embedding using character n-grams."""
        text = text.lower().strip()
        vec = np.zeros(dim)
        for i in range(len(text) - 2):
            ngram = text[i:i+3]
            idx = hash(ngram) % dim
            vec[idx] += 1
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Cosine similarity between two vectors."""
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    def _evict_oldest(self) -> None:
        """Evict the oldest entry."""
        if self._entries:
            self._entries.pop(0)

    def clear(self) -> None:
        """Clear all entries."""
        self._entries.clear()
        logger.info("SemanticCache cleared")

    def stats(self) -> dict:
        total = self._hits + self._misses
        return {
            "size": len(self._entries),
            "max_size": self.max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / max(total, 1),
            "threshold": self.similarity_threshold,
        }
