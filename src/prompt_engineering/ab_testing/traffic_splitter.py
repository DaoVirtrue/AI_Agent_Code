"""Deterministic traffic splitting using hash-based assignment.

Provides consistent hashing to ensure the same user always gets
the same variant, while maintaining specified traffic ratios.
"""

import hashlib
import logging
from collections import defaultdict
from typing import Optional

logger = logging.getLogger(__name__)


class TrafficSplitter:
    """Deterministic traffic splitting using hash-based assignment.

    Uses consistent hashing to ensure the same user always gets
    the same variant, while maintaining the specified traffic ratios.

    Algorithm:
    1. Hash the key using SHA-256
    2. Normalize hash to [0, 1) range
    3. Map to variant based on cumulative probability ranges
    """

    def __init__(self, split_config: dict[str, float]):
        """Initialize with variant -> weight mapping.

        Args:
            split_config: Dict mapping variant name to its traffic weight.
                e.g., {"variant_a": 0.5, "variant_b": 0.3, "control": 0.2}

        Raises:
            ValueError: If weights are non-positive or don't sum to ~1.0.
        """
        self._validate_and_set_config(split_config)
        self._counters: dict[str, int] = defaultdict(int)
        self._total_assignments: int = 0
        logger.info(
            "TrafficSplitter initialized with %d variants: %s",
            len(self._variants),
            {v: f"{w:.0%}" for v, w in self._cumulative.items()},
        )

    def _validate_and_set_config(self, split_config: dict[str, float]) -> None:
        """Validate the split configuration and set internal state.

        Args:
            split_config: The variant->weight mapping.

        Raises:
            ValueError: If validation fails.
        """
        if not split_config:
            raise ValueError("split_config must not be empty")

        total = sum(split_config.values())

        if not (0.99 <= total <= 1.01):
            raise ValueError(
                f"Split weights sum to {total:.4f}, expected ~1.0 "
                f"(tolerance: +/-0.01)"
            )

        for variant_name, weight in split_config.items():
            if weight <= 0:
                raise ValueError(
                    f"Weight for variant '{variant_name}' must be positive, "
                    f"got {weight}"
                )

        # Store sorted variants for stable ordering
        self._variants = sorted(split_config.keys())
        self._weights = {v: split_config[v] for v in self._variants}

        # Pre-compute cumulative probability ranges
        self._cumulative: dict[str, float] = {}
        cumulative = 0.0
        for variant in self._variants:
            cumulative += self._weights[variant]
            self._cumulative[variant] = cumulative

    def assign(self, key: str) -> str:
        """Assign a key to a variant deterministically.

        Uses SHA-256 hash of the key, normalized to [0, 1), then mapped
        to the corresponding variant's cumulative probability range.

        Args:
            key: A unique identifier (e.g., user_id, session_id).

        Returns:
            The assigned variant name.
        """
        # Compute SHA-256 hash of the key
        hash_digest = hashlib.sha256(key.encode("utf-8")).hexdigest()

        # Take first 16 hex characters (64 bits) and normalize to [0, 1)
        hash_int = int(hash_digest[:16], 16)
        normalized = hash_int / (16 ** 16)

        # Map to variant based on cumulative ranges
        assigned = None
        for variant in self._variants:
            if normalized < self._cumulative[variant]:
                assigned = variant
                break

        # Fallback: should not occur if ranges cover [0, 1)
        if assigned is None:
            assigned = self._variants[-1]

        # Update counters
        self._counters[assigned] += 1
        self._total_assignments += 1

        logger.debug(
            "Key '%s' hashed to %.6f -> assigned to '%s'",
            key[:20] + "..." if len(key) > 20 else key,
            normalized,
            assigned,
        )

        return assigned

    def get_actual_split(self) -> dict[str, float]:
        """Get the observed traffic split based on all assignments made so far.

        Returns:
            Dict mapping variant_name -> actual_fraction of traffic.
            Returns the configured split if no assignments have been made.
        """
        if self._total_assignments == 0:
            return dict(self._weights)

        result = {}
        for variant in self._variants:
            count = self._counters.get(variant, 0)
            result[variant] = count / self._total_assignments
        return result

    def update_config(self, split_config: dict[str, float]) -> None:
        """Update the split configuration. Resets assignment counters.

        Args:
            split_config: New variant->weight mapping.

        Raises:
            ValueError: If validation fails.
        """
        self._validate_and_set_config(split_config)
        self._counters = defaultdict(int)
        self._total_assignments = 0
        logger.info(
            "Traffic split configuration updated and counters reset. "
            "New config: %s",
            {v: f"{w:.0%}" for v, w in self._cumulative.items()},
        )

    def reset_counters(self) -> None:
        """Reset assignment counters for re-measurement."""
        self._counters = defaultdict(int)
        self._total_assignments = 0
        logger.info("Traffic split assignment counters reset")
