"""Iteration closed loop: evaluate -> diagnose -> optimize -> verify cycle for RAG optimization."""

import copy
from dataclasses import dataclass, field
from typing import Optional, Callable

from src.evaluation.six_dimension import SixDimensionEvaluator, EvaluationResult
from src.evaluation.drift_detector import DriftDetector, DriftResult
from src.monitoring.logging_setup import get_logger

logger = get_logger(__name__)


@dataclass
class IterationSnapshot:
    """Snapshot of the pipeline state at one iteration."""

    iteration: int
    overall_score: float
    dimension_scores: dict[str, float]
    improvement: float = 0.0  # vs previous iteration
    configuration: dict = field(default_factory=dict)
    notes: str = ""


@dataclass
class OptimizationResult:
    """Result of the iteration closed loop optimization."""

    iterations: int
    converged: bool
    best_score: float
    best_configuration: dict
    improvement: float  # From initial to best
    snapshots: list[IterationSnapshot]
    drift_detected: bool = False
    drift_details: Optional[DriftResult] = None
    total_time_seconds: float = 0.0

    @property
    def summary(self) -> dict:
        """Get a summary dict of the optimization result."""
        return {
            "iterations": self.iterations,
            "converged": self.converged,
            "best_score": self.best_score,
            "improvement": self.improvement,
            "drift_detected": self.drift_detected,
            "total_time_seconds": self.total_time_seconds,
            "score_trajectory": [s.overall_score for s in self.snapshots],
        }


class IterationClosedLoop:
    """Closed-loop optimizer for RAG pipelines.

    The cycle:
    1. EVALUATE: Run the pipeline on the golden dataset, collect scores
    2. DIAGNOSE: Identify weak dimensions and failure modes
    3. OPTIMIZE: Adjust pipeline parameters to address weaknesses
    4. VERIFY: Re-evaluate and check for improvement

    The loop continues until:
    - Maximum iterations reached
    - Convergence (improvement < threshold for N consecutive iterations)
    - No more tunable parameters available
    """

    def __init__(
        self,
        evaluator: Optional[SixDimensionEvaluator] = None,
        drift_detector: Optional[DriftDetector] = None,
        convergence_threshold: float = 0.01,
        convergence_patience: int = 3,
        backtrack_on_degradation: bool = True,
    ):
        """Initialize the iteration closed loop.

        Args:
            evaluator: Six-dimension evaluator instance.
            drift_detector: Drift detector for monitoring score degradation.
            convergence_threshold: Minimum improvement to consider progress.
            convergence_patience: Number of no-improvement iterations before stopping.
            backtrack_on_degradation: If True, revert to best config when scores drop.
        """
        self.evaluator = evaluator or SixDimensionEvaluator()
        self.drift_detector = drift_detector or DriftDetector()
        self.convergence_threshold = convergence_threshold
        self.convergence_patience = convergence_patience
        self.backtrack_on_degradation = backtrack_on_degradation

    async def run(
        self,
        pipeline,
        dataset: list,
        max_iterations: int = 10,
        initial_config: Optional[dict] = None,
        on_iteration: Optional[Callable] = None,
    ) -> OptimizationResult:
        """Run the closed-loop optimization.

        Args:
            pipeline: The RAG pipeline to optimize (must have evaluate and configure methods).
            dataset: Golden dataset of examples for evaluation.
            max_iterations: Maximum number of optimize cycles.
            initial_config: Optional initial pipeline configuration.
            on_iteration: Optional callback (snapshot) called after each iteration.

        Returns:
            OptimizationResult summarizing the entire optimization run.
        """
        import time as time_module

        start_time = time_module.monotonic()
        snapshots: list[IterationSnapshot] = []
        best_score = 0.0
        best_config = initial_config or {}
        patience_counter = 0
        previous_score = 0.0
        baseline_scores = None

        # Get initial configuration
        if initial_config:
            pipeline.configure(**initial_config)

        current_config = self._get_pipeline_config(pipeline)

        for iteration in range(1, max_iterations + 1):
            logger.info(
                "Iteration started",
                iteration=iteration,
                max_iterations=max_iterations,
            )

            # STEP 1: EVALUATE
            eval_results = await self._evaluate_pipeline(pipeline, dataset)

            if not eval_results:
                logger.error("No evaluation results produced")
                break

            overall_score = statistics.mean(r.overall_score for r in eval_results)
            dim_scores = self._aggregate_dimensions(eval_results)

            # STEP 2: DIAGNOSE
            diagnosis = await self._diagnose(eval_results, baseline_scores)

            if baseline_scores is None:
                baseline_scores = dim_scores
                previous_score = overall_score

            # Check for drift if we have a baseline
            drift_result = None
            if baseline_scores and iteration > 1:
                drift_result = self.drift_detector.detect(
                    baseline_scores=baseline_scores,
                    current_scores=dim_scores,
                )

            # STEP 3: OPTIMIZE
            if diagnosis["can_optimize"]:
                optimization_params = self._generate_optimization_params(
                    diagnosis["weak_dimensions"],
                    current_config,
                )
                pipeline.configure(**optimization_params)
                current_config = self._get_pipeline_config(pipeline)
            else:
                logger.info("No optimization needed, all dimensions healthy")

            # STEP 4: VERIFY
            improvement = overall_score - previous_score

            snapshot = IterationSnapshot(
                iteration=iteration,
                overall_score=round(overall_score, 4),
                dimension_scores={k: round(v, 4) for k, v in dim_scores.items()},
                improvement=round(improvement, 4),
                configuration=copy.deepcopy(current_config),
                notes=diagnosis.get("summary", ""),
            )
            snapshots.append(snapshot)

            if on_iteration:
                on_iteration(snapshot)

            # Track best
            if overall_score > best_score:
                best_score = overall_score
                best_config = copy.deepcopy(current_config)
                patience_counter = 0
                logger.info(
                    "New best score",
                    iteration=iteration,
                    score=round(overall_score, 4),
                )
            elif improvement <= self.convergence_threshold:
                patience_counter += 1
                logger.debug(
                    "No significant improvement",
                    iteration=iteration,
                    patience=patience_counter,
                    patience_limit=self.convergence_patience,
                )

                # Backtrack if degrading significantly
                if improvement < -0.02 and self.backtrack_on_degradation:
                    logger.warning(
                        "Score degraded, backtracking to best config",
                        iteration=iteration,
                        current=round(overall_score, 4),
                        best=round(best_score, 4),
                    )
                    pipeline.configure(**best_config)
                    current_config = copy.deepcopy(best_config)
            else:
                patience_counter = 0

            # Check convergence
            if patience_counter >= self.convergence_patience:
                logger.info(
                    "Convergence reached",
                    iteration=iteration,
                    patience=self.convergence_patience,
                )
                break

            previous_score = overall_score

        # Final evaluation with best config
        pipeline.configure(**best_config)

        elapsed = time_module.monotonic() - start_time

        result = OptimizationResult(
            iterations=len(snapshots),
            converged=patience_counter >= self.convergence_patience,
            best_score=round(best_score, 4),
            best_configuration=best_config,
            improvement=round(best_score - (snapshots[0].overall_score if snapshots else 0), 4),
            snapshots=snapshots,
            drift_detected=drift_result.drift_detected if drift_result else False,
            drift_details=drift_result,
            total_time_seconds=round(elapsed, 2),
        )

        logger.info(
            "Optimization complete",
            iterations=result.iterations,
            converged=result.converged,
            best_score=result.best_score,
            improvement=result.improvement,
            total_time_seconds=result.total_time_seconds,
        )

        return result

    async def _evaluate_pipeline(
        self,
        pipeline,
        dataset: list,
    ) -> list[EvaluationResult]:
        """Run the pipeline on the dataset and return evaluation results."""
        results = []

        for example in dataset:
            try:
                query = example.query if hasattr(example, 'query') else example.get("query", "")
                expected = example.expected_answer if hasattr(example, 'expected_answer') else example.get("expected_answer", "")
                contexts = example.contexts if hasattr(example, 'contexts') else example.get("contexts", [])

                # Run pipeline
                pipeline_result = await pipeline.process(query, contexts=contexts)

                # Evaluate
                eval_result = await self.evaluator.evaluate(
                    query=query,
                    answer=pipeline_result.answer,
                    contexts=contexts,
                    response_time=pipeline_result.latency_ms,
                    cost=pipeline_result.cost_usd,
                    expected_answer=expected,
                )
                results.append(eval_result)

            except Exception as e:
                logger.error(
                    "Evaluation failed for example",
                    error=str(e),
                    query=query[:100],
                )

        return results

    async def _diagnose(
        self,
        eval_results: list[EvaluationResult],
        baseline_scores: Optional[dict[str, float]] = None,
    ) -> dict:
        """Diagnose which dimensions need improvement.

        Returns:
            Dict with weak_dimensions, failure modes, and optimization suggestions.
        """
        if not eval_results:
            return {"can_optimize": False, "weak_dimensions": [], "summary": "No results"}

        # Aggregate scores by dimension
        dim_scores = self._aggregate_dimensions(eval_results)

        # Identify weak dimensions (score < 0.7)
        weak = []
        strong = []
        for dim, score in dim_scores.items():
            if score < 0.7:
                weak.append({"dimension": dim, "score": score, "gap": 0.7 - score})
            else:
                strong.append({"dimension": dim, "score": score})

        weak.sort(key=lambda x: x["gap"], reverse=True)

        # Check degradation vs baseline
        degraded = []
        if baseline_scores:
            for dim, score in dim_scores.items():
                baseline = baseline_scores.get(dim, score)
                if baseline - score > 0.03:
                    degraded.append({
                        "dimension": dim,
                        "previous": baseline,
                        "current": score,
                        "drop": baseline - score,
                    })

        # Analyze failure patterns
        low_accuracy_examples = [
            r for r in eval_results
            if any(d.name == "accuracy" and d.score < 0.5 for d in r.dimensions)
        ]
        hallucination_examples = [
            r for r in eval_results
            if any(d.name == "faithfulness" and d.score < 0.5 for d in r.dimensions)
        ]

        diagnosis = {
            "can_optimize": len(weak) > 0,
            "weak_dimensions": weak,
            "healthy_dimensions": strong,
            "degraded_from_baseline": degraded,
            "failure_patterns": {
                "low_accuracy_count": len(low_accuracy_examples),
                "hallucination_count": len(hallucination_examples),
            },
            "summary": self._generate_diagnosis_summary(weak, degraded),
        }

        return diagnosis

    def _generate_optimization_params(
        self,
        weak_dimensions: list[dict],
        current_config: dict,
    ) -> dict:
        """Generate parameter adjustments to address weak dimensions.

        Maps diagnosis findings to concrete pipeline parameter changes.
        """
        params = dict(current_config)

        for weak in weak_dimensions:
            dim = weak["dimension"]

            if dim == "accuracy":
                # Increase context retrieval, lower temperature
                params["top_k"] = params.get("top_k", 10) + 5
                params["temperature"] = max(0.0, params.get("temperature", 0.3) - 0.1)
                params["rerank"] = True

            elif dim == "relevance":
                # Improve retrieval strategy
                params["retrieval_strategy"] = "hybrid"
                params["min_relevance_score"] = max(0.0, params.get("min_relevance_score", 0.5) + 0.1)

            elif dim == "faithfulness":
                # Reduce hallucinations: more contexts, stricter grounding
                params["top_k"] = params.get("top_k", 10) + 3
                params["temperature"] = max(0.0, params.get("temperature", 0.3) - 0.2)
                params["grounding_strictness"] = params.get("grounding_strictness", 0.5) + 0.2

            elif dim == "fluency":
                # Increase temperature slightly for more natural output
                params["temperature"] = min(1.5, params.get("temperature", 0.5) + 0.1)

            elif dim == "latency":
                # Enable caching, reduce context count
                params["use_cache"] = True
                params["top_k"] = max(3, params.get("top_k", 10) - 3)

            elif dim == "cost":
                # Use cheaper model, fewer contexts
                params["model"] = params.get("fallback_model", params.get("model", "gpt-4o"))
                params["top_k"] = max(3, params.get("top_k", 10) - 2)

        logger.debug("Generated optimization params", params=params)
        return params

    def _aggregate_dimensions(
        self,
        results: list[EvaluationResult],
    ) -> dict[str, float]:
        """Aggregate dimension scores across evaluation results."""
        import statistics

        if not results:
            return {}

        dim_values: dict[str, list[float]] = {}
        for result in results:
            for dim in result.dimensions:
                dim_values.setdefault(dim.name, []).append(dim.score)

        return {
            dim: statistics.mean(scores)
            for dim, scores in dim_values.items()
        }

    def _generate_diagnosis_summary(
        self,
        weak: list[dict],
        degraded: list[dict],
    ) -> str:
        """Generate a human-readable diagnosis summary."""
        parts = []

        if weak:
            weak_names = [f"{w['dimension']}({w['score']:.2f})" for w in weak[:3]]
            parts.append(f"Weak dimensions: {', '.join(weak_names)}")

        if degraded:
            deg_names = [f"{d['dimension']}(-{d['drop']:.3f})" for d in degraded[:3]]
            parts.append(f"Degraded: {', '.join(deg_names)}")

        if not parts:
            parts.append("All dimensions healthy")

        return " | ".join(parts)

    def _get_pipeline_config(self, pipeline) -> dict:
        """Extract current configuration from pipeline object."""
        config_vars = [
            "top_k", "temperature", "retrieval_strategy",
            "model", "rerank", "use_cache", "min_relevance_score",
            "grounding_strictness", "fallback_model",
        ]

        config = {}
        for var in config_vars:
            if hasattr(pipeline, var):
                config[var] = getattr(pipeline, var)

        return config
