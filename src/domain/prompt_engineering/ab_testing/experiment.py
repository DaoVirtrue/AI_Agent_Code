"""A/B Experiment lifecycle management.

Manages the full lifecycle of prompt engineering A/B tests:
creation, user assignment, observation recording, stopping, and
statistical analysis of results.
"""

import uuid
import hashlib
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class ABResult:
    """Result of a completed A/B experiment."""
    experiment_id: uuid.UUID
    experiment_name: str
    status: str
    variants: dict  # variant_name -> {mean_score, std_score, count, win_rate, ...}
    winner: Optional[str]
    confidence: float
    recommendation: str
    p_values: dict[str, float]
    effect_sizes: dict[str, float]


class ABExperiment:
    """Manage A/B test lifecycle for prompt template variants.

    Supports creating experiments with multiple variants, deterministic
    user assignment via hashing, recording observations (scores, latency,
    token counts, cost), stopping experiments, and statistical analysis
    of results.
    """

    def __init__(self, db_session=None):
        """Initialize with an optional async SQLAlchemy session.

        Args:
            db_session: An AsyncSession for persistence; if None, operates
                in memory only via _active_experiments.
        """
        self.db = db_session
        self._active_experiments: dict[uuid.UUID, dict] = {}
        logger.info("ABExperiment manager initialized")

    async def create(
        self,
        name: str,
        template_id: uuid.UUID,
        variants: list[dict],
        traffic_split: dict[str, float],
        metrics: list[str],
        description: str = "",
        tenant_id: Optional[uuid.UUID] = None,
    ) -> dict:
        """Create a new A/B experiment.

        Args:
            name: Human-readable experiment name.
            template_id: The base prompt template being tested.
            variants: List of dicts with keys "name", "template_content",
                and optional "description".
            traffic_split: Dict mapping variant_name -> fraction (e.g. 0.5).
            metrics: List of metric names to track (e.g. ["score", "latency_ms"]).
            description: Optional longer description.
            tenant_id: Optional tenant scope.

        Returns:
            Experiment config dict with generated experiment_id.

        Raises:
            ValueError: If traffic_split values don't sum to ~1.0,
                if variants are empty, or if variant names don't match
                traffic_split keys.
        """
        # Validate traffic split sums to ~1.0
        total = sum(traffic_split.values())
        if not (0.99 <= total <= 1.01):
            raise ValueError(
                f"Traffic split values sum to {total:.4f}, expected ~1.0"
            )

        # Validate variants not empty
        if not variants:
            raise ValueError("At least one variant is required")

        variant_names = {v["name"] for v in variants}
        split_names = set(traffic_split.keys())

        # Check that traffic_split keys match variant names
        if variant_names != split_names:
            missing_in_variants = split_names - variant_names
            missing_in_split = variant_names - split_names
            msg_parts = []
            if missing_in_variants:
                msg_parts.append(
                    f"Traffic split references unknown variants: {missing_in_variants}"
                )
            if missing_in_split:
                msg_parts.append(
                    f"Variants without traffic allocation: {missing_in_split}"
                )
            raise ValueError("; ".join(msg_parts))

        experiment_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        experiment = {
            "experiment_id": experiment_id,
            "name": name,
            "template_id": template_id,
            "description": description,
            "tenant_id": tenant_id,
            "variants": variants,
            "traffic_split": traffic_split,
            "metrics": metrics,
            "status": "active",
            "created_at": now,
            "stopped_at": None,
            "observations": {name: [] for name in variant_names},
            "total_observations": 0,
            "variant_counts": {name: 0 for name in variant_names},
        }

        self._active_experiments[experiment_id] = experiment
        logger.info(
            "Created experiment '%s' (id=%s) with %d variants",
            name,
            experiment_id,
            len(variants),
        )
        return experiment

    async def assign_variant(self, user_id: str) -> str:
        """Deterministically assign a user to a variant using hash-based splitting.

        Uses SHA-256 of user_id concatenated with experiment_id, then maps
        the normalized hash value to a variant range based on configured
        traffic split proportions.

        Args:
            user_id: A unique identifier for the user/session.

        Returns:
            The name of the assigned variant.

        Raises:
            RuntimeError: If no active experiment is registered.
        """
        if not self._active_experiments:
            raise RuntimeError("No active experiments available for assignment")

        # Use the first (or only) active experiment
        active = [
            e for e in self._active_experiments.values() if e["status"] == "active"
        ]
        if not active:
            raise RuntimeError("No active experiments; all have been stopped")

        experiment = active[0]
        experiment_id = experiment["experiment_id"]

        # Deterministic hash
        hash_input = f"{user_id}:{experiment_id}"
        hash_digest = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()
        # Normalize to [0, 1)
        hash_int = int(hash_digest[:16], 16)
        normalized = hash_int / (16 ** 16)

        # Map to variant range
        cumulative = 0.0
        for variant_name, fraction in experiment["traffic_split"].items():
            cumulative += fraction
            if normalized < cumulative:
                return variant_name

        # Fallback (should not happen if fractions sum to 1.0)
        last_variant = list(experiment["traffic_split"].keys())[-1]
        return last_variant

    async def record_observation(
        self,
        experiment_id: uuid.UUID,
        variant_name: str,
        request_id: str,
        score: float,
        latency_ms: float = 0.0,
        token_count: int = 0,
        cost: float = 0.0,
        metadata: Optional[dict] = None,
    ) -> None:
        """Record a single observation for a variant in an experiment.

        Args:
            experiment_id: The experiment to record against.
            variant_name: The variant that was served.
            request_id: A unique ID for this request/observation.
            score: The primary evaluation score.
            latency_ms: Response latency in milliseconds.
            token_count: Number of tokens consumed.
            cost: Monetary cost of the request.
            metadata: Optional additional metadata dict.

        Raises:
            KeyError: If experiment_id or variant_name is not found.
            ValueError: If the experiment is not active.
        """
        experiment = self._active_experiments.get(experiment_id)
        if experiment is None:
            raise KeyError(f"Experiment {experiment_id} not found")

        if experiment["status"] != "active":
            raise ValueError(
                f"Experiment {experiment_id} is not active (status={experiment['status']})"
            )

        if variant_name not in experiment["observations"]:
            raise KeyError(
                f"Variant '{variant_name}' not found in experiment {experiment_id}"
            )

        observation = {
            "request_id": request_id,
            "score": score,
            "latency_ms": latency_ms,
            "token_count": token_count,
            "cost": cost,
            "metadata": metadata or {},
            "timestamp": datetime.now(timezone.utc),
        }

        experiment["observations"][variant_name].append(observation)
        experiment["variant_counts"][variant_name] += 1
        experiment["total_observations"] += 1

        logger.debug(
            "Recorded observation for variant '%s' in experiment %s (score=%.3f)",
            variant_name,
            experiment_id,
            score,
        )

    async def stop(self, experiment_id: uuid.UUID) -> ABResult:
        """Stop an active experiment, compute final results, and return ABResult.

        Args:
            experiment_id: The experiment to stop.

        Returns:
            ABResult with statistical analysis results.

        Raises:
            KeyError: If experiment_id is not found.
            ValueError: If the experiment is already stopped.
        """
        experiment = self._active_experiments.get(experiment_id)
        if experiment is None:
            raise KeyError(f"Experiment {experiment_id} not found")

        if experiment["status"] != "active":
            raise ValueError(
                f"Experiment {experiment_id} is already stopped"
            )

        experiment["status"] = "stopped"
        experiment["stopped_at"] = datetime.now(timezone.utc)

        logger.info("Stopped experiment '%s' (id=%s)", experiment["name"], experiment_id)

        return await self.get_results(experiment_id)

    async def get_results(self, experiment_id: uuid.UUID) -> ABResult:
        """Get statistical analysis results for an experiment.

        Uses Welch's t-test between all variant pairs to determine
        statistical significance. The winner is determined by the variant
        with the highest mean score, provided it is statistically
        significantly better than all others at alpha=0.05.

        Args:
            experiment_id: The experiment to analyze.

        Returns:
            ABResult with complete statistical analysis.

        Raises:
            KeyError: If experiment_id is not found.
        """
        experiment = self._active_experiments.get(experiment_id)
        if experiment is None:
            raise KeyError(f"Experiment {experiment_id} not found")

        observations = experiment["observations"]
        variant_names = list(observations.keys())

        # Compute per-variant statistics
        variants_stats: dict[str, dict] = {}
        all_p_values: dict[str, float] = {}
        all_effect_sizes: dict[str, float] = {}

        for name in variant_names:
            scores = [o["score"] for o in observations[name]]
            n = len(scores)
            if n == 0:
                variants_stats[name] = {
                    "mean_score": 0.0,
                    "std_score": 0.0,
                    "count": 0,
                    "win_rate": 0.0,
                    "median_score": 0.0,
                    "min_score": 0.0,
                    "max_score": 0.0,
                }
            else:
                arr = np.array(scores, dtype=np.float64)
                variants_stats[name] = {
                    "mean_score": float(np.mean(arr)),
                    "std_score": float(np.std(arr, ddof=1)) if n > 1 else 0.0,
                    "count": n,
                    "win_rate": 0.0,
                    "median_score": float(np.median(arr)),
                    "min_score": float(np.min(arr)),
                    "max_score": float(np.max(arr)),
                }

        # Pairwise Welch's t-test (and effect size)
        all_scores: dict[str, list[float]] = {
            name: [o["score"] for o in observations[name]]
            for name in variant_names
        }

        for i, name_a in enumerate(variant_names):
            for name_b in variant_names[i + 1 :]:
                scores_a = all_scores[name_a]
                scores_b = all_scores[name_b]
                pair_key = f"{name_a}_vs_{name_b}"

                if len(scores_a) < 2 or len(scores_b) < 2:
                    all_p_values[pair_key] = 1.0
                    all_effect_sizes[pair_key] = 0.0
                    continue

                arr_a = np.array(scores_a, dtype=np.float64)
                arr_b = np.array(scores_b, dtype=np.float64)

                # Welch's t-test
                mean_a = np.mean(arr_a)
                mean_b = np.mean(arr_b)
                var_a = np.var(arr_a, ddof=1)
                var_b = np.var(arr_b, ddof=1)
                n_a = len(arr_a)
                n_b = len(arr_b)

                se_a = var_a / n_a
                se_b = var_b / n_b
                se_diff = np.sqrt(se_a + se_b)

                if se_diff == 0:
                    t_stat = 0.0
                    p_value = 1.0
                else:
                    t_stat = (mean_a - mean_b) / se_diff
                    # Welch-Satterthwaite degrees of freedom
                    df_num = (se_a + se_b) ** 2
                    df_den = (se_a ** 2) / (n_a - 1) + (se_b ** 2) / (n_b - 1)
                    if df_den == 0:
                        p_value = 1.0
                    else:
                        df = df_num / df_den
                        # Two-tailed p-value from t-distribution
                        from scipy import stats as scipy_stats
                        p_value = 2 * scipy_stats.t.sf(abs(t_stat), df)

                all_p_values[pair_key] = float(p_value)

                # Cohen's d effect size
                pooled_std = np.sqrt(((n_a - 1) * var_a + (n_b - 1) * var_b) / (n_a + n_b - 2))
                if pooled_std == 0:
                    cohens_d = 0.0
                else:
                    cohens_d = (mean_a - mean_b) / pooled_std
                all_effect_sizes[pair_key] = float(abs(cohens_d))

        # Bonferroni correction on p-values
        n_comparisons = len(all_p_values)
        p_values_list = list(all_p_values.values())
        corrected_p = []
        for p in p_values_list:
            corrected_p.append(min(p * n_comparisons, 1.0))
        for idx, key in enumerate(all_p_values.keys()):
            all_p_values[key] = corrected_p[idx]

        # Determine winner: variant with highest mean that beats all others
        variant_means = {
            name: variants_stats[name]["mean_score"] for name in variant_names
        }
        candidates = sorted(variant_means, key=variant_means.get, reverse=True)

        winner: Optional[str] = None
        confidence: float = 0.0
        recommendation: str = ""

        best = candidates[0]
        best_mean = variant_means[best]

        # Check if best is significantly better than all others
        all_beats = True
        min_confidence = 1.0
        for other in candidates[1:]:
            pair_key = f"{best}_vs_{other}"
            rev_key = f"{other}_vs_{best}"
            p_val = all_p_values.get(pair_key, all_p_values.get(rev_key, 1.0))
            if p_val >= 0.05:
                all_beats = False
            min_confidence = min(min_confidence, 1.0 - p_val)

        if all_beats and len(candidates) > 1:
            winner = best
            confidence = min_confidence
            recommendation = (
                f"Variant '{best}' is the winner with mean score {best_mean:.3f}. "
                f"Statistically significant at p < 0.05 (Bonferroni corrected). "
                f"Confidence: {confidence:.2%}."
            )
        elif len(candidates) == 1:
            recommendation = (
                f"Only one variant '{best}' present. "
                f"Add more variants for meaningful comparison."
            )
        else:
            # Check if there's a tie or no clear winner
            second_best = candidates[1]
            second_mean = variant_means[second_best]
            if best_mean > second_mean:
                pair_key = f"{best}_vs_{second_best}"
                rev_key = f"{second_best}_vs_{best}"
                p_val_pair = all_p_values.get(pair_key, all_p_values.get(rev_key, 1.0))
                recommendation = (
                    f"Variant '{best}' has the highest mean score ({best_mean:.3f}), "
                    f"but the difference from '{second_best}' ({second_mean:.3f}) "
                    f"is not statistically significant (p={p_val_pair:.4f}). "
                    f"Consider collecting more data."
                )
            else:
                recommendation = (
                    f"No clear winner. Multiple variants have similar performance. "
                    f"Best mean: '{best}' = {best_mean:.3f}. "
                    f"Consider collecting more data or refining variants."
                )

        # Compute win rates (how often each variant has the highest score per comparison window)
        # Simple approach: fraction of observations where this variant scored above the global median
        all_scores_flat = []
        for name in variant_names:
            all_scores_flat.extend([o["score"] for o in observations[name]])
        if all_scores_flat:
            global_median = float(np.median(np.array(all_scores_flat, dtype=np.float64)))
            for name in variant_names:
                obs_list = observations[name]
                if obs_list:
                    wins = sum(1 for o in obs_list if o["score"] > global_median)
                    variants_stats[name]["win_rate"] = (
                        wins / len(obs_list) if obs_list else 0.0
                    )

        return ABResult(
            experiment_id=experiment_id,
            experiment_name=experiment["name"],
            status=experiment["status"],
            variants=variants_stats,
            winner=winner,
            confidence=confidence,
            recommendation=recommendation,
            p_values=all_p_values,
            effect_sizes=all_effect_sizes,
        )

    async def list_experiments(self, status: Optional[str] = None) -> list[dict]:
        """List experiments, optionally filtered by status.

        Args:
            status: Filter by 'active' or 'stopped'. If None, returns all.

        Returns:
            List of experiment summary dicts.
        """
        result = []
        for exp_id, exp in self._active_experiments.items():
            if status is not None and exp["status"] != status:
                continue
            result.append({
                "experiment_id": str(exp_id),
                "name": exp["name"],
                "status": exp["status"],
                "variant_count": len(exp["variants"]),
                "total_observations": exp["total_observations"],
                "created_at": exp["created_at"].isoformat(),
                "stopped_at": (
                    exp["stopped_at"].isoformat() if exp["stopped_at"] else None
                ),
            })
        return result

    async def delete_experiment(self, experiment_id: uuid.UUID) -> bool:
        """Delete an experiment and its data.

        Args:
            experiment_id: The experiment to delete.

        Returns:
            True if the experiment was deleted, False if not found.
        """
        if experiment_id in self._active_experiments:
            name = self._active_experiments[experiment_id]["name"]
            del self._active_experiments[experiment_id]
            logger.info("Deleted experiment '%s' (id=%s)", name, experiment_id)
            return True
        logger.warning("Attempted to delete non-existent experiment %s", experiment_id)
        return False
