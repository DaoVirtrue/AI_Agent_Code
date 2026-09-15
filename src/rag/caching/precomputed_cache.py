"""L4 Cache: Precomputed answers for frequent/templated queries.

For known frequent queries, precompute and cache answers offline.
This is the slowest to populate but has zero latency on hit.
"""

import json
import logging
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)


class PrecomputedCache:
    """L4 cache - precomputed answers.

    For high-traffic queries (e.g., FAQ questions, common support queries),
    answers are precomputed and stored. This cache is populated offline
    or by scheduled jobs, not on cache miss.

    Supports pattern matching for templated queries:
    "What is {product} pricing?" -> precomputed answers per product
    """

    def __init__(self, cache_file: Optional[str] = None):
        """Initialize precomputed cache.

        Args:
            cache_file: Optional JSON file to load precomputed entries from
        """
        self._entries: dict[str, dict] = {}
        self._pattern_entries: list[dict] = []
        self._hits = 0
        self._misses = 0

        if cache_file:
            self.load_from_file(cache_file)

        logger.info("PrecomputedCache: %d exact entries, %d patterns",
                     len(self._entries), len(self._pattern_entries))

    async def get(self, query: str) -> Optional[dict]:
        """Get a precomputed answer for a query.

        Checks exact match first, then pattern match.
        """
        normalized = query.strip().lower()

        # Exact match
        if normalized in self._entries:
            self._hits += 1
            logger.debug("PrecomputedCache EXACT HIT")
            return self._entries[normalized]

        # Pattern match
        for pattern_entry in self._pattern_entries:
            import re
            pattern = pattern_entry.get("pattern", "")
            if pattern and re.search(pattern, normalized):
                self._hits += 1
                logger.debug("PrecomputedCache PATTERN HIT")
                return pattern_entry["result"]

        self._misses += 1
        return None

    def add_entry(self, query: str, result: dict, is_pattern: bool = False) -> None:
        """Add a precomputed entry.

        Args:
            query: Query text or regex pattern (if is_pattern=True)
            result: Precomputed result dict
            is_pattern: Whether query is a regex pattern
        """
        if is_pattern:
            self._pattern_entries.append({
                "pattern": query,
                "result": result.copy(),
                "added_at": time.time(),
            })
        else:
            self._entries[query.strip().lower()] = result.copy()

    def remove_entry(self, query: str) -> bool:
        """Remove a precomputed entry."""
        normalized = query.strip().lower()
        if normalized in self._entries:
            del self._entries[normalized]
            return True
        return False

    def load_from_file(self, file_path: str) -> bool:
        """Load precomputed entries from a JSON file.

        File format:
        {
            "entries": [
                {"query": "exact query", "result": {...}},
                {"query": "regex pattern", "result": {...}, "is_pattern": true}
            ]
        }
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            for entry in data.get("entries", []):
                query = entry["query"]
                result = entry["result"]
                is_pattern = entry.get("is_pattern", False)

                if is_pattern:
                    self._pattern_entries.append({
                        "pattern": query,
                        "result": result,
                        "added_at": time.time(),
                    })
                else:
                    self._entries[query.strip().lower()] = result

            logger.info("Loaded %d precomputed entries from %s", len(data.get("entries", [])), file_path)
            return True
        except Exception as e:
            logger.error("Failed to load precomputed cache: %s", e)
            return False

    def save_to_file(self, file_path: str) -> bool:
        """Save precomputed entries to a JSON file."""
        try:
            entries = []
            for query, result in self._entries.items():
                entries.append({"query": query, "result": result})
            for pe in self._pattern_entries:
                entries.append({
                    "query": pe["pattern"],
                    "result": pe["result"],
                    "is_pattern": True,
                })

            with open(file_path, "w", encoding="utf-8") as f:
                json.dump({"entries": entries}, f, ensure_ascii=False, indent=2)

            logger.info("Saved %d precomputed entries to %s", len(entries), file_path)
            return True
        except Exception as e:
            logger.error("Failed to save precomputed cache: %s", e)
            return False

    def clear(self) -> None:
        """Clear all precomputed entries."""
        self._entries.clear()
        self._pattern_entries.clear()

    def stats(self) -> dict:
        total = self._hits + self._misses
        return {
            "exact_entries": len(self._entries),
            "pattern_entries": len(self._pattern_entries),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / max(total, 1),
        }
