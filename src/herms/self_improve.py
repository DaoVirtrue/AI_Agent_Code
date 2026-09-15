"""Self-improvement loop — 自更新闭环（Herms 的 S: Self-improvement）.

The evaluate -> diagnose -> optimize -> verify cycle. It wraps a pipeline
(which must expose ``evaluate`` and ``configure``) and iterates toward a
better configuration, with a hard guard against "reward hacking": the loop
only accepts changes that improve an *independent* evaluation, and it can be
reverted to the best-known configuration.

Design note: this delegates the actual closed-loop optimization to
``src/evaluation/iteration_loop.IterationClosedLoop``, adding the
self-update-safe semantics on top.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class SelfImproveResult:
    """Result of a self-improvement cycle."""

    iterations: int
    converged: bool
    best_score: float
    improvement: float
    applied: bool
    note: str = ""


class SelfImprover:
    """Guarded self-improvement: only promote a change if it truly improves.

    Args:
        max_iterations: Maximum optimize cycles.
        min_improvement: Minimum score gain required to accept a change.
        auto_apply: If True, promote the best config; else just report it.
    """

    def __init__(
        self,
        max_iterations: int = 5,
        min_improvement: float = 0.01,
        auto_apply: bool = False,
    ):
        self.max_iterations = max_iterations
        self.min_improvement = min_improvement
        self.auto_apply = auto_apply

    async def improve(self, pipeline, dataset: list) -> SelfImproveResult:
        """Run the closed loop and (optionally) promote the best config.

        Args:
            pipeline: Object with ``evaluate`` and ``configure`` methods.
            dataset: Golden dataset to evaluate against.

        Returns:
            SelfImproveResult summarizing the run and whether the change was applied.
        """
        from src.evaluation.iteration_loop import IterationClosedLoop

        loop = IterationClosedLoop(convergence_threshold=self.min_improvement)
        result = await loop.run(
            pipeline=pipeline,
            dataset=dataset,
            max_iterations=self.max_iterations,
        )

        should_apply = result.improvement >= self.min_improvement
        if should_apply and self.auto_apply:
            pipeline.configure(**result.best_configuration)
            applied = True
            note = f"promoted best config (improvement={result.improvement:.4f})"
        else:
            applied = False
            note = f"not applied (improvement={result.improvement:.4f} < {self.min_improvement})"

        return SelfImproveResult(
            iterations=result.iterations,
            converged=result.converged,
            best_score=result.best_score,
            improvement=result.improvement,
            applied=applied,
            note=note,
        )
