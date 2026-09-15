from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from .exact_cache import ExactCache
from .semantic_cache import SemanticCache
from .summary_cache import SummaryCache
from .precomputed_cache import PrecomputedCache
from .cache_orchestrator import CacheOrchestrator


@dataclass
class CacheEntry:
    """A single cache entry."""
    key: str
    value: Any
    created_at: datetime
    expires_at: datetime
    hit_count: int = 0
    last_accessed: Optional[datetime] = None
    ttl_seconds: int = 3600
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        return datetime.now() > self.expires_at


@dataclass
class CacheLookupResult:
    """Result of a cache lookup."""
    hit: bool
    level: str
    entry: Optional[CacheEntry] = None
    lookup_time_ms: float = 0.0


class BaseCache(ABC):
    """Abstract base for cache implementations."""

    def __init__(self, ttl_seconds: int = 3600, max_size: int = 10000):
        self.ttl_seconds = ttl_seconds
        self.max_size = max_size

    @abstractmethod
    async def get(self, key: str) -> Optional[CacheEntry]:
        ...

    @abstractmethod
    async def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None, **kwargs: Any) -> None:
        ...

    @abstractmethod
    async def delete(self, key: str) -> bool:
        ...

    @abstractmethod
    async def clear(self) -> None:
        ...


__all__ = [
    "ExactCache",
    "SemanticCache",
    "SummaryCache",
    "PrecomputedCache",
    "CacheOrchestrator",
    "BaseCache",
    "CacheEntry",
    "CacheLookupResult",
]
