"""Abstract base and in-memory vector store implementations."""

from __future__ import annotations

import uuid
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class VectorDocument:
    """A document stored in a vector store."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    text: str = ""
    embedding: Optional[np.ndarray] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "content": self.text,
            "score": self.score,
            "metadata": self.metadata,
        }


class BaseVectorStore(ABC):
    """Abstract interface for vector stores."""

    @abstractmethod
    async def add(self, documents: list[VectorDocument]) -> list[str]:
        """Add documents to the store. Returns list of IDs."""
        ...

    @abstractmethod
    async def search(
        self,
        query_embedding: np.ndarray,
        top_k: int = 10,
        filters: Optional[dict] = None,
    ) -> list[VectorDocument]:
        """Search for similar documents. Returns scored documents."""
        ...

    @abstractmethod
    async def delete(self, ids: list[str]) -> int:
        """Delete documents by ID. Returns number deleted."""
        ...

    @abstractmethod
    async def count(self) -> int:
        """Return total number of documents."""
        ...

    @abstractmethod
    async def get(self, doc_id: str) -> Optional[VectorDocument]:
        """Get a single document by ID."""
        ...


class InMemoryVectorStore(BaseVectorStore):
    """Simple in-memory vector store for development/testing.

    Uses numpy for cosine similarity search. Not suitable for production
    (no persistence, no scalability), but great for testing and small datasets.
    """

    def __init__(self):
        self._documents: dict[str, VectorDocument] = {}
        self._embeddings: list[np.ndarray] = []
        self._id_to_index: dict[str, int] = {}
        logger.info("InMemoryVectorStore initialized")

    async def add(self, documents: list[VectorDocument]) -> list[str]:
        """Add documents to in-memory store."""
        ids = []
        for doc in documents:
            if not doc.id:
                doc.id = str(uuid.uuid4())
            self._documents[doc.id] = doc
            if doc.embedding is not None:
                self._id_to_index[doc.id] = len(self._embeddings)
                self._embeddings.append(doc.embedding)
            ids.append(doc.id)
        logger.debug("Added %d documents to in-memory store", len(ids))
        return ids

    async def search(
        self,
        query_embedding: np.ndarray,
        top_k: int = 10,
        filters: Optional[dict] = None,
    ) -> list[VectorDocument]:
        """Search by cosine similarity."""
        if not self._embeddings:
            return []

        # Normalize query
        query_norm = query_embedding / (np.linalg.norm(query_embedding) + 1e-8)
        db_matrix = np.array(self._embeddings)
        db_norms = np.linalg.norm(db_matrix, axis=1, keepdims=True) + 1e-8
        db_normalized = db_matrix / db_norms

        # Cosine similarity
        similarities = np.dot(db_normalized, query_norm)

        # Get top-k
        top_indices = np.argsort(similarities)[::-1][:top_k]

        results = []
        id_list = list(self._id_to_index.keys())
        for idx in top_indices:
            if idx < len(id_list):
                doc_id = id_list[idx]
                doc = self._documents.get(doc_id)
                if doc:
                    doc.score = float(similarities[idx])

                    # Apply filters
                    if filters and not self._matches_filters(doc.metadata, filters):
                        continue

                    results.append(doc)

        return results[:top_k]

    async def delete(self, ids: list[str]) -> int:
        """Delete documents by ID."""
        deleted = 0
        for doc_id in ids:
            if doc_id in self._documents:
                del self._documents[doc_id]
                if doc_id in self._id_to_index:
                    del self._id_to_index[doc_id]
                deleted += 1
        # Rebuild embedding array
        self._rebuild_embedding_index()
        return deleted

    async def count(self) -> int:
        """Return document count."""
        return len(self._documents)

    async def get(self, doc_id: str) -> Optional[VectorDocument]:
        """Get a document by ID."""
        return self._documents.get(doc_id)

    def _matches_filters(self, metadata: dict, filters: dict) -> bool:
        """Check if document metadata matches filters (simple equality)."""
        for key, value in filters.items():
            if key not in metadata or metadata[key] != value:
                return False
        return True

    def _rebuild_embedding_index(self):
        """Rebuild the embedding list from current documents."""
        self._embeddings = []
        self._id_to_index = {}
        for doc_id, doc in self._documents.items():
            if doc.embedding is not None:
                self._id_to_index[doc_id] = len(self._embeddings)
                self._embeddings.append(doc.embedding)

    def clear(self) -> None:
        """Remove all documents."""
        self._documents.clear()
        self._embeddings.clear()
        self._id_to_index.clear()
