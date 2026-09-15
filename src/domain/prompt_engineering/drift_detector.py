"""
Distribution drift detection for prompt performance scores.

Uses the two-sample Kolmogorov-Smirnov test to compare current score
distributions against stored baselines. Tracks trends over time with
rolling windows.

Typical use: monitor if a prompt's quality is degrading over time,
which may indicate model changes, data distribution shift, or
prompt template drift.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import numpy as np
from scipy import stats

logger = logging.getLogger(__name__)


@dataclass
class DriftResult:
    """Result of a drift detection test.

    Attributes:
        prompt_name: Name of the prompt being monitored.
        drift_detected: True if drift was detected (p < alpha).
        ks_statistic: The KS test statistic.
        p_value: The p-value from the KS test.
        baseline_mean: Mean of the baseline score distribution.
        current_mean: Mean of the current score distribution.
        mean_shift: Difference between current and baseline means.
        baseline_std: Standard deviation of the baseline distribution.
        current_std: Standard deviation of the current distribution.
        sample_size_baseline: Number of samples in the baseline.
        sample_size_current: Number of samples in the current window.
        timestamp: ISO-8601 timestamp of when the test was run.
    """

    prompt_name: str
    drift_detected: bool
    ks_statistic: float
    p_value: float
    baseline_mean: float
    current_mean: float
    mean_shift: float
    baseline_std: float
    current_std: float
    sample_size_baseline: int
    sample_size_current: int
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class PromptDriftDetector:
    """Detect distribution drift in prompt performance scores.

    Uses the two-sample Kolmogorov-Smirnov test to compare current
    score distributions against stored baselines. Tracks trends
    over time with rolling windows.

    Typical use: monitor if a prompt's quality is degrading over time,
    which may indicate model changes, data distribution shift, or
    prompt template drift.

    Usage::

        detector = PromptDriftDetector()
        detector.add_baseline("greeting_prompt", [0.85, 0.92, 0.88, ...])

        # Later, check for drift:
        result = detector.detect("greeting_prompt", [0.72, 0.68, 0.75, ...])
        if result.drift_detected:
            print(f"Drift detected! p={result.p_value:.4f}, "
                  f"mean shift={result.mean_shift:.3f}")
    """

    # Minimum samples required for a valid statistical test
    MIN_SAMPLES_BASELINE: int = 10
    MIN_SAMPLES_CURRENT: int = 5

    def __init__(self) -> None:
        """Initialize baseline storage and trend storage."""
        self._baselines: dict[str, np.ndarray] = {}
        self._trends: dict[str, list[dict[str, Any]]] = defaultdict(list)
        logger.info("PromptDriftDetector initialized")

    # ------------------------------------------------------------------
    # Baseline management
    # ------------------------------------------------------------------

    def add_baseline(self, prompt_name: str, scores: list[float]) -> None:
        """Store baseline score distribution for a prompt.

        Overwrites any existing baseline for the same prompt name.
        Scores should represent the expected/"good" performance distribution
        for this prompt.

        Args:
            prompt_name: Unique name identifying the prompt.
            scores: List of numeric performance scores to use as baseline.

        Raises:
            ValueError: If scores list is empty.
        """
        if not scores:
            raise ValueError(
                f"Cannot set baseline for {prompt_name!r}: scores list is empty"
            )

        arr = np.array(scores, dtype=np.float64)
        self._baselines[prompt_name] = arr

        logger.info(
            "Baseline set for %r: %d samples, mean=%.4f, std=%.4f",
            prompt_name,
            len(arr),
            float(np.mean(arr)),
            float(np.std(arr)),
        )

    def clear_baseline(self, prompt_name: str) -> None:
        """Remove baseline for a prompt.

        Args:
            prompt_name: The name of the prompt whose baseline should be removed.
        """
        if prompt_name in self._baselines:
            del self._baselines[prompt_name]
            logger.info("Cleared baseline for %r", prompt_name)
        else:
            logger.debug("No baseline to clear for %r", prompt_name)

    def list_monitored_prompts(self) -> list[str]:
        """Return list of prompts with baselines stored.

        Returns:
            Sorted list of prompt names that have baselines.
        """
        return sorted(self._baselines.keys())

    # ------------------------------------------------------------------
    # Drift detection
    # ------------------------------------------------------------------

    def detect(
        self,
        prompt_name: str,
        current_scores: list[float],
        alpha: float = 0.05,
    ) -> DriftResult:
        """Compare current scores against baseline using two-sample KS-test.

        The Kolmogorov-Smirnov test is non-parametric and tests whether
        two samples are drawn from the same distribution. A small p-value
        (< alpha) indicates the current scores have likely drifted from
        the baseline.

        Args:
            prompt_name: The prompt to check for drift.
            current_scores: Recent performance scores to compare against baseline.
            alpha: Significance level for the test (default 0.05).

        Returns:
            DriftResult with full statistics.

        Raises:
            ValueError: If no baseline exists for the prompt, or if sample sizes
                are too small for a reliable test.
        """
        if prompt_name not in self._baselines:
            raise ValueError(
                f"No baseline found for prompt {prompt_name!r}. "
                f"Call add_baseline() first."
            )

        baseline = self._baselines[prompt_name]
        current = np.array(current_scores, dtype=np.float64)

        if len(baseline) < self.MIN_SAMPLES_BASELINE:
            raise ValueError(
                f"Baseline for {prompt_name!r} has only {len(baseline)} samples; "
                f"need at least {self.MIN_SAMPLES_BASELINE} for a reliable test."
            )

        if len(current) < self.MIN_SAMPLES_CURRENT:
            raise ValueError(
                f"Current scores for {prompt_name!r} has only {len(current)} samples; "
                f"need at least {self.MIN_SAMPLES_CURRENT} for a reliable test."
            )

        # Run KS test
        ks_stat, p_value = stats.ks_2samp(baseline, current)

        baseline_mean = float(np.mean(baseline))
        current_mean = float(np.mean(current))
        baseline_std = float(np.std(baseline, ddof=1))
        current_std = float(np.std(current, ddof=1))
        mean_shift = current_mean - baseline_mean
        drift_detected = p_value < alpha

        result = DriftResult(
            prompt_name=prompt_name,
            drift_detected=drift_detected,
            ks_statistic=float(ks_stat),
            p_value=float(p_value),
            baseline_mean=baseline_mean,
            current_mean=current_mean,
            mean_shift=float(mean_shift),
            baseline_std=baseline_std,
            current_std=current_std,
            sample_size_baseline=len(baseline),
            sample_size_current=len(current),
        )

        if drift_detected:
            logger.warning(
                "DRIFT DETECTED for %r: KS=%.4f, p=%.6f, "
                "mean_shift=%.4f (%.2f -> %.2f)",
                prompt_name,
                ks_stat,
                p_value,
                mean_shift,
                baseline_mean,
                current_mean,
            )
        else:
            logger.debug(
                "No drift for %r: KS=%.4f, p=%.4f (alpha=%.2f)",
                prompt_name,
                ks_stat,
                p_value,
                alpha,
            )

        return result

    # ------------------------------------------------------------------
    # Trend tracking
    # ------------------------------------------------------------------

    def update_trend(self, prompt_name: str, scores: list[float]) -> None:
        """Record a new observation point for trend tracking.

        Stores timestamp, mean, std, count, and the raw scores for
        later rolling-window analysis.

        Args:
            prompt_name: The prompt to record an observation for.
            scores: List of performance scores from this observation.
        """
        if not scores:
            return

        arr = np.array(scores, dtype=np.float64)
        entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mean": float(np.mean(arr)),
            "std": float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0,
            "count": len(arr),
            "min": float(np.min(arr)),
            "max": float(np.max(arr)),
            "scores": list(arr),
        }
        self._trends[prompt_name].append(entry)
        logger.debug(
            "Trend updated for %r: mean=%.4f, count=%d (total observations: %d)",
            prompt_name,
            entry["mean"],
            entry["count"],
            len(self._trends[prompt_name]),
        )

    def get_trend(
        self, prompt_name: str, window: int = 30
    ) -> list[dict[str, Any]]:
        """Get rolling window trend of scores for a prompt.

        Summarizes trend observations into rolling windows of the given
        size. Each window entry contains aggregated statistics.

        Args:
            prompt_name: The prompt to retrieve trends for.
            window: Number of recent observations to include in the window.

        Returns:
            List of dicts with keys: timestamp, mean, std, count, window_start,
            window_end, for each rolling window. Most recent first.
        """
        observations = self._trends.get(prompt_name, [])
        if not observations:
            return []

        recent = observations[-window:]
        result: list[dict[str, Any]] = [
            {
                "timestamp": obs["timestamp"],
                "mean": obs["mean"],
                "std": obs["std"],
                "count": obs["count"],
                "min": obs.get("min"),
                "max": obs.get("max"),
            }
            for obs in recent
        ]
        # Most recent first
        result.reverse()
        return result

    # ------------------------------------------------------------------
    # Statistics helpers
    # ------------------------------------------------------------------

    def get_baseline_stats(self, prompt_name: str) -> Optional[dict[str, Any]]:
        """Get summary statistics for a baseline.

        Args:
            prompt_name: The prompt to get stats for.

        Returns:
            Dict with mean, std, min, max, count, median, q25, q75,
            or None if no baseline exists.
        """
        if prompt_name not in self._baselines:
            return None

        arr = self._baselines[prompt_name]
        return {
            "prompt_name": prompt_name,
            "mean": float(np.mean(arr)),
            "std": float(np.std(arr, ddof=1)),
            "min": float(np.min(arr)),
            "max": float(np.max(arr)),
            "count": len(arr),
            "median": float(np.median(arr)),
            "q25": float(np.percentile(arr, 25)),
            "q75": float(np.percentile(arr, 75)),
        }

    def compare_all_prompts(
        self, current_scores_map: dict[str, list[float]], alpha: float = 0.05
    ) -> dict[str, DriftResult]:
        """Run drift detection for multiple prompts at once.

        Args:
            current_scores_map: Dict mapping prompt_name -> list of current scores.
            alpha: Significance level for the KS test.

        Returns:
            Dict mapping prompt_name -> DriftResult. Prompts without baselines
            are skipped with a warning log.
        """
        results: dict[str, DriftResult] = {}
        for name, scores in current_scores_map.items():
            if name not in self._baselines:
                logger.warning(
                    "Skipping %r: no baseline available", name
                )
                continue
            try:
                results[name] = self.detect(name, scores, alpha=alpha)
            except ValueError as exc:
                logger.warning("Cannot detect drift for %r: %s", name, exc)
        return results
