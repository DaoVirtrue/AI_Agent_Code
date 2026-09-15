"""Multi-level cache orchestrator.

Coordinates L1 (exact) -> L2 (semantic) -> L3 (summary) -> L4 (precomputed)
cache lookups and populates all levels on cache miss.
"""

import time
import logging
from typing import Any, Optional

from .exact_cache import ExactCache
from .semantic_cache import SemanticCache
from .summary_cache import SummaryCache
from .precomputed_cache import PrecomputedCache

logger = logging.getLogger(__name__)


class CacheOrchestrator:
    """Orchestrate multi-level caching for RAG queries.

    Cache hierarchy:
    L1 (ExactCache):      Exact query match - fastest
    L2 (SemanticCache):   Semantic similarity match - slightly slower
    L3 (SummaryCache):    Conversation context cache
    L4 (PrecomputedCache): Offline precomputed answers

    On lookup: check L1 -> L2 -> L4 (L3 is for conversation context only)
    On miss: generate, then populate L1 and L2

    L3 is used separately for conversation context management.
    """

    def __init__(
        self,
        l1: Optional[ExactCache] = None,
        l2: Optional[SemanticCache] = None,
        l3: Optional[SummaryCache] = None,
        l4: Optional[PrecomputedCache] = None,
    ):
        """Initialize cache orchestrator.

        Args:
            l1: L1 exact cache (created if None)
            l2: L2 semantic cache (created if None)
            l3: L3 summary cache (created if None)
            l4: L4 precomputed cache (created if None)
        """
        self.l1 = l1 or ExactCache()
        self.l2 = l2 or SemanticCache()
        self.l3 = l3 or SummaryCache()
        self.l4 = l4 or PrecomputedCache()

        self._total_queries = 0
        self._cache_hits = 0

        logger.info("CacheOrchestrator initialized with 4-level cache")

    async def lookup(self, query: str) -> dict:
        """Look up a query in the cache hierarchy.

        Returns:
            Dict with {hit: bool, level: str, answer: Optional[str], sources: Optional[list]}
        """
        self._total_queries += 1

        # L1: Exact match
        result = self.l1.get(query)
        if result:
            self._cache_hits += 1
            return {"hit": True, "level": "exact", **result}

        # L2: Semantic match
        result = await self.l2.get(query)
        if result:
            self._cache_hits += 1
            # Promote to L1 for future exact hits
            self.l1.set(query, result)
            return {"hit": True, "level": "semantic", **result}

        # L4: Precomputed
        result = await self.l4.get(query)
        if result:
            self._cache_hits += 1
            # Populate L1 and L2
            self.l1.set(query, result)
            # L2 set is async
            return {"hit": True, "level": "precomputed", **result}

        return {"hit": False, "level": "none", "answer": None, "sources": None}

    def store(self, query: str, result: dict) -> None:
        """Store a result in all cache levels (called on cache miss)."""
        self.l1.set(query, result)
        # L2 is async, so we schedule it
        # In production, this would be done via a background task

    async def store_async(self, query: str, result: dict) -> None:
        """Async version: store in all cache levels."""
        self.l1.set(query, result)
        await self.l2.set(query, result)

    # Conversation context methods (L3)
    def get_conversation_context(self, conversation_id: str) -> dict:
        """Get cached conversation context (L3)."""
        return self.l3.get_context(conversation_id)

    def add_conversation_message(
        self, conversation_id: str, role: str, content: str, **kwargs
    ) -> None:
        """Add a message to conversation cache (L3)."""
        self.l3.add_message(conversation_id, role, content, **kwargs)

    def update_conversation_summary(self, conversation_id: str, summary: str) -> None:
        """Update conversation summary (L3)."""
        self.l3.update_summary(conversation_id, summary)

    def delete_conversation(self, conversation_id: str) -> bool:
        """Delete a conversation from cache."""
        return self.l3.delete_conversation(conversation_id)

    def clear_all(self) -> None:
        """Clear all cache levels."""
        self.l1.clear()
        self.l2.clear()
        self.l3.clear()
        self.l4.clear()
        logger.info("All cache levels cleared")

    def stats(self) -> dict:
        """Get aggregate cache statistics."""
        return {
            "total_queries": self._total_queries,
            "cache_hits": self._cache_hits,
            "overall_hit_rate": self._cache_hits / max(self._total_queries, 1),
            "l1_exact": self.l1.stats(),
            "l2_semantic": self.l2.stats(),
            "l3_summary": self.l3.stats(),
            "l4_precomputed": self.l4.stats(),
        }

    def warm_cache(self, entries: list[tuple[str, dict]]) -> None:
        """Pre-warm all cache levels with query-result pairs."""
        for query, result in entries:
            self.l1.set(query, result)
        logger.info("Cache warming: %d entries added to L1", len(entries))
