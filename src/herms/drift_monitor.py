"""Online drift monitoring — 在线漂移监控（Herms 的 M: Monitoring）.

Tracks production quality signals that degrade silently:
- rejection rate（拒答率）— the model saying "I don't know" more often
- citation rate（引用点击率）— users finding sources useful
- negative feedback rate（负反馈率）— thumbs-down / correction ratio

When a metric drifts past its threshold, an alert is raised so the team can
roll back a grayscale version before the regression is widely visible.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class DriftConfig:
    """Thresholds for drift detection.

    Attributes:
        rejection_rate_max: Alert if rejection rate exceeds this (0-1).
        citation_rate_min: Alert if citation rate drops below this (0-1).
        negative_feedback_max: Alert if negative feedback exceeds this (0-1).
        window_seconds: Rolling window for rate computation.
    """

    rejection_rate_max: float = 0.30
    citation_rate_min: float = 0.50
    negative_feedback_max: float = 0.15
    window_seconds: float = 3600.0


@dataclass
class DriftAlert:
    """A drift alert raised by the monitor."""

    metric: str
    current: float
    threshold: float
    direction: str  # "high" | "low"
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "metric": self.metric,
            "current": round(self.current, 4),
            "threshold": self.threshold,
            "direction": self.direction,
        }


class DriftMonitor:
    """Monitors production quality signals and raises drift alerts."""

    def __init__(self, config: Optional[DriftConfig] = None):
        self.config = config or DriftConfig()
        self._rejections: deque[tuple[float, bool]] = deque()
        self._citations: deque[tuple[float, bool]] = deque()
        self._negative_feedback: deque[tuple[float, bool]] = deque()
        self._alerts: list[DriftAlert] = []

    def record_answer(self, *, rejected: bool, cited: bool, negative_feedback: bool) -> None:
        """Record the quality signals for one answered query."""
        now = time.monotonic()
        self._rejections.append((now, rejected))
        self._citations.append((now, cited))
        self._negative_feedback.append((now, negative_feedback))
        self._prune_all(now)

    def check(self) -> list[DriftAlert]:
        """Evaluate all metrics and return any newly-raised alerts."""
        new_alerts = []
        now = time.monotonic()
        self._prune_all(now)

        rejection_rate = self._rate(self._rejections)
        citation_rate = self._rate(self._citations)
        neg_rate = self._rate(self._negative_feedback)

        if rejection_rate > self.config.rejection_rate_max:
            new_alerts.append(DriftAlert("rejection_rate", rejection_rate, self.config.rejection_rate_max, "high"))
        if citation_rate < self.config.citation_rate_min:
            new_alerts.append(DriftAlert("citation_rate", citation_rate, self.config.citation_rate_min, "low"))
        if neg_rate > self.config.negative_feedback_max:
            new_alerts.append(DriftAlert("negative_feedback", neg_rate, self.config.negative_feedback_max, "high"))

        self._alerts.extend(new_alerts)
        return new_alerts

    def metrics(self) -> dict:
        """Return the current metric values."""
        self._prune_all(time.monotonic())
        return {
            "rejection_rate": self._rate(self._rejections),
            "citation_rate": self._rate(self._citations),
            "negative_feedback_rate": self._rate(self._negative_feedback),
        }

    @property
    def alerts(self) -> list[dict]:
        return [a.to_dict() for a in self._alerts]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _rate(self, events: deque[tuple[float, bool]]) -> float:
        if not events:
            return 0.0
        return sum(1 for _, positive in events if positive) / len(events)

    def _prune_all(self, now: float) -> None:
        cutoff = now - self.config.window_seconds
        for q in (self._rejections, self._citations, self._negative_feedback):
            while q and q[0][0] < cutoff:
                q.popleft()
