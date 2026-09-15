"""Traffic tagging — 流量染色字段全链路透传（Herms 的 R: Rollout）。

Injects version/experiment/strategy tags into a request context so that every
downstream service (gateway, RAG, agent) can route and report per-version.
This is the foundation of canary / grayscale rollout: without stable tags,
multi-version parallel release is untrackable.

Tags (from the architecture doc):
    version_set_id, strategy_id, experiment_id, tenant_id, session_id,
    task_id, trace_id
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class TrafficTags:
    """The full set of traffic tags attached to a request."""

    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str = ""
    session_id: str = ""
    task_id: str = ""
    version_set_id: str = ""
    strategy_id: str = ""
    experiment_id: str = ""

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "tenant_id": self.tenant_id,
            "session_id": self.session_id,
            "task_id": self.task_id,
            "version_set_id": self.version_set_id,
            "strategy_id": self.strategy_id,
            "experiment_id": self.experiment_id,
        }

    @classmethod
    def from_headers(cls, headers: dict[str, str]) -> "TrafficTags":
        """Extract traffic tags from HTTP headers (X-* prefix)."""
        def get(key: str) -> str:
            return headers.get(key, "") or headers.get(key.lower(), "")

        return cls(
            trace_id=get("X-Trace-Id") or str(uuid.uuid4()),
            tenant_id=get("X-Tenant-Id"),
            session_id=get("X-Session-Id"),
            task_id=get("X-Task-Id"),
            version_set_id=get("X-Version-Set-Id"),
            strategy_id=get("X-Strategy-Id"),
            experiment_id=get("X-Experiment-Id"),
        )

    def as_headers(self) -> dict[str, str]:
        """Serialize tags into HTTP headers for downstream propagation."""
        mapping = {
            "trace_id": "X-Trace-Id",
            "tenant_id": "X-Tenant-Id",
            "session_id": "X-Session-Id",
            "task_id": "X-Task-Id",
            "version_set_id": "X-Version-Set-Id",
            "strategy_id": "X-Strategy-Id",
            "experiment_id": "X-Experiment-Id",
        }
        return {header: getattr(self, field_name) for field_name, header in mapping.items()
                if getattr(self, field_name)}


def tag_request(tags: Optional[TrafficTags] = None, **overrides) -> TrafficTags:
    """Create or extend traffic tags (convenience factory)."""
    if tags is None:
        tags = TrafficTags()
    for key, value in overrides.items():
        if hasattr(tags, key):
            setattr(tags, key, value)
    return tags
