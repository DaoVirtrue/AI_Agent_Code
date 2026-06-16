"""
Load Balancer

Intelligent provider selection using configurable strategies:
  - Weighted Round Robin: weights from model priority configuration
  - Least Latency: selects the provider with the lowest recent P50 latency
"""

from __future__ import annotations

import asyncio
import logging
import statistics
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ai_gateway.providers.base import BaseProvider

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ProviderWeight:
    """Weight configuration for a specific provider and model."""

    provider_name: str
    weight: int = 100
    priority: int = 1  # 1 = highest
    models: List[str] = field(default_factory=list)


_DEFAULT_WEIGHTS: Dict[str, List[ProviderWeight]] = {
    "gpt-4o": [
        ProviderWeight(provider_name="openai", weight=100, priority=1, models=["gpt-4o"]),
    ],
    "gpt-4o-mini": [
        ProviderWeight(provider_name="openai", weight=100, priority=1, models=["gpt-4o-mini"]),
    ],
    "claude-sonnet-4": [
        ProviderWeight(provider_name="anthropic", weight=100, priority=1, models=["claude-sonnet-4"]),
    ],
    "claude-opus-4": [
        ProviderWeight(provider_name="anthropic", weight=100, priority=1, models=["claude-opus-4"]),
    ],
    "deepseek-chat": [
        ProviderWeight(provider_name="deepseek", weight=100, priority=1, models=["deepseek-chat"]),
    ],
}

# Default weight for unknown models
_DEFAULT_WEIGHT = 50


@dataclass
class LatencyRecord:
    """A single latency measurement for a provider."""

    value_ms: float
    timestamp: float = field(default_factory=time.monotonic)


# ---------------------------------------------------------------------------
# Load balancer strategies
# ---------------------------------------------------------------------------

class WeightedRoundRobin:
    """
    Weighted round-robin selection.

    Weights are obtained from the provider model configuration.
    Higher weight = more frequent selection.
    """

    def __init__(self):
        self._counters: Dict[str, int] = {}
        self._lock = asyncio.Lock()

    async def select(
        self,
        candidates: List[BaseProvider],
        weights: Dict[str, int],
    ) -> BaseProvider:
        """
        Select the next provider using weighted round-robin.

        Args:
            candidates: Available provider instances.
            weights: Mapping of provider_name -> weight.

        Returns:
            The selected provider instance.
        """
        if not candidates:
            raise ValueError("No candidates available for selection")

        if len(candidates) == 1:
            return candidates[0]

        async with self._lock:
            total_weight = sum(
                weights.get(p.provider_name, _DEFAULT_WEIGHT) for p in candidates
            )
            if total_weight == 0:
                total_weight = len(candidates)

            # Find the candidate with the highest counter-to-weight ratio
            # (standard weighted round robin algorithm)
            best_provider = candidates[0]
            best_ratio = float("inf")

            for provider in candidates:
                name = provider.provider_name
                weight = weights.get(name, _DEFAULT_WEIGHT)

                counter = self._counters.get(name, 0)
                ratio = counter / weight if weight > 0 else float("inf")

                if ratio < best_ratio:
                    best_ratio = ratio
                    best_provider = provider

            self._counters[best_provider.provider_name] = (
                self._counters.get(best_provider.provider_name, 0) + 1
            )

        return best_provider


class LeastLatency:
    """
    Least-latency selection strategy.

    Tracks a sliding window of the last N latency measurements per provider
    and selects the one with the lowest P50 (median) latency.
    """

    def __init__(self, window_size: int = 100, min_samples: int = 5):
        """
        Args:
            window_size: Number of recent latency measurements to track.
            min_samples: Minimum samples before P50 is trusted.
        """
        self._window_size = window_size
        self._min_samples = min_samples
        self._latencies: Dict[str, deque] = {}
        self._lock = asyncio.Lock()

    async def select(
        self,
        candidates: List[BaseProvider],
    ) -> BaseProvider:
        """
        Select the provider with the lowest P50 latency.

        Falls back to round-robin if insufficient latency data is available.
        """
        if not candidates:
            raise ValueError("No candidates available for selection")

        if len(candidates) == 1:
            return candidates[0]

        async with self._lock:
            best_provider = candidates[0]
            best_p50 = float("inf")

            for provider in candidates:
                name = provider.provider_name
                records = self._latencies.get(name, deque())
                values = [r.value_ms for r in records]

                if len(values) >= self._min_samples:
                    p50 = statistics.median(values)
                    if p50 < best_p50:
                        best_p50 = p50
                        best_provider = provider
                else:
                    # Not enough data: prefer this untested provider
                    if best_p50 == float("inf"):
                        best_provider = provider

            return best_provider

    async def record_latency(self, provider_name: str, latency_ms: float) -> None:
        """
        Record a latency measurement for a provider.

        Args:
            provider_name: The provider's name (from provider_name property).
            latency_ms: Measured latency in milliseconds.
        """
        async with self._lock:
            if provider_name not in self._latencies:
                self._latencies[provider_name] = deque(maxlen=self._window_size)
            self._latencies[provider_name].append(LatencyRecord(value_ms=latency_ms))

    def get_p50(self, provider_name: str) -> Optional[float]:
        """Get the current P50 latency for a provider."""
        records = self._latencies.get(provider_name)
        if not records or len(records) < self._min_samples:
            return None
        return statistics.median([r.value_ms for r in records])


# ---------------------------------------------------------------------------
# Main LoadBalancer
# ---------------------------------------------------------------------------

class LoadBalancer:
    """
    Provider load balancer supporting multiple strategies.

    Strategies:
      - "weighted_round_robin": Default. Uses configurable weights.
      - "least_latency": Selects the fastest provider based on recent P50.
      - "random": Simple random selection.
    """

    STRATEGIES = ("weighted_round_robin", "least_latency", "random")

    def __init__(
        self,
        weights: Optional[Dict[str, List[ProviderWeight]]] = None,
        default_strategy: str = "weighted_round_robin",
    ):
        """
        Args:
            weights: Model-to-provider weight mappings. Uses _DEFAULT_WEIGHTS if None.
            default_strategy: The strategy to use for selection.
        """
        self._weights: Dict[str, List[ProviderWeight]] = weights or _DEFAULT_WEIGHTS
        self._default_strategy = default_strategy
        self._wrr = WeightedRoundRobin()
        self._least_latency = LeastLatency(window_size=100, min_samples=5)
        self._provider_for_model: Dict[str, str] = {}

        # Flatten weights: first match is the best match
        for model, pw_list in self._weights.items():
            for pw in pw_list:
                for m in pw.models:
                    self._provider_for_model[m] = pw.provider_name

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------

    async def select(
        self,
        model_id: str,
        candidates: List[BaseProvider],
        strategy: Optional[str] = None,
    ) -> BaseProvider:
        """
        Select a provider for the given model.

        Args:
            model_id: The requested model name.
            candidates: List of available providers that can serve this model.
            strategy: Override the default selection strategy.

        Returns:
            The selected BaseProvider instance.
        """
        strategy = strategy or self._default_strategy

        # Filter to only providers that can serve this model
        ranked_providers = self._rank_candidates(model_id, candidates)

        if not ranked_providers:
            raise ValueError(f"No provider available for model '{model_id}'")

        if strategy == "least_latency":
            return await self._least_latency.select(ranked_providers)
        elif strategy == "weighted_round_robin":
            weights = self._build_weight_map(model_id, ranked_providers)
            return await self._wrr.select(ranked_providers, weights)
        elif strategy == "random":
            import random
            return random.choice(ranked_providers)
        else:
            raise ValueError(f"Unknown strategy: {strategy}")

    async def record_latency(self, provider_name: str, latency_ms: float) -> None:
        """
        Record a latency measurement for use by latency-aware strategies.
        """
        await self._least_latency.record_latency(provider_name, latency_ms)

    def get_latency_stats(self, provider_name: str) -> Dict[str, Any]:
        """Get latency statistics for a provider."""
        p50 = self._least_latency.get_p50(provider_name)
        return {
            "provider": provider_name,
            "p50_ms": p50,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _rank_candidates(
        self,
        model_id: str,
        candidates: List[BaseProvider],
    ) -> List[BaseProvider]:
        """
        Rank candidates by priority for the given model.

        Providers explicitly listed in the weight config for this model
        are ranked first, sorted by priority (lower = higher priority).
        """
        if model_id not in self._weights:
            return candidates

        weight_list = self._weights[model_id]
        preferred_names = [
            pw.provider_name for pw in sorted(weight_list, key=lambda p: p.priority)
        ]

        # Sort candidates: preferred first, then the rest
        def sort_key(p: BaseProvider) -> int:
            try:
                return preferred_names.index(p.provider_name)
            except ValueError:
                return len(preferred_names)

        return sorted(candidates, key=sort_key)

    def _build_weight_map(
        self,
        model_id: str,
        candidates: List[BaseProvider],
    ) -> Dict[str, int]:
        """Build a provider_name -> weight mapping for weighted selection."""
        weight_map: Dict[str, int] = {}

        if model_id in self._weights:
            for pw in self._weights[model_id]:
                weight_map[pw.provider_name] = pw.weight

        # Ensure all candidates have a weight
        for provider in candidates:
            if provider.provider_name not in weight_map:
                weight_map[provider.provider_name] = _DEFAULT_WEIGHT

        return weight_map

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def set_weights(self, model_id: str, weights: List[ProviderWeight]) -> None:
        """Update weight configuration for a model."""
        self._weights[model_id] = weights
        for pw in weights:
            for m in pw.models:
                self._provider_for_model[m] = pw.provider_name

    def get_weights(self, model_id: str) -> List[ProviderWeight]:
        """Get weight configuration for a model."""
        return self._weights.get(model_id, [])
