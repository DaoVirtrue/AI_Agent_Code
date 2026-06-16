"""Query processing module for RAG system.

Provides query rewriting, expansion, decomposition, HyDE generation,
and adaptive query routing to optimize retrieval effectiveness.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from .rewriting import QueryRewriter
from .expansion import QueryExpander
from .decomposition import QueryDecomposer
from .hyde import HyDEGenerator
from .router import QueryRouter


@dataclass
class ProcessedQuery:
    """Result of query processing."""
    original: str
    rewritten: list[str] = field(default_factory=list)
    expanded: list[str] = field(default_factory=list)
    hyde_document: str = ""
    sub_queries: list[dict[str, str]] = field(default_factory=list)
    route: str = "simple"
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseQueryProcessor(ABC):
    """Abstract base for query processors."""

    @abstractmethod
    async def process(self, query: str, **kwargs: Any) -> list[str]:
        """Process a query and return transformed versions."""
        ...


__all__ = [
    "QueryRewriter",
    "QueryExpander",
    "QueryDecomposer",
    "HyDEGenerator",
    "QueryRouter",
    "BaseQueryProcessor",
    "ProcessedQuery",
]
