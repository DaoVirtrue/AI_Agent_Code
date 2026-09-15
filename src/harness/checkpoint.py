"""Checkpoint / snapshot store — 断点快照与回放.

From the architecture doc (section 2.3 + section 11.3): every agent step is
snapshotted so a run can be replayed offline or resumed from the most recent
stable point. Snapshots capture the full state needed to reconstruct a step:
task id, step index, inputs, outputs, completed tool calls, and cost so far.

This is a lightweight in-memory implementation; swap the storage backend for
PostgreSQL / Redis in production.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class Snapshot:
    """A single execution snapshot."""

    task_id: str
    step_index: int
    state: dict = field(default_factory=dict)
    tool_calls: list[dict] = field(default_factory=list)
    cost_usd: float = 0.0
    tokens_used: int = 0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "step_index": self.step_index,
            "state": self.state,
            "tool_calls": self.tool_calls,
            "cost_usd": self.cost_usd,
            "tokens_used": self.tokens_used,
            "timestamp": self.timestamp,
        }


class CheckpointStore:
    """In-memory snapshot store with resume support.

    Args:
        max_snapshots_per_task: Cap on retained snapshots per task (LRU-ish).
    """

    def __init__(self, max_snapshots_per_task: int = 100):
        self.max_snapshots_per_task = max_snapshots_per_task
        self._snapshots: dict[str, list[Snapshot]] = {}

    def save(self, snapshot: Snapshot) -> None:
        """Persist a snapshot for a task."""
        task_id = snapshot.task_id
        if task_id not in self._snapshots:
            self._snapshots[task_id] = []
        snaps = self._snapshots[task_id]
        snaps.append(snapshot)
        if len(snaps) > self.max_snapshots_per_task:
            self._snapshots[task_id] = snaps[-self.max_snapshots_per_task:]

    def latest(self, task_id: str) -> Optional[Snapshot]:
        """Return the most recent snapshot for a task, or None."""
        snaps = self._snapshots.get(task_id, [])
        return snaps[-1] if snaps else None

    def history(self, task_id: str) -> list[dict]:
        """Return the full snapshot history for a task."""
        return [s.to_dict() for s in self._snapshots.get(task_id, [])]

    def clear(self, task_id: str) -> None:
        """Drop all snapshots for a task."""
        self._snapshots.pop(task_id, None)
