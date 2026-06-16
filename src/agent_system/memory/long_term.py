"""
Long-term memory with vector-backed persistent storage.

Uses a vector store for semantic retrieval and stores rich metadata
alongside each memory entry. Supports importance-based retention.
"""

import hashlib
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class LTMMemory:
    """A single entry in long-term memory."""
    memory_id: str
    content: str
    embedding: list[float] | None
    importance: float  # 1-10 scale
    metadata: dict
    created_at: float
    last_accessed: float
    access_count: int = 0
    tags: list[str] = field(default_factory=list)


class LongTermMemory:
    """Vector-backed persistent long-term memory store.

    Provides semantic search over stored memories using embeddings,
    with support for importance-based filtering, tagging, and CRUD operations.

    Args:
        vector_store: A vector store instance (e.g., Chroma, FAISS, Pinecone)
                      with `add_texts`, `similarity_search` methods.
        embedding_model: An embedding model callable that converts text to vectors.
                         Should have a method like `embed_query(text) -> list[float]`
                         or `embed_documents(texts) -> list[list[float]]`.
    """

    def __init__(self, vector_store=None, embedding_model=None):
        self._vector_store = vector_store
        self._embedding_model = embedding_model
        self._memories: dict[str, LTMMemory] = {}
        self._tags_index: dict[str, set[str]] = {}  # tag -> set of memory_ids
        self._total_memories = 0

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def add(
        self,
        content: str,
        importance: float = 5.0,
        metadata: dict | None = None,
        tags: list[str] | None = None,
    ) -> str:
        """Add a new memory to long-term storage.

        Args:
            content: The text content of the memory.
            importance: Importance score (1-10, 10 being most important).
            metadata: Additional metadata dict.
            tags: Optional list of tags for categorization.

        Returns:
            The memory_id of the newly created memory.
        """
        memory_id = str(uuid.uuid4())

        # Generate embedding if model is available
        embedding = None
        if self._embedding_model:
            try:
                if hasattr(self._embedding_model, "embed_query"):
                    embedding = await self._embed_model(content)
                elif hasattr(self._embedding_model, "embed_documents"):
                    embeddings = await self._embed_model_batch([content])
                    embedding = embeddings[0] if embeddings else None
            except Exception as e:
                logger.warning("Failed to generate embedding for memory: %s", e)

        now = time.time()
        memory = LTMMemory(
            memory_id=memory_id,
            content=content,
            embedding=embedding,
            importance=max(1.0, min(10.0, importance)),
            metadata=metadata or {},
            created_at=now,
            last_accessed=now,
            tags=tags or [],
        )

        self._memories[memory_id] = memory
        self._total_memories += 1

        # Update tags index
        for tag in memory.tags:
            if tag not in self._tags_index:
                self._tags_index[tag] = set()
            self._tags_index[tag].add(memory_id)

        # Store in vector store if available
        if self._vector_store and embedding:
            try:
                await self._add_to_vector_store(memory_id, content, embedding, metadata)
            except Exception as e:
                logger.warning("Failed to add to vector store: %s", e)

        logger.debug("Added LTM memory: %s (importance=%.1f)", memory_id, importance)
        return memory_id

    async def search(self, query: str, k: int = 5, min_importance: float = 0.0) -> list[dict]:
        """Semantic search over long-term memories.

        Uses vector similarity if available, falling back to keyword matching.

        Args:
            query: The search query.
            k: Number of results to return.
            min_importance: Minimum importance score filter.

        Returns:
            List of dicts with memory data sorted by relevance.
        """
        if not self._memories:
            return []

        # Try vector search first
        if self._vector_store and self._embedding_model:
            try:
                return await self._vector_search(query, k, min_importance)
            except Exception as e:
                logger.warning("Vector search failed, falling back to keyword: %s", e)

        # Fallback: keyword search
        return await self._keyword_search(query, k, min_importance)

    async def update(self, memory_id: str, **kwargs) -> bool:
        """Update a memory's attributes.

        Args:
            memory_id: The memory to update.
            **kwargs: Fields to update (content, importance, metadata, tags).

        Returns:
            True if the memory was found and updated.
        """
        if memory_id not in self._memories:
            return False

        memory = self._memories[memory_id]

        if "content" in kwargs:
            memory.content = kwargs["content"]
            # Re-embed if content changed
            if self._embedding_model:
                try:
                    memory.embedding = await self._embed_model(memory.content)
                except Exception:
                    pass

        if "importance" in kwargs:
            memory.importance = max(1.0, min(10.0, float(kwargs["importance"])))

        if "metadata" in kwargs:
            memory.metadata.update(kwargs["metadata"])

        if "tags" in kwargs:
            # Update tags index
            old_tags = set(memory.tags)
            new_tags = set(kwargs["tags"])
            for tag in old_tags - new_tags:
                self._tags_index.get(tag, set()).discard(memory_id)
            for tag in new_tags - old_tags:
                self._tags_index.setdefault(tag, set()).add(memory_id)
            memory.tags = list(new_tags)

        memory.last_accessed = time.time()
        return True

    async def delete(self, memory_id: str) -> bool:
        """Delete a memory by ID.

        Args:
            memory_id: The memory to delete.

        Returns:
            True if the memory was found and deleted.
        """
        if memory_id not in self._memories:
            return False

        memory = self._memories.pop(memory_id)
        self._total_memories -= 1

        # Clean up tags index
        for tag in memory.tags:
            if tag in self._tags_index:
                self._tags_index[tag].discard(memory_id)
                if not self._tags_index[tag]:
                    del self._tags_index[tag]

        # Remove from vector store
        if self._vector_store:
            try:
                await self._remove_from_vector_store(memory_id)
            except Exception as e:
                logger.warning("Failed to remove from vector store: %s", e)

        return True

    async def get(self, memory_id: str) -> dict | None:
        """Get a single memory by ID.

        Args:
            memory_id: The memory ID.

        Returns:
            Dict with memory data or None if not found.
        """
        memory = self._memories.get(memory_id)
        if not memory:
            return None

        memory.last_accessed = time.time()
        memory.access_count += 1

        return {
            "memory_id": memory.memory_id,
            "content": memory.content,
            "importance": memory.importance,
            "metadata": memory.metadata,
            "created_at": memory.created_at,
            "last_accessed": memory.last_accessed,
            "access_count": memory.access_count,
            "tags": memory.tags,
        }

    # ------------------------------------------------------------------
    # Search implementations
    # ------------------------------------------------------------------

    async def _vector_search(self, query: str, k: int, min_importance: float) -> list[dict]:
        """Perform vector similarity search."""
        query_embedding = await self._embed_model(query)

        if hasattr(self._vector_store, "similarity_search_by_vector"):
            results = self._vector_store.similarity_search_by_vector(
                query_embedding, k=k * 2  # Fetch extra to filter by importance
            )
        elif hasattr(self._vector_store, "similarity_search"):
            results = self._vector_store.similarity_search(query, k=k * 2)
        else:
            return []

        filtered = []
        for doc in results:
            memory_id = doc.metadata.get("memory_id", "")
            if memory_id in self._memories:
                memory = self._memories[memory_id]
                if memory.importance >= min_importance:
                    filtered.append({
                        "memory_id": memory.memory_id,
                        "content": memory.content,
                        "importance": memory.importance,
                        "metadata": memory.metadata,
                        "created_at": memory.created_at,
                        "tags": memory.tags,
                        "score": getattr(doc, "score", None),
                    })
                    if len(filtered) >= k:
                        break

        return filtered

    async def _keyword_search(self, query: str, k: int, min_importance: float) -> list[dict]:
        """Fallback keyword-based search."""
        query_lower = query.lower()
        query_terms = query_lower.split()

        scored = []
        for memory in self._memories.values():
            if memory.importance < min_importance:
                continue

            content_lower = memory.content.lower()
            score = 0

            # Exact phrase match
            if query_lower in content_lower:
                score += 10

            # Term frequency
            for term in query_terms:
                score += content_lower.count(term)

            # Importance boost
            score += memory.importance * 0.5

            # Recency boost
            hours_ago = (time.time() - memory.last_accessed) / 3600
            score += max(0, 2 - hours_ago * 0.1)

            # Access frequency boost
            score += min(memory.access_count * 0.1, 2.0)

            if score > 0:
                scored.append((score, memory))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for _, memory in scored[:k]:
            results.append({
                "memory_id": memory.memory_id,
                "content": memory.content,
                "importance": memory.importance,
                "metadata": memory.metadata,
                "created_at": memory.created_at,
                "tags": memory.tags,
                "score": None,
            })

        return results

    # ------------------------------------------------------------------
    # Vector store helpers
    # ------------------------------------------------------------------

    async def _embed_model(self, text: str) -> list[float]:
        """Generate embedding for a single text."""
        if callable(self._embedding_model):
            return self._embedding_model(text)

        if hasattr(self._embedding_model, "aembed_query"):
            return await self._embedding_model.aembed_query(text)
        elif hasattr(self._embedding_model, "embed_query"):
            return self._embedding_model.embed_query(text)
        raise RuntimeError("Embedding model has no embed_query method")

    async def _embed_model_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts."""
        if hasattr(self._embedding_model, "aembed_documents"):
            return await self._embedding_model.aembed_documents(texts)
        elif hasattr(self._embedding_model, "embed_documents"):
            return self._embedding_model.embed_documents(texts)
        raise RuntimeError("Embedding model has no embed_documents method")

    async def _add_to_vector_store(
        self, memory_id: str, content: str,
        embedding: list[float], metadata: dict,
    ) -> None:
        """Add a memory to the vector store."""
        if hasattr(self._vector_store, "add_texts"):
            metadatas = [{"memory_id": memory_id, **metadata}]
            self._vector_store.add_texts(
                texts=[content],
                metadatas=metadatas,
                embeddings=[embedding] if embedding else None,
            )

    async def _remove_from_vector_store(self, memory_id: str) -> None:
        """Remove a memory from the vector store."""
        if hasattr(self._vector_store, "delete"):
            self._vector_store.delete(filter={"memory_id": memory_id})

    # ------------------------------------------------------------------
    # Stats & Utils
    # ------------------------------------------------------------------

    def list_by_tag(self, tag: str) -> list[dict]:
        """List all memories with a given tag."""
        ids = self._tags_index.get(tag, set())
        results = []
        for mid in ids:
            memory = self._memories.get(mid)
            if memory:
                results.append({
                    "memory_id": memory.memory_id,
                    "content": memory.content[:200],
                    "importance": memory.importance,
                    "tags": memory.tags,
                })
        return results

    def get_all_tags(self) -> list[str]:
        """Return all unique tags in the store."""
        return sorted(self._tags_index.keys())

    @property
    def count(self) -> int:
        """Total number of stored memories."""
        return self._total_memories

    def __len__(self) -> int:
        return self._total_memories

    def __repr__(self) -> str:
        return f"LongTermMemory(memories={self._total_memories}, tags={len(self._tags_index)})"
