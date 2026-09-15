"""Retrieval module - dense, sparse, hybrid retrieval and reranking."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .dense import DenseRetriever
from .sparse import SparseRetriever
from .hybrid import HybridRetriever
from .reranker import Reranker
from .fusion import RRFFusion


@dataclass
class SearchResult:
    """Single search result from retrieval."""
    doc_id: str
    content: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)
    source: str = ""
    embedding: list[float] | None = None


@dataclass
class RetrievalResult:
    """Results from a retrieval operation."""
    query: str
    results: list[SearchResult]
    latency_ms: float
    total_candidates: int = 0
    retrieval_method: str = ""


__all__ = [
    "DenseRetriever",
    "SparseRetriever",
    "HybridRetriever",
    "Reranker",
    "RRFFusion",
    "SearchResult",
    "RetrievalResult",
]
