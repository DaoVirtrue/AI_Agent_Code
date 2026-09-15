"""Resource reclamation with TTL（文档第 11.6 节）.

Every resource must have a TTL so a crashed process never leaks it (sandboxes,
locks, KV cache, idempotency records, snapshots). This module provides a
generic TTL reclaimer and a resource registry for tracking owned resources.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class Resource:
    """A tracked resource with a TTL and an optional cleanup callback."""

    resource_id: str
    kind: str
    ttl_seconds: float
    created_at: float = field(default_factory=time.time)
    cleanup: Optional[Callable[[], Any]] = None
    metadata: dict = field(default_factory=dict)

    @property
    def expired(self) -> bool:
        return time.time() - self.created_at >= self.ttl_seconds

    @property
    def age_seconds(self) -> float:
        return time.time() - self.created_at


class ResourceReclaimer:
    """Tracks resources and reclaims expired ones.

    Usage::

        reclaimer = ResourceReclaimer()
        reclaimer.register("sandbox-1", kind="sandbox", ttl_seconds=60, cleanup=destroy)
        ...
        reclaimed = await reclaimer.reclaim_expired()
    """

    def __init__(self):
        self._resources: dict[str, Resource] = {}

    def register(
        self,
        resource_id: str,
        kind: str,
        ttl_seconds: float,
        cleanup: Optional[Callable[[], Any]] = None,
        metadata: Optional[dict] = None,
    ) -> Resource:
        """Register a resource with a TTL."""
        resource = Resource(
            resource_id=resource_id,
            kind=kind,
            ttl_seconds=ttl_seconds,
            cleanup=cleanup,
            metadata=metadata or {},
        )
        self._resources[resource_id] = resource
        return resource

    def unregister(self, resource_id: str) -> bool:
        """Remove a resource (e.g. after clean shutdown)."""
        return self._resources.pop(resource_id, None) is not None

    async def reclaim_expired(self) -> list[str]:
        """Reclaim all expired resources, returning their IDs."""
        expired_ids = [rid for rid, r in self._resources.items() if r.expired]
        for rid in expired_ids:
            resource = self._resources.pop(rid)
            if resource.cleanup is not None:
                try:
                    result = resource.cleanup()
                    if hasattr(result, "__await__"):
                        await result
                except Exception as exc:  # noqa: BLE001 - log and continue
                    logger.error("Cleanup failed for %s: %s", rid, exc)
        return expired_ids

    def expired_count(self) -> int:
        return sum(1 for r in self._resources.values() if r.expired)

    def list_resources(self, kind: Optional[str] = None) -> list[dict]:
        """List tracked resources, optionally filtered by kind."""
        out = []
        for r in self._resources.values():
            if kind is None or r.kind == kind:
                out.append({
                    "resource_id": r.resource_id,
                    "kind": r.kind,
                    "age_seconds": r.age_seconds,
                    "ttl_seconds": r.ttl_seconds,
                    "expired": r.expired,
                })
        return out
