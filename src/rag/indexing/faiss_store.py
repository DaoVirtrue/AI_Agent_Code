"""FAISS vector store implementation."""

import logging
import os
import pickle
import uuid
from typing import Any, Optional

import numpy as np

from .vector_store import BaseVectorStore, VectorDocument

logger = logging.getLogger(__name__)

try:
    import faiss
    HAS_FAISS = True
except ImportError:
    HAS_FAISS = False
    logger.info("faiss not installed")


class FAISSStore(BaseVectorStore):
    """FAISS vector index store.

    High-performance similarity search using Facebook AI Similarity Search.
    Supports multiple index types: Flat (exact), IVF (approximate), HNSW.

    Suitable for local/embedded deployments where a separate vector DB
    is not needed.
    """

    INDEX_TYPES = {
        "flat": "Flat",
        "ivf": "IVF",
        "hnsw": "HNSW",
    }

    def __init__(
        self,
        dim: int = 1024,
        index_type: str = "flat",
        metric: str = "cosine",
        nlist: int = 100,
        nprobe: int = 10,
        M: int = 32,  # HNSW connections
    ):
        """Initialize FAISS store.

        Args:
            dim: Embedding dimension
            index_type: "flat", "ivf", or "hnsw"
            metric: "cosine", "l2", or "ip" (inner product)
            nlist: IVF clusters (for IVF index)
            nprobe: IVF search probes
            M: HNSW graph connections
        """
        self.dim = dim
        self.index_type = index_type
        self.metric = metric
        self.nlist = nlist
        self.nprobe = nprobe
        self.M = M
        self._index = None
        self._documents: dict[int, VectorDocument] = {}
        self._id_to_idx: dict[str, int] = {}
        self._next_idx = 0

        if HAS_FAISS:
            self._create_index()
            logger.info("FAISSStore: type=%s, dim=%d, metric=%s", index_type, dim, metric)
        else:
            logger.warning("faiss not available - using in-memory fallback")

    def _create_index(self):
        """Create the FAISS index based on configuration."""
        if not HAS_FAISS:
            return

        # Determine base index
        if self.metric == "cosine":
            # FAISS uses inner product for cosine after normalization
            base_index = faiss.IndexFlatIP(self.dim)
        elif self.metric == "ip":
            base_index = faiss.IndexFlatIP(self.dim)
        else:
            base_index = faiss.IndexFlatL2(self.dim)

        # Wrap based on index type
        if self.index_type == "flat":
            if self.metric == "cosine":
                self._index = faiss.IndexIDMap(base_index)
            else:
                self._index = faiss.IndexIDMap(base_index)
        elif self.index_type == "ivf":
            quantizer = faiss.IndexFlatIP(self.dim) if self.metric in ("cosine", "ip") else faiss.IndexFlatL2(self.dim)
            idx = faiss.IndexIVFFlat(quantizer, self.dim, self.nlist, faiss.METRIC_INNER_PRODUCT if self.metric in ("cosine", "ip") else faiss.METRIC_L2)
            if not idx.is_trained:
                # Train with some random data for initialization
                train_data = np.random.randn(max(1000, self.nlist * 10), self.dim).astype(np.float32)
                if self.metric == "cosine":
                    faiss.normalize_L2(train_data)
                idx.train(train_data)
            idx.nprobe = self.nprobe
            self._index = faiss.IndexIDMap(idx)
        elif self.index_type == "hnsw":
            idx = faiss.IndexHNSWFlat(self.dim, self.M)
            idx.hnsw.efConstruction = 200
            idx.hnsw.efSearch = 64
            self._index = faiss.IndexIDMap(idx)
        else:
            self._index = faiss.IndexIDMap(base_index)

        logger.info("FAISS index created: %s", self.index_type)

    async def add(self, documents: list[VectorDocument]) -> list[str]:
        """Add documents to FAISS index."""
        if not HAS_FAISS or self._index is None:
            return await self._fallback_add(documents)

        ids = []
        embeddings = []
        faiss_ids = []

        for doc in documents:
            doc_id = doc.id or str(uuid.uuid4())
            ids.append(doc_id)

            if doc.embedding is not None:
                emb = doc.embedding.astype(np.float32).reshape(1, -1)
                if self.metric == "cosine":
                    faiss.normalize_L2(emb)
                embeddings.append(emb[0])
                idx = self._next_idx
                self._next_idx += 1
                faiss_ids.append(idx)
                self._documents[idx] = doc
                self._id_to_idx[doc_id] = idx
                doc.id = doc_id

        if embeddings:
            emb_array = np.array(embeddings, dtype=np.float32)
            id_array = np.array(faiss_ids, dtype=np.int64)
            self._index.add_with_ids(emb_array, id_array)

        logger.debug("Added %d documents to FAISS", len(ids))
        return ids

    async def search(
        self,
        query_embedding: np.ndarray,
        top_k: int = 10,
        filters: Optional[dict] = None,
    ) -> list[VectorDocument]:
        """Search FAISS index."""
        if not HAS_FAISS or self._index is None or self._index.ntotal == 0:
            return await self._fallback_search(query_embedding, top_k)

        try:
            q = query_embedding.astype(np.float32).reshape(1, -1)
            if self.metric == "cosine":
                faiss.normalize_L2(q)

            actual_k = min(top_k, self._index.ntotal)
            distances, indices = self._index.search(q, actual_k)

            documents = []
            for i in range(actual_k):
                idx = indices[0][i]
                if idx < 0 or idx not in self._documents:
                    continue
                doc = self._documents[idx]
                score = float(distances[0][i])

                # For cosine/IP similarity, convert to 0-1 range
                if self.metric in ("cosine", "ip"):
                    score = max(0.0, min(1.0, score))

                # Apply filters
                if filters and not self._matches_filters(doc.metadata, filters):
                    continue

                result_doc = VectorDocument(
                    id=doc.id,
                    text=doc.text,
                    score=score,
                    metadata=doc.metadata,
                )
                documents.append(result_doc)

            return documents

        except Exception as e:
            logger.error("FAISS search error: %s", e)
            return []

    async def delete(self, ids: list[str]) -> int:
        """Delete documents from FAISS index (marks for rebuild)."""
        deleted = 0
        for doc_id in ids:
            if doc_id in self._id_to_idx:
                idx = self._id_to_idx.pop(doc_id)
                self._documents.pop(idx, None)
                deleted += 1

        if deleted > 0:
            # FAISS doesn't support deletion natively, rebuild index
            await self._rebuild_index()

        return deleted

    async def count(self) -> int:
        """Get document count."""
        if self._index and HAS_FAISS:
            return self._index.ntotal
        return len(self._documents)

    async def get(self, doc_id: str) -> Optional[VectorDocument]:
        """Get a document by ID."""
        if doc_id in self._id_to_idx:
            idx = self._id_to_idx[doc_id]
            return self._documents.get(idx)
        return None

    async def _rebuild_index(self):
        """Rebuild FAISS index from current documents."""
        if not HAS_FAISS:
            return

        self._create_index()
        old_docs = list(self._documents.values())
        self._documents = {}
        self._id_to_idx = {}
        self._next_idx = 0

        for doc in old_docs:
            if doc.embedding is not None:
                emb = doc.embedding.astype(np.float32).reshape(1, -1)
                if self.metric == "cosine":
                    faiss.normalize_L2(emb)
                idx = self._next_idx
                self._next_idx += 1
                self._documents[idx] = doc
                self._id_to_idx[doc.id] = idx
                self._index.add_with_ids(emb, np.array([idx], dtype=np.int64))

        logger.info("FAISS index rebuilt: %d documents", self._next_idx)

    def _matches_filters(self, metadata: dict, filters: dict) -> bool:
        """Check if metadata matches filters."""
        for key, value in filters.items():
            if key not in metadata or metadata[key] != value:
                return False
        return True

    def save(self, file_path: str) -> bool:
        """Save FAISS index and document store to disk."""
        if not HAS_FAISS:
            return False
        try:
            data = {
                "documents": self._documents,
                "id_to_idx": self._id_to_idx,
                "next_idx": self._next_idx,
            }
            faiss.write_index(self._index, f"{file_path}.index")
            with open(f"{file_path}.meta", "wb") as f:
                pickle.dump(data, f)
            logger.info("Saved FAISS store to %s", file_path)
            return True
        except Exception as e:
            logger.error("FAISS save error: %s", e)
            return False

    @classmethod
    def load(cls, file_path: str, **kwargs) -> "FAISSStore":
        """Load FAISS index and document store from disk."""
        if not HAS_FAISS:
            raise RuntimeError("FAISS not installed")

        store = cls(**kwargs)
        try:
            store._index = faiss.read_index(f"{file_path}.index")
            with open(f"{file_path}.meta", "rb") as f:
                data = pickle.load(f)
            store._documents = data["documents"]
            store._id_to_idx = data["id_to_idx"]
            store._next_idx = data["next_idx"]
            logger.info("Loaded FAISS store from %s: %d documents", file_path, store._next_idx)
        except Exception as e:
            logger.error("FAISS load error: %s", e)
        return store

    # Fallback methods
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
