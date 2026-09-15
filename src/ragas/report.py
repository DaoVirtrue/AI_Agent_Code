"""RAGAS evaluation report store — 评测历史与趋势.

Persists evaluation runs (in-memory for now; PostgreSQL in production) so the
frontend can render historical trends and compare runs against a baseline.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class EvalRun:
    """A single recorded evaluation run."""

    run_id: str
    scores: dict
    created_at: float = field(default_factory=time.time)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "scores": self.scores,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }


class EvalRunStore:
    """In-memory store for evaluation runs."""

    def __init__(self, max_runs: int = 500):
        self.max_runs = max_runs
        self._runs: dict[str, EvalRun] = {}

    def save(self, scores: dict, metadata: Optional[dict] = None) -> EvalRun:
        """Record a run and return it."""
        run = EvalRun(run_id=str(uuid.uuid4()), scores=scores, metadata=metadata or {})
        self._runs[run.run_id] = run
        if len(self._runs) > self.max_runs:
            # Evict oldest
            oldest = min(self._runs.values(), key=lambda r: r.created_at)
            self._runs.pop(oldest.run_id, None)
        return run

    def list_runs(self, limit: int = 50) -> list[dict]:
        """Return recent runs, newest first."""
        runs = sorted(self._runs.values(), key=lambda r: r.created_at, reverse=True)
        return [r.to_dict() for r in runs[:limit]]

    def get_run(self, run_id: str) -> Optional[dict]:
        run = self._runs.get(run_id)
        return run.to_dict() if run else None

    def trend(self, metric: str = "overall", limit: int = 50) -> list[dict]:
        """Return the time series for a metric across recent runs."""
        runs = sorted(self._runs.values(), key=lambda r: r.created_at)
        return [
            {"run_id": r.run_id, "created_at": r.created_at, metric: r.scores.get(metric, 0.0)}
            for r in runs[-limit:]
        ]
