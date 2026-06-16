"""Statistical analysis for A/B test results.

Provides Welch's t-test, Cohen's d effect size, confidence intervals,
Bonferroni correction for multiple comparisons, and sample size estimation.
"""

import numpy as np
from scipy import stats
from dataclasses import dataclass
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class ABResult:
    """Complete statistical comparison result between two variants."""
    variant_a_name: str
    variant_b_name: str
    mean_a: float
    mean_b: float
    std_a: float
    std_b: float
    n_a: int
    n_b: int
    t_statistic: float
    p_value: float
    significant: bool
    cohens_d: float
    effect_size_interpretation: str
    ci_95: tuple[float, float]
    winner: Optional[str]
    recommendation: str


class ABTestAnalyzer:
    """Statistical analysis for A/B test results.

    Supports:
    - Welch's t-test (unequal variance t-test)
    - Cohen's d effect size
    - 95% confidence intervals
    - Bonferroni correction for multiple comparisons
    - Required sample size estimation
    """

    def analyze(
        self,
        scores_a: list[float],
        scores_b: list[float],
        variant_a_name: str = "A",
        variant_b_name: str = "B",
        alpha: float = 0.05,
    ) -> ABResult:
        """Perform full statistical analysis comparing two variants.

        Performs:
            - Welch's t-test for significance
            - Cohen's d for effect size
            - 95% CI for mean difference
            - Determines winner if significant

        Args:
            scores_a: List of scores for variant A.
            scores_b: List of scores for variant B.
            variant_a_name: Label for variant A.
            variant_b_name: Label for variant B.
            alpha: Significance level (default 0.05).

        Returns:
            ABResult dataclass with complete analysis.

        Raises:
            ValueError: If either list has fewer than 2 elements.
        """
        if len(scores_a) < 2:
            raise ValueError(
                f"Variant '{variant_a_name}' has only {len(scores_a)} observations. "
                f"At least 2 are required for the t-test."
            )
        if len(scores_b) < 2:
            raise ValueError(
                f"Variant '{variant_b_name}' has only {len(scores_b)} observations. "
                f"At least 2 are required for the t-test."
            )

        arr_a = np.array(scores_a, dtype=np.float64)
        arr_b = np.array(scores_b, dtype=np.float64)

        n_a = len(arr_a)
        n_b = len(arr_b)
        mean_a = float(np.mean(arr_a))
        mean_b = float(np.mean(arr_b))
        std_a = float(np.std(arr_a, ddof=1))
        std_b = float(np.std(arr_b, ddof=1))

        # Welch's t-test (unequal variance)
        var_a = np.var(arr_a, ddof=1)
        var_b = np.var(arr_b, ddof=1)

        se_a = var_a / n_a
        se_b = var_b / n_b
        se_diff = np.sqrt(se_a + se_b)

        if se_diff == 0:
            t_statistic = 0.0
            p_value = 1.0
            df = n_a + n_b - 2  # fallback
        else:
            t_statistic = float((mean_a - mean_b) / se_diff)

            # Welch-Satterthwaite degrees of freedom
            df_num = (se_a + se_b) ** 2
            df_den = (se_a ** 2) / (n_a - 1) + (se_b ** 2) / (n_b - 1)

            if df_den == 0:
                df = n_a + n_b - 2
                p_value = 1.0
            else:
                df = df_num / df_den
                # Two-tailed p-value
                p_value = float(2 * stats.t.sf(abs(t_statistic), df))

        # Cohen's d effect size (using pooled standard deviation)
        pooled_std_sq = ((n_a - 1) * var_a + (n_b - 1) * var_b) / (n_a + n_b - 2)
        pooled_std = np.sqrt(pooled_std_sq)

        if pooled_std == 0:
            cohens_d = 0.0
        else:
            cohens_d = (mean_a - mean_b) / pooled_std

        cohens_d_abs = abs(cohens_d)
        effect_size_interpretation = self.interpret_cohens_d(cohens_d_abs)

        # 95% confidence interval for the difference in means
        ci_95 = self.confidence_interval(scores_a, scores_b, alpha=alpha)

        # Determine significance
        significant = p_value < alpha

        # Determine winner
        winner: Optional[str] = None
        recommendation: str = ""

        if significant:
            if mean_a > mean_b:
                winner = variant_a_name
                recommendation = (
                    f"Variant '{variant_a_name}' significantly outperforms "
                    f"'{variant_b_name}' (p={p_value:.4f}, d={cohens_d_abs:.3f}, "
                    f"{effect_size_interpretation}). "
                    f"Mean difference: {mean_a - mean_b:.4f}, "
                    f"95% CI: [{ci_95[0]:.4f}, {ci_95[1]:.4f}]. "
                    f"Recommend adopting '{variant_a_name}'."
                )
            else:
                winner = variant_b_name
                recommendation = (
                    f"Variant '{variant_b_name}' significantly outperforms "
                    f"'{variant_a_name}' (p={p_value:.4f}, d={cohens_d_abs:.3f}, "
                    f"{effect_size_interpretation}). "
                    f"Mean difference: {mean_b - mean_a:.4f}, "
                    f"95% CI: [{ci_95[0]:.4f}, {ci_95[1]:.4f}]. "
                    f"Recommend adopting '{variant_b_name}'."
                )
        else:
            recommendation = (
                f"No statistically significant difference between "
                f"'{variant_a_name}' (M={mean_a:.4f}, SD={std_a:.4f}) and "
                f"'{variant_b_name}' (M={mean_b:.4f}, SD={std_b:.4f}), "
                f"p={p_value:.4f}, d={cohens_d_abs:.3f} ({effect_size_interpretation}). "
                f"95% CI: [{ci_95[0]:.4f}, {ci_95[1]:.4f}]. "
                f"Consider collecting more data or testing different variants."
            )

        return ABResult(
            variant_a_name=variant_a_name,
            variant_b_name=variant_b_name,
            mean_a=mean_a,
            mean_b=mean_b,
            std_a=std_a,
            std_b=std_b,
            n_a=n_a,
            n_b=n_b,
            t_statistic=t_statistic,
            p_value=p_value,
            significant=significant,
            cohens_d=cohens_d_abs,
            effect_size_interpretation=effect_size_interpretation,
            ci_95=ci_95,
            winner=winner,
            recommendation=recommendation,
        )

    def compare_all_pairs(
        self,
        variant_scores: dict[str, list[float]],
        alpha: float = 0.05,
    ) -> list[ABResult]:
        """Compare all variant pairs and apply Bonferroni correction.

        Runs Welch's t-test between every pair of variants, then applies
        Bonferroni correction to adjust for multiple comparisons.

        Args:
            variant_scores: Dict mapping variant_name -> list of scores.
            alpha: Significance level (default 0.05).

        Returns:
            List of ABResult for each pair, with Bonferroni-corrected
            significance flags.
        """
        variant_names = sorted(variant_scores.keys())
        n_variants = len(variant_names)

        if n_variants < 2:
            logger.warning(
                "compare_all_pairs called with only %d variant(s); "
                "at least 2 are required for comparison",
                n_variants,
            )
            return []

        # Number of pairwise comparisons
        n_pairs = n_variants * (n_variants - 1) // 2

        # Collect raw results
        raw_results: list[ABResult] = []
        raw_p_values: list[float] = []

        for i in range(n_variants):
            for j in range(i + 1, n_variants):
                name_a = variant_names[i]
                name_b = variant_names[j]

                try:
                    result = self.analyze(
                        scores_a=variant_scores[name_a],
                        scores_b=variant_scores[name_b],
                        variant_a_name=name_a,
                        variant_b_name=name_b,
                        alpha=alpha,
                    )
                except ValueError as e:
                    logger.warning(
                        "Skipping comparison '%s' vs '%s': %s",
                        name_a,
                        name_b,
                        e,
                    )
                    continue

                raw_results.append(result)
                raw_p_values.append(result.p_value)

        if not raw_results:
            return []

        # Apply Bonferroni correction
        corrected_p_values = self.bonferroni_correction(raw_p_values)

        # Update results with corrected p-values and significance
        corrected_results: list[ABResult] = []
        for idx, result in enumerate(raw_results):
            corrected_p = corrected_p_values[idx]
            corrected_significant = corrected_p < alpha

            # Recompute winner and recommendation with corrected p-value
            if corrected_significant:
                if result.mean_a > result.mean_b:
                    updated_winner = result.variant_a_name
                    updated_recommendation = (
                        f"Variant '{result.variant_a_name}' significantly outperforms "
                        f"'{result.variant_b_name}' (Bonferroni-corrected "
                        f"p={corrected_p:.4f}, d={result.cohens_d:.3f}). "
                        f"Mean difference: {result.mean_a - result.mean_b:.4f}. "
                        f"Recommend adopting '{result.variant_a_name}'."
                    )
                else:
                    updated_winner = result.variant_b_name
                    updated_recommendation = (
                        f"Variant '{result.variant_b_name}' significantly outperforms "
                        f"'{result.variant_a_name}' (Bonferroni-corrected "
                        f"p={corrected_p:.4f}, d={result.cohens_d:.3f}). "
                        f"Mean difference: {result.mean_b - result.mean_a:.4f}. "
                        f"Recommend adopting '{result.variant_b_name}'."
                    )
            else:
                updated_winner = None
                updated_recommendation = (
                    f"No statistically significant difference after Bonferroni "
                    f"correction (corrected p={corrected_p:.4f}, raw p={result.p_value:.4f}, "
                    f"d={result.cohens_d:.3f}). "
                    f"Consider collecting more data."
                )

            corrected_results.append(ABResult(
                variant_a_name=result.variant_a_name,
                variant_b_name=result.variant_b_name,
                mean_a=result.mean_a,
                mean_b=result.mean_b,
                std_a=result.std_a,
                std_b=result.std_b,
                n_a=result.n_a,
                n_b=result.n_b,
                t_statistic=result.t_statistic,
                p_value=corrected_p,
                significant=corrected_significant,
                cohens_d=result.cohens_d,
                effect_size_interpretation=result.effect_size_interpretation,
                ci_95=result.ci_95,
                winner=updated_winner,
                recommendation=updated_recommendation,
            ))

        return corrected_results

    def interpret_cohens_d(self, d: float) -> str:
        """Interpret Cohen's d effect size.

        Interpretation thresholds:
            |d| < 0.2  : negligible
            0.2 <= |d| < 0.5 : small
            0.5 <= |d| < 0.8 : medium
            |d| >= 0.8 : large

        Args:
            d: Absolute value of Cohen's d.

        Returns:
            String interpretation (e.g., 'small', 'medium').
        """
        d_abs = abs(d)
        if d_abs < 0.2:
            return "negligible"
        elif d_abs < 0.5:
            return "small"
        elif d_abs < 0.8:
            return "medium"
        else:
            return "large"

    def bonferroni_correction(self, p_values: list[float]) -> list[float]:
        """Apply Bonferroni correction: multiply each p-value by number of tests.

        Corrected p-values are clamped to a maximum of 1.0.

        Args:
            p_values: List of raw p-values from multiple tests.

        Returns:
            List of Bonferroni-corrected p-values.
        """
        n_tests = len(p_values)
        if n_tests == 0:
            return []

        corrected = [min(p * n_tests, 1.0) for p in p_values]
        logger.debug(
            "Bonferroni correction applied to %d p-values (factor=%d)",
            n_tests,
            n_tests,
        )
        return corrected

    def required_sample_size(
        self,
        effect_size: float = 0.3,
        power: float = 0.8,
        alpha: float = 0.05,
    ) -> int:
        """Estimate required sample size per variant for desired power.

        Uses the formula for a two-sample two-tailed t-test:
            n = 2 * (z_{alpha/2} + z_{beta})^2 / effect_size^2

        where:
            z_{alpha/2} is the critical value for the significance level,
            z_{beta} is the critical value for the desired power,
            effect_size is Cohen's d (mean difference / pooled SD).

        Args:
            effect_size: The minimum effect size to detect (Cohen's d).
                Default 0.3 (small-medium).
            power: Desired statistical power (default 0.8 for 80%).
            alpha: Significance level (default 0.05).

        Returns:
            Required sample size per group (rounded up to nearest integer).
        """
        if effect_size <= 0:
            raise ValueError(f"Effect size must be positive, got {effect_size}")

        # z-score for alpha/2 (two-tailed)
        z_alpha = stats.norm.ppf(1 - alpha / 2)

        # z-score for power (one-tailed)
        z_beta = stats.norm.ppf(power)

        # Sample size formula
        n = 2 * (z_alpha + z_beta) ** 2 / (effect_size ** 2)

        sample_size = int(np.ceil(n))
        logger.info(
            "Required sample size: %d per group (effect_size=%.2f, power=%.0f%%, alpha=%.2f)",
            sample_size,
            effect_size,
            power * 100,
            alpha,
        )
        return sample_size

    def confidence_interval(
        self,
        scores_a: list[float],
        scores_b: list[float],
        alpha: float = 0.05,
    ) -> tuple[float, float]:
        """Calculate confidence interval for the difference in means.

        Uses Welch-Satterthwaite degrees of freedom (does not assume
        equal variances between groups).

        Args:
            scores_a: Scores for variant A.
            scores_b: Scores for variant B.
            alpha: Significance level (default 0.05 for 95% CI).

        Returns:
            Tuple of (lower_bound, upper_bound) for the mean difference
            (mean_a - mean_b).
        """
        arr_a = np.array(scores_a, dtype=np.float64)
        arr_b = np.array(scores_b, dtype=np.float64)

        n_a = len(arr_a)
        n_b = len(arr_b)

        if n_a < 2 or n_b < 2:
            raise ValueError(
                f"Both groups need at least 2 observations. "
                f"Got n_a={n_a}, n_b={n_b}."
            )

        mean_a = np.mean(arr_a)
        mean_b = np.mean(arr_b)
        mean_diff = mean_a - mean_b

        var_a = np.var(arr_a, ddof=1)
        var_b = np.var(arr_b, ddof=1)

        se_a = var_a / n_a
        se_b = var_b / n_b
        se_diff = np.sqrt(se_a + se_b)

        if se_diff == 0:
            return (float(mean_diff), float(mean_diff))

        # Welch-Satterthwaite degrees of freedom
        df_num = (se_a + se_b) ** 2
        df_den = (se_a ** 2) / (n_a - 1) + (se_b ** 2) / (n_b - 1)

        if df_den == 0:
            df = n_a + n_b - 2
        else:
            df = df_num / df_den

        # Critical value from t-distribution
        t_crit = stats.t.ppf(1 - alpha / 2, df)

        margin = t_crit * se_diff
        lower = mean_diff - margin
        upper = mean_diff + margin

        return (float(lower), float(upper))
