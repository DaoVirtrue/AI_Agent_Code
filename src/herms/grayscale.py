"""Grayscale rollout — 灰度发布 + 多版本并行（Herms 的 R: Rollout）。

Routes a request to one of several versions based on its traffic tags, using a
deterministic hash (so the same session/tenant always hits the same version).
This enables canary releases and A/B experiments without a full cutover.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class VersionTarget:
    """A version (or strategy) that can receive traffic."""

    name: str
    weight: float  # 0-1, fraction of traffic to route here
    config: dict = field(default_factory=dict)


@dataclass
class RouteDecision:
    """Result of a grayscale routing decision."""

    selected: str
    bucket: int  # 0-99 (percentile bucket the request landed in)
    metadata: dict = field(default_factory=dict)


class GrayscaleRouter:
    """Deterministic weighted router across versions.

    Args:
        targets: List of VersionTarget (weights should sum to ~1.0).
        salt: A stable salt so the same key routes consistently across restarts.
    """

    def __init__(self, targets: list[VersionTarget], salt: str = "llm-platform"):
        if not targets:
            raise ValueError("At least one target is required")
        self.targets = targets
        self.salt = salt
        total = sum(t.weight for t in targets)
        if abs(total - 1.0) > 0.01:
            logger.warning("Grayscale weights sum to %.2f (expected ~1.0)", total)

    def route(self, key: str) -> RouteDecision:
        """Route a request key (e.g. tenant_id or session_id) to a version.

        Uses a stable hash -> bucket in [0, 99], then maps the bucket onto the
        cumulative weight distribution.
        """
        bucket = self._stable_bucket(key)
        cumulative = 0.0
        for target in self.targets:
            cumulative += target.weight
            if bucket / 100.0 < cumulative:
                return RouteDecision(selected=target.name, bucket=bucket, metadata=target.config)
        # Fallthrough to the last target (guards against float drift)
        last = self.targets[-1]
        return RouteDecision(selected=last.name, bucket=bucket, metadata=last.config)

    def _stable_bucket(self, key: str) -> int:
        """Hash a key into a stable 0-99 bucket."""
        digest = hashlib.md5(f"{self.salt}:{key}".encode()).hexdigest()
        return int(digest[:8], 16) % 100

    def canary(self, key: str) -> bool:
        """Convenience: is this key routed to a non-default (canary) version?"""
        return self.route(key).selected != self.targets[0].name
