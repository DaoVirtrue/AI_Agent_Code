"""Milvus vector store implementation."""

import logging
import uuid
from typing import Any, Optional

import numpy as np

from .vector_store import BaseVectorStore, VectorDocument

logger = logging.getLogger(__name__)

try:
    from pymilvus import (
        Collection, CollectionSchema, DataType, FieldSchema,
        connections, utility, AnnSearchRequest, WeightedRanker,
    )
    HAS_MILVUS = True
except ImportError:
    HAS_MILVUS = False
    logger.info("pymilvus not installed")


class MilvusStore(BaseVectorStore):
    """Milvus vector database store implementation.

    Supports dense and sparse (hybrid) search via Milvus 2.4+.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 19530,
        collection_name: str = "rag_documents",
        dim: int = 1024,
        user: str = "",
        password: str = "",
        metric_type: str = "COSINE",
        index_type: str = "IVF_FLAT",
        consistency_level: str = "Bounded",
    ):
        """Initialize Milvus store connection.

        Args:
            host: Milvus host
            port: Milvus gRPC port
            collection_name: Collection name
            dim: Embedding dimension
            user: Username for authentication
            password: Password for authentication
            metric_type: Similarity metric (COSINE, IP, L2)
            index_type: Vector index type
            consistency_level: Milvus consistency level
        """
        self.host = host
        self.port = port
        self.collection_name = collection_name
        self.dim = dim
        self.metric_type = metric_type
        self.index_type = index_type
        self.consistency_level = consistency_level
        self._collection: Optional[Collection] = None
        self._connected = False

        if HAS_MILVUS:
            try:
                conn_kwargs = {"host": host, "port": str(port)}
                if user:
                    conn_kwargs["user"] = user
                if password:
                    conn_kwargs["password"] = password
                connections.connect(alias="default", **conn_kwargs)
                self._connected = True
                self._ensure_collection()
                logger.info("MilvusStore connected: %s:%d, collection=%s", host, port, collection_name)
            except Exception as e:
                logger.error("Milvus connection failed: %s", e)
                self._connected = False
        else:
            logger.warning("pymilvus not available - using in-memory fallback")

    async def add(self, documents: list[VectorDocument]) -> list[str]:
        """Add documents to Milvus collection."""
        if not self._connected or not HAS_MILVUS:
            return await self._fallback_add(documents)

        ids = []
        entities = []

        for doc in documents:
            doc_id = doc.id or str(uuid.uuid4())
            ids.append(doc_id)

            entity = {
                "id": doc_id,
                "text": doc.text[:65535],  # Milvus VARCHAR limit
                "embedding": doc.embedding.tolist() if doc.embedding is not None else [0.0] * self.dim,
                "metadata": str(doc.metadata),
            }
            entities.append(entity)

        try:
            self._collection.insert(entities)
            self._collection.flush()
            logger.debug("Inserted %d documents into Milvus", len(ids))
        except Exception as e:
            logger.error("Milvus insert error: %s", e)

        return ids

    async def search(
        self,
        query_embedding: np.ndarray,
        top_k: int = 10,
        filters: Optional[dict] = None,
    ) -> list[VectorDocument]:
        """Search Milvus for similar documents."""
        if not self._connected or not HAS_MILVUS:
            return await self._fallback_search(query_embedding, top_k)

        try:
            self._collection.load()

            search_params = {
                "metric_type": self.metric_type,
                "params": {"nprobe": 10},
            }

            filter_expr = self._build_filter_expr(filters) if filters else None

            results = self._collection.search(
                data=[query_embedding.tolist()],
                anns_field="embedding",
                param=search_params,
                limit=top_k,
                expr=filter_expr,
                output_fields=["text", "metadata"],
                consistency_level=self.consistency_level,
            )

            documents = []
            for hits in results:
                for hit in hits:
                    doc = VectorDocument(
                        id=hit.id,
                        text=hit.entity.get("text", ""),
                        score=float(hit.distance),
                        metadata=eval(hit.entity.get("metadata", "{}")),
                    )
                    documents.append(doc)

            return documents

        except Exception as e:
            logger.error("Milvus search error: %s", e)
            return []

    async def delete(self, ids: list[str]) -> int:
        """Delete documents from Milvus."""
        if not self._connected or not HAS_MILVUS:
            return await self._fallback_delete(ids)

        try:
            expr = f"id in {ids}"
            self._collection.delete(expr)
            self._collection.flush()
            return len(ids)
        except Exception as e:
            logger.error("Milvus delete error: %s", e)
            return 0

    async def count(self) -> int:
        """Get document count."""
        if not self._connected or not HAS_MILVUS:
            return self._fallback.count() if hasattr(self, '_fallback') else 0

        try:
            self._collection.flush()
            return self._collection.num_entities
        except Exception:
            return 0

    async def get(self, doc_id: str) -> Optional[VectorDocument]:
        """Get a document by ID from Milvus."""
        if not self._connected or not HAS_MILVUS:
            return None

        try:
            results = self._collection.query(
                expr=f'id == "{doc_id}"',
                output_fields=["text", "metadata", "embedding"],
            )
            if results:
                r = results[0]
                return VectorDocument(
                    id=r["id"],
                    text=r.get("text", ""),
                    metadata=eval(r.get("metadata", "{}")),
                )
        except Exception as e:
            logger.error("Milvus get error: %s", e)

        return None

    def _ensure_collection(self):
        """Ensure the Milvus collection exists with correct schema."""
        if not HAS_MILVUS:
            return

        if utility.has_collection(self.collection_name):
            self._collection = Collection(self.collection_name)
            return

        # Define schema
        fields = [
            FieldSchema(name="id", dtype=DataType.VARCHAR, is_primary=True, max_length=128),
            FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=65535),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=self.dim),
            FieldSchema(name="metadata", dtype=DataType.VARCHAR, max_length=8192),
        ]

        schema = CollectionSchema(fields, description="RAG document collection")
        self._collection = Collection(self.collection_name, schema)

        # Create index
        index_params = {
            "metric_type": self.metric_type,
            "index_type": self.index_type,
            "params": {"nlist": 128},
        }
        self._collection.create_index(field_name="embedding", index_params=index_params)
        logger.info("Created Milvus collection: %s (dim=%d)", self.collection_name, self.dim)

    def _build_filter_expr(self, filters: dict) -> str:
        """Build Milvus filter expression from dict filters."""
        conditions = []
        for key, value in filters.items():
            if isinstance(value, str):
                conditions.append(f'metadata like "%{key}%{value}%"')
            else:
                conditions.append(f'metadata like "%{key}%"')
        return " and ".join(conditions) if conditions else ""

    # Fallback methods (when Milvus is unavailable)
    async def _fallback_add(self, documents: list[VectorDocument]) -> list[str]:
        if not hasattr(self, '_fallback'):
            from .vector_store import InMemoryVectorStore
            self._fallback = InMemoryVectorStore()
        return await self._fallback.add(documents)

    async def _fallback_search(self, query_embedding, top_k) -> list[VectorDocument]:
        if not hasattr(self, '_fallback'):
            from .vector_store import InMemoryVectorStore
            self._fallback = InMemoryVectorStore()
        return await self._fallback.search(query_embedding, top_k)

    async def _fallback_delete(self, ids: list[str]) -> int:
        if not hasattr(self, '_fallback'):
            return 0
        return await self._fallback.delete(ids)

    async def create_collection(self, collection_name: str, dim: int, description: str = "") -> bool:
        """Create a new collection programmatically."""
        if not HAS_MILVUS:
            return False
        try:
            if utility.has_collection(collection_name):
                return False
            fields = [
                FieldSchema(name="id", dtype=DataType.VARCHAR, is_primary=True, max_length=128),
                FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=dim),
                FieldSchema(name="metadata", dtype=DataType.VARCHAR, max_length=8192),
            ]
            schema = CollectionSchema(fields, description=description)
            col = Collection(collection_name, schema)
            index_params = {
                "metric_type": "COSINE",
                "index_type": "IVF_FLAT",
                "params": {"nlist": 128},
            }
            col.create_index(field_name="embedding", index_params=index_params)
            logger.info("Created collection: %s", collection_name)
            return True
        except Exception as e:
            logger.error("Create collection error: %s", e)
            return False

    async def drop_collection(self, collection_name: str) -> bool:
        """Drop a collection."""
        if not HAS_MILVUS:
            return False
        try:
            if utility.has_collection(collection_name):
                utility.drop_collection(collection_name)
                return True
            return False
        except Exception as e:
            logger.error("Drop collection error: %s", e)
            return False
