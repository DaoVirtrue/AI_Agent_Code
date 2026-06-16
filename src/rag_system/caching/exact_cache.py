"""L1 Cache: Exact match cache using in-memory dict with TTL."""

import time
import hashlib
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ExactCache:
    """L1 cache - exact query match with TTL.

    Fastest cache layer. Checks if the exact same query was answered before.
    Uses normalized query as key. Simple but high hit rate for repetitive queries.

    Properties:
    - O(1) lookup via hash map
    - Configurable TTL per entry
    - LRU eviction when max size reached
    - Thread-safe with simple locking
    """

    def __init__(self, max_size: int = 10000, ttl_seconds: int = 3600):
        """Initialize exact cache.

        Args:
            max_size: Maximum number of entries
            ttl_seconds: Default TTL for cache entries
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: dict[str, dict] = {}
        self._access_times: dict[str, float] = {}
        self._hits = 0
        self._misses = 0
        logger.info("ExactCache: max_size=%d, ttl=%ds", max_size, ttl_seconds)

    def get(self, query: str) -> Optional[dict]:
        """Get cached result for an exact query match.

        Args:
            query: The exact query text

        Returns:
            Cached result dict or None if not found/expired
        """
        key = self._normalize_key(query)

        if key in self._cache:
            entry = self._cache[key]
            # Check TTL
            if time.time() - entry["timestamp"] > entry.get("ttl", self.ttl_seconds):
                self._cache.pop(key, None)
                self._access_times.pop(key, None)
                self._misses += 1
                return None

            # Update access time for LRU
            self._access_times[key] = time.time()
            self._hits += 1
            logger.debug("ExactCache HIT for '%s...'", query[:30])
            return entry["result"]

        self._misses += 1
        return None

    def set(self, query: str, result: dict, ttl: Optional[int] = None) -> None:
        """Cache a result for a query.

        Args:
            query: The query text
            result: The result dict to cache
            ttl: Optional TTL override for this entry
        """
        key = self._normalize_key(query)

        # Evict if at capacity (LRU)
        if len(self._cache) >= self.max_size:
            self._evict_lru()

        self._cache[key] = {
            "result": result.copy(),
            "timestamp": time.time(),
            "ttl": ttl or self.ttl_seconds,
        }
        self._access_times[key] = time.time()

    def invalidate(self, query: str) -> bool:
        """Invalidate a specific cached query."""
        key = self._normalize_key(query)
        if key in self._cache:
            self._cache.pop(key)
            self._access_times.pop(key, None)
            return True
        return False

    def clear(self) -> None:
        """Clear all cache entries."""
        self._cache.clear()
        self._access_times.clear()
        logger.info("ExactCache cleared")

    def stats(self) -> dict:
        """Get cache statistics."""
        total = self._hits + self._misses
        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / max(total, 1),
            "ttl_seconds": self.ttl_seconds,
        }

    def _normalize_key(self, query: str) -> str:
        """Normalize query for cache key (case-insensitive, trimmed)."""
        return hashlib.md5(query.strip().lower().encode()).hexdigest()

    def _evict_lru(self) -> None:
        """Evict least recently used entry."""
        if not self._access_times:
            return

        lru_key = min(self._access_times, key=self._access_times.get)
        self._cache.pop(lru_key, None)
        self._access_times.pop(lru_key, None)

    def warm_cache(self, entries: list[tuple[str, dict]]) -> None:
        """Pre-warm the cache with query-result pairs."""
        for query, result in entries:
            self.set(query, result)
        logger.info("Warmed ExactCache with %d entries", len(entries))
