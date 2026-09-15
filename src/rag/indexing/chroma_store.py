"""Chroma vector store implementation."""

import logging
import uuid
from typing import Any, Optional

import numpy as np

from .vector_store import BaseVectorStore, VectorDocument

logger = logging.getLogger(__name__)

try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    HAS_CHROMA = True
except ImportError:
    HAS_CHROMA = False
    logger.info("chromadb not installed")


class ChromaStore(BaseVectorStore):
    """Chroma vector database store.

    Suitable for lightweight/local deployments. Supports persistent
    and in-memory modes.
    """

    def __init__(
        self,
        collection_name: str = "rag_documents",
        persist_directory: str = "./chroma_data",
        distance_metric: str = "cosine",
    ):
        """Initialize Chroma store.

        Args:
            collection_name: Name of the Chroma collection
            persist_directory: Directory for persistent storage
            distance_metric: "cosine", "l2", or "ip"
        """
        self.collection_name = collection_name
        self.persist_directory = persist_directory
        self.distance_metric = distance_metric
        self._client = None
        self._collection = None

        if HAS_CHROMA:
            try:
                self._client = chromadb.PersistentClient(
                    path=persist_directory,
                    settings=ChromaSettings(anonymized_telemetry=False),
                )
                self._collection = self._client.get_or_create_collection(
                    name=collection_name,
                    metadata={"hnsw:space": distance_metric},
                )
                logger.info("ChromaStore: collection=%s, path=%s", collection_name, persist_directory)
            except Exception as e:
                logger.error("Chroma init error: %s", e)
        else:
            logger.warning("chromadb not available")

    async def add(self, documents: list[VectorDocument]) -> list[str]:
        """Add documents to Chroma collection."""
        if not self._collection:
            return await self._fallback_add(documents)

        ids = []
        texts = []
        embeddings = []
        metadatas = []

        for doc in documents:
            doc_id = doc.id or str(uuid.uuid4())
            ids.append(doc_id)
            texts.append(doc.text)
            if doc.embedding is not None:
                embeddings.append(doc.embedding.tolist())
            metadatas.append(doc.metadata)

        try:
            kwargs = {"ids": ids, "documents": texts, "metadatas": metadatas}
            if embeddings:
                kwargs["embeddings"] = embeddings
            self._collection.add(**kwargs)
            logger.debug("Added %d documents to Chroma", len(ids))
        except Exception as e:
            logger.error("Chroma add error: %s", e)

        return ids

    async def search(
        self,
        query_embedding: np.ndarray,
        top_k: int = 10,
        filters: Optional[dict] = None,
    ) -> list[VectorDocument]:
        """Search Chroma for similar documents."""
        if not self._collection:
            return await self._fallback_search(query_embedding, top_k)

        try:
            where_filter = filters if filters else None
            results = self._collection.query(
                query_embeddings=[query_embedding.tolist()],
                n_results=top_k,
                where=where_filter,
                include=["documents", "metadatas", "distances"],
            )

            documents = []
            if results["ids"] and results["ids"][0]:
                for i, doc_id in enumerate(results["ids"][0]):
                    doc = VectorDocument(
                        id=doc_id,
                        text=results["documents"][0][i] if results["documents"] else "",
                        score=1.0 - float(results["distances"][0][i]) if results["distances"] else 0.0,
                        metadata=results["metadatas"][0][i] if results["metadatas"] else {},
                    )
                    documents.append(doc)

            return documents

        except Exception as e:
            logger.error("Chroma search error: %s", e)
            return []

    async def delete(self, ids: list[str]) -> int:
        """Delete documents from Chroma."""
        if not self._collection:
            return 0

        try:
            self._collection.delete(ids=ids)
            return len(ids)
        except Exception as e:
            logger.error("Chroma delete error: %s", e)
            return 0

    async def count(self) -> int:
        """Get document count."""
        if not self._collection:
            return 0
        try:
            return self._collection.count()
        except Exception:
            return 0

    async def get(self, doc_id: str) -> Optional[VectorDocument]:
        """Get a document by ID."""
        if not self._collection:
            return None

        try:
            results = self._collection.get(
                ids=[doc_id],
                include=["documents", "metadatas"],
            )
            if results["ids"]:
                return VectorDocument(
                    id=results["ids"][0],
                    text=results["documents"][0] if results["documents"] else "",
                    metadata=results["metadatas"][0] if results["metadatas"] else {},
                )
        except Exception as e:
            logger.error("Chroma get error: %s", e)

        return None

    async def update_metadata(self, doc_id: str, metadata: dict) -> bool:
        """Update document metadata."""
        if not self._collection:
            return False
        try:
            self._collection.update(ids=[doc_id], metadatas=[metadata])
            return True
        except Exception as e:
            logger.error("Chroma update error: %s", e)
            return False

    # Fallback
    async def _fallback_add(self, documents):
        if not hasattr(self, '_fallback'):
            from .vector_store import InMemoryVectorStore
            self._fallback = InMemoryVectorStore()
        return await self._fallback.add(documents)

    async def _fallback_search(self, qe, k):
        if not hasattr(self, '_fallback'):
            from .vector_store import InMemoryVectorStore
            self._fallback = InMemoryVectorStore()
        return await self._fallback.search(qe, k)
