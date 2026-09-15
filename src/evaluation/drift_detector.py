"""Drift detection for monitoring RAG/LLM quality degradation over time."""

import statistics
from dataclasses import dataclass, field
from typing import Optional

from src.observability.logging_setup import get_logger

logger = get_logger(__name__)


@dataclass
class DriftResult:
    """Result of drift detection analysis."""

    drift_detected: bool
    dimensions_drifted: list[str]
    baseline_scores: dict[str, float]
    current_scores: dict[str, float]
    deltas: dict[str, float]
    p_values: dict[str, float] = field(default_factory=dict)
    threshold: float = 0.05
    details: str = ""

    @property
    def max_drift_dimension(self) -> Optional[str]:
        """The dimension with the largest absolute drift."""
        if not self.deltas:
            return None
        return max(self.deltas, key=lambda k: abs(self.deltas[k]))

    @property
    def max_drift_magnitude(self) -> float:
        """The magnitude of the largest drift."""
        if not self.deltas:
            return 0.0
        return max(abs(v) for v in self.deltas.values())


class DriftDetector:
    """Detects statistical drift in RAG/LLM evaluation scores.

    Compares current evaluation scores against baseline scores and
    flags dimensions that have degraded beyond a configurable threshold.

    Detection methods:
    - Absolute difference: |current - baseline| > threshold
    - Relative difference: |current - baseline| / baseline > threshold
    - Statistical test: Mann-Whitney U test (when raw score arrays available)
    """

    def __init__(
        self,
        absolute_threshold: float = 0.05,
        relative_threshold: float = 0.10,
        min_sample_size: int = 10,
    ):
        """Initialize the drift detector.

        Args:
            absolute_threshold: Minimum absolute score difference to flag drift.
            relative_threshold: Minimum relative change to flag drift.
            min_sample_size: Minimum samples needed for statistical tests.
        """
        self.absolute_threshold = absolute_threshold
        self.relative_threshold = relative_threshold
        self.min_sample_size = min_sample_size

    def detect(
        self,
        baseline_scores: dict[str, float],
        current_scores: dict[str, float],
        threshold: Optional[float] = None,
        baseline_samples: Optional[dict[str, list[float]]] = None,
        current_samples: Optional[dict[str, list[float]]] = None,
    ) -> DriftResult:
        """Detect drift between baseline and current evaluation scores.

        Args:
            baseline_scores: Baseline dimension -> mean score mapping.
            current_scores: Current dimension -> mean score mapping.
            threshold: Optional override for absolute threshold.
            baseline_samples: Optional raw score arrays for statistical tests.
            current_samples: Optional raw score arrays for statistical tests.

        Returns:
            DriftResult summarizing all detected drifts.
        """
        threshold = threshold if threshold is not None else self.absolute_threshold

        dimensions_drifted = []
        deltas = {}
        p_values = {}

        all_dimensions = set(baseline_scores.keys()) | set(current_scores.keys())

        for dim in sorted(all_dimensions):
            baseline = baseline_scores.get(dim, 0.5)
            current = current_scores.get(dim, 0.5)
            delta = current - baseline
            deltas[dim] = delta

            # Check absolute drift
            absolute_drift = abs(delta) > threshold

            # Check relative drift (only for non-zero baselines)
            relative_drift = False
            if abs(baseline) > 0.001:
                relative_drift = abs(delta) / abs(baseline) > self.relative_threshold

            # Statistical test if raw samples available
            statistical_drift = False
            if baseline_samples and current_samples:
                p_value = self._mann_whitney_test(
                    baseline_samples.get(dim, []),
                    current_samples.get(dim, []),
                )
                p_values[dim] = p_value
                statistical_drift = p_value < 0.05

            if absolute_drift or relative_drift or statistical_drift:
                dimensions_drifted.append(dim)

        drift_detected = len(dimensions_drifted) > 0

        # Build detailed explanation
        if drift_detected:
            details_parts = []
            for dim in dimensions_drifted:
                delta = deltas[dim]
                direction = "decreased" if delta < 0 else "increased"
                details_parts.append(
                    f"{dim}: {direction} by {abs(delta):.3f} "
                    f"(baseline={baseline_scores.get(dim, 'N/A')}, "
                    f"current={current_scores.get(dim, 'N/A')})"
                )
            details = "; ".join(details_parts)
        else:
            max_delta = max(abs(v) for v in deltas.values()) if deltas else 0.0
            details = f"No significant drift detected (max delta: {max_delta:.4f})"

        result = DriftResult(
            drift_detected=drift_detected,
            dimensions_drifted=dimensions_drifted,
            baseline_scores=baseline_scores,
            current_scores=current_scores,
            deltas=deltas,
            p_values=p_values,
            threshold=threshold,
            details=details,
        )

        if drift_detected:
            logger.warning(
                "Drift detected",
                dimensions=dimensions_drifted,
                max_delta=max(abs(v) for v in deltas.values()),
            )
        else:
            logger.debug("No drift detected", details=details)

        return result

    def detect_distribution_drift(
        self,
        baseline_distribution: list[float],
        current_distribution: list[float],
        n_bins: int = 10,
    ) -> dict:
        """Detect drift in the overall score distribution shape.

        Uses PSI (Population Stability Index) to measure distribution drift.
        PSI < 0.1: No significant drift
        PSI 0.1-0.25: Moderate drift
        PSI > 0.25: Significant drift

        Args:
            baseline_distribution: Baseline score values.
            current_distribution: Current score values.
            n_bins: Number of bins for PSI calculation.

        Returns:
            Dict with PSI value and interpretation.
        """
        if len(baseline_distribution) < self.min_sample_size:
            return {"psi": 0.0, "interpretation": "insufficient_data"}
        if len(current_distribution) < self.min_sample_size:
            return {"psi": 0.0, "interpretation": "insufficient_data"}

        psi = self._calculate_psi(
            baseline_distribution, current_distribution, n_bins
        )

        if psi < 0.1:
            interpretation = "no_significant_drift"
        elif psi < 0.25:
            interpretation = "moderate_drift"
        else:
            interpretation = "significant_drift"

        logger.info(
            "Distribution drift analysis",
            psi=round(psi, 4),
            interpretation=interpretation,
        )

        return {"psi": round(psi, 4), "interpretation": interpretation}

    @staticmethod
    def _calculate_psi(
        expected: list[float],
        actual: list[float],
        n_bins: int = 10,
    ) -> float:
        """Calculate Population Stability Index (PSI).

        PSI = sum((actual% - expected%) * ln(actual% / expected%))
        """
        if not expected or not actual:
            return 0.0

        epsilon = 0.0001  # Avoid division by zero

        all_values = expected + actual
        min_val, max_val = min(all_values), max(all_values)

        if max_val == min_val:
            return 0.0

        bin_width = (max_val - min_val) / n_bins

        psi_sum = 0.0
        for i in range(n_bins):
            bin_start = min_val + i * bin_width
            bin_end = bin_start + bin_width

            if i == n_bins - 1:
                bin_end = max_val + epsilon

            expected_count = sum(1 for v in expected if bin_start <= v < bin_end)
            actual_count = sum(1 for v in actual if bin_start <= v < bin_end)

            expected_ratio = (expected_count / len(expected)) + epsilon
            actual_ratio = (actual_count / len(actual)) + epsilon

            psi_sum += (actual_ratio - expected_ratio) * (
                __import__("math").log(actual_ratio / expected_ratio)
            )

        return max(0.0, psi_sum)

    @staticmethod
    def _mann_whitney_test(
        sample_a: list[float],
        sample_b: list[float],
    ) -> float:
        """Perform Mann-Whitney U test (approximate p-value).

        A simplified implementation that returns an approximate p-value
        based on the z-score of the U statistic.

        Args:
            sample_a: First sample of scores.
            sample_b: Second sample of scores.

        Returns:
            Approximate two-tailed p-value.
        """
        import math

        if len(sample_a) < 2 or len(sample_b) < 2:
            return 1.0

        combined = [(v, 0) for v in sample_a] + [(v, 1) for v in sample_b]
        combined.sort(key=lambda x: x[0])

        # Assign ranks (average for ties)
        ranks = {}
        i = 0
        while i < len(combined):
            j = i
            while j < len(combined) and combined[j][0] == combined[i][0]:
                j += 1
            avg_rank = (i + j + 1) / 2.0
            for k in range(i, j):
                ranks[k] = avg_rank
            i = j

        # Sum ranks for group a
        rank_sum_a = sum(ranks[k] for k in range(len(combined)) if combined[k][1] == 0)
        n_a = len(sample_a)
        n_b = len(sample_b)

        # U statistic
        u = rank_sum_a - n_a * (n_a + 1) / 2.0

        # Mean and standard deviation of U under null hypothesis
        mean_u = n_a * n_b / 2.0
        std_u = math.sqrt(n_a * n_b * (n_a + n_b + 1) / 12.0)

        if std_u == 0:
            return 0.5

        z = (u - mean_u) / std_u

        # Approximate two-tailed p-value from z-score
        # Using the error function approximation
        p = 2.0 * (1.0 - _norm_cdf(abs(z)))

        return min(1.0, max(0.0, p))


def _norm_cdf(x: float) -> float:
    """Approximate standard normal CDF."""
    import math
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))
