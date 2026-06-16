"""
Ebbinghaus forgetting curve implementation for memory retention modeling.

Implements: R = e^(-t/S)
Where R is retention, t is elapsed time, and S is relative strength.

Used to decide when memories should be evicted based on their decay.
"""

import logging
import math
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class RetentionGranularity:
    """Time constants for different memory importance levels."""
    FINE: float = 86400 * 30     # 30 days
    MEDIUM: float = 86400 * 7     # 7 days
    COARSE: float = 86400 * 1     # 1 day
    TRANSIENT: float = 86400 * 0.5  # 12 hours


class ForgettingCurve:
    """Ebbinghaus-inspired forgetting curve for memory retention.

    Models memory decay using: R = e^(-t/S)

    Where:
    - R is retention (0 to 1)
    - t is elapsed time in seconds
    - S is the strength/decay constant

    Args:
        default_granularity: Default decay speed ("fine", "medium", "coarse", "transient").
        eviction_threshold: Retention below which memories are evicted (default 0.1).
        importance_boost: Multiplier to extend retention for high-importance memories.
    """

    STRENGTH: dict[str, float] = {
        "fine": RetentionGranularity.FINE,
        "medium": RetentionGranularity.MEDIUM,
        "coarse": RetentionGranularity.COARSE,
        "transient": RetentionGranularity.TRANSIENT,
    }

    def __init__(
        self,
        default_granularity: str = "medium",
        eviction_threshold: float = 0.1,
        importance_boost: bool = True,
    ):
        self.default_granularity = default_granularity
        self.eviction_threshold = eviction_threshold
        self.importance_boost = importance_boost

    # ------------------------------------------------------------------
    # Core retention calculation
    # ------------------------------------------------------------------

    def retention(
        self,
        elapsed: float,
        granularity: str = "medium",
        importance: float = 5.0,
    ) -> float:
        """Calculate the retention score for a memory.

        Args:
            elapsed: Time elapsed since the memory was created or last accessed (seconds).
            granularity: Decay speed ("fine", "medium", "coarse", "transient").
            importance: Importance score (1-10), used to boost retention.

        Returns:
            Retention score between 0 and 1.
        """
        base_strength = self.STRENGTH.get(granularity, self.STRENGTH["medium"])

        # Importance boost: higher importance means slower decay
        if self.importance_boost:
            # Scale: importance 10 = 2x retention, importance 1 = 0.5x
            boost = 0.5 + (importance / 10.0) * 1.5
            strength = base_strength * boost
        else:
            strength = base_strength

        # Ebbinghaus formula: R = e^(-t/S)
        if strength <= 0:
            return 0.0

        retention_value = math.exp(-elapsed / strength)

        # Clamp to [0, 1]
        return max(0.0, min(1.0, retention_value))

    # ------------------------------------------------------------------
    # Eviction decision
    # ------------------------------------------------------------------

    def should_evict(self, entry: dict, current_time: float) -> bool:
        """Decide whether a memory entry should be evicted.

        Args:
            entry: Dict with keys: created_at, last_accessed, importance.
            current_time: Current timestamp for elapsed calculation.

        Returns:
            True if the memory should be evicted.
        """
        created_at = entry.get("created_at", current_time)
        last_accessed = entry.get("last_accessed", created_at)
        importance = entry.get("importance", 5.0)

        # Use last accessed time for more recent decay reset
        elapsed = current_time - last_accessed

        # Determine granularity based on importance
        if importance >= 8:
            granularity = "fine"
        elif importance >= 5:
            granularity = "medium"
        elif importance >= 3:
            granularity = "coarse"
        else:
            granularity = "transient"

        r = self.retention(elapsed, granularity, importance)
        should_evict = r < self.eviction_threshold

        if should_evict:
            logger.debug(
                "Eviction candidate: importance=%.1f, age=%.1fh, retention=%.4f",
                importance, elapsed / 3600, r,
            )

        return should_evict

    # ------------------------------------------------------------------
    # Bulk operations
    # ------------------------------------------------------------------

    def filter_active(
        self,
        entries: list[dict],
        current_time: float | None = None,
    ) -> list[dict]:
        """Filter a list of memory entries to only active (non-evicted) ones.

        Args:
            entries: List of memory entry dicts.
            current_time: Reference time (defaults to now).

        Returns:
            List of entries that should be retained.
        """
        now = current_time or time.time()
        return [e for e in entries if not self.should_evict(e, now)]

    def get_retention_scores(
        self,
        entries: list[dict],
        current_time: float | None = None,
    ) -> list[tuple[dict, float]]:
        """Get retention scores for a list of entries.

        Args:
            entries: List of memory entry dicts.
            current_time: Reference time (defaults to now).

        Returns:
            List of (entry, retention_score) tuples.
        """
        now = current_time or time.time()
        results = []
        for entry in entries:
            created_at = entry.get("created_at", now)
            last_accessed = entry.get("last_accessed", created_at)
            importance = entry.get("importance", 5.0)
            elapsed = now - last_accessed
            r = self.retention(
                elapsed,
                self._granularity_for_importance(importance),
                importance,
            )
            results.append((entry, r))
        return results

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _granularity_for_importance(self, importance: float) -> str:
        """Map an importance score to a granularity level."""
        if importance >= 8:
            return "fine"
        elif importance >= 5:
            return "medium"
        elif importance >= 3:
            return "coarse"
        else:
            return "transient"

    def time_until_eviction(
        self,
        importance: float = 5.0,
        granularity: str = "medium",
    ) -> float:
        """Estimate how long until a memory reaches the eviction threshold.

        Args:
            importance: Importance score (1-10).
            granularity: Decay speed.

        Returns:
            Estimated seconds until eviction threshold is reached.
        """
        base_strength = self.STRENGTH.get(granularity, self.STRENGTH["medium"])

        if self.importance_boost:
            boost = 0.5 + (importance / 10.0) * 1.5
            strength = base_strength * boost
        else:
            strength = base_strength

        # Solve: e^(-t/S) = eviction_threshold
        # t = -S * ln(eviction_threshold)
        if self.eviction_threshold <= 0:
            return float("inf")

        return -strength * math.log(self.eviction_threshold)

    def __repr__(self) -> str:
        return (
            f"ForgettingCurve(granularity={self.default_granularity}, "
            f"threshold={self.eviction_threshold})"
        )
