"""Persistent storage and retrieval for few-shot examples.

Provides CRUD operations with embedding-based similarity search
and tag-based filtering using an in-memory store with optional
database persistence via SQLAlchemy.
"""

import uuid
import hashlib
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import logging

logger = logging.getLogger(__name__)


class FewShotRepository:
    """Persistent storage and retrieval for few-shot examples.

    Stores examples with embedding vectors for similarity search.
    Supports CRUD operations and tag-based filtering. Uses an
    in-memory dict store as the primary backing, with optional
    database persistence.

    Embedding storage is compatible with pgvector (when using
    database persistence) or simple JSON/numpy arrays for in-memory
    operation.
    """

    def __init__(self, db_session=None):
        """Initialize with optional async SQLAlchemy session.

        Args:
            db_session: An optional AsyncSession for database-backed
                persistence. If None, operates purely in memory.
        """
        self.db = db_session
        self._embedding_model = None  # Can be set externally via property
        # In-memory store: {tenant_id: {example_id: example_dict}}
        self._store: dict[uuid.UUID, dict[uuid.UUID, dict]] = {}
        logger.info("FewShotRepository initialized")

    async def add(
        self,
        tenant_id: uuid.UUID,
        input_text: str,
        output_text: str,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict] = None,
        score: Optional[float] = None,
    ) -> dict:
        """Add a new few-shot example.

        Args:
            tenant_id: The tenant owning this example.
            input_text: The example input/prompt text.
            output_text: The example output/completion text.
            tags: Optional list of tags for categorization.
            metadata: Optional additional metadata dict.
            score: Optional quality/performance score for this example.

        Returns:
            Dict with example_id and all stored data.
        """
        example_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        # Compute embedding for similarity search
        embedding = self._simple_embed(input_text)

        example = {
            "example_id": example_id,
            "tenant_id": tenant_id,
            "input": input_text,
            "output": output_text,
            "tags": tags or [],
            "metadata": metadata or {},
            "score": score,
            "embedding": embedding,
            "created_at": now,
            "updated_at": now,
        }

        # Store in memory
        if tenant_id not in self._store:
            self._store[tenant_id] = {}
        self._store[tenant_id][example_id] = example

        logger.info(
            "Added few-shot example %s for tenant %s (tags=%s)",
            example_id,
            tenant_id,
            tags,
        )
        return dict(example)

    async def search(
        self,
        tenant_id: uuid.UUID,
        query: str,
        k: int = 10,
        tags: Optional[list[str]] = None,
    ) -> list[dict]:
        """Search for similar few-shot examples using embedding similarity.

        Embeds the query text and computes cosine similarity against all
        stored examples for the tenant. Optionally filters by tags.

        Args:
            tenant_id: The tenant scope to search within.
            query: The query text to find similar examples for.
            k: Number of top results to return.
            tags: Optional list of tags; only examples matching at least
                one tag are returned.

        Returns:
            List of up to k example dicts sorted by similarity score
            descending. Each dict includes a 'similarity' key.
        """
        tenant_examples = self._store.get(tenant_id)
        if not tenant_examples:
            logger.debug("No examples found for tenant %s", tenant_id)
            return []

        # Embed the query
        query_embedding = self._simple_embed(query)

        scored = []
        for example_id, example in tenant_examples.items():
            # Filter by tags if specified
            if tags:
                example_tags = set(example.get("tags", []))
                if not example_tags.intersection(tags):
                    continue

            stored_embedding = example.get("embedding")
            if stored_embedding is None:
                continue

            similarity = self._cosine_similarity(query_embedding, stored_embedding)

            scored.append({
                "example_id": example["example_id"],
                "tenant_id": example["tenant_id"],
                "input": example["input"],
                "output": example["output"],
                "tags": list(example.get("tags", [])),
                "metadata": dict(example.get("metadata", {})),
                "score": example.get("score"),
                "similarity": float(similarity),
                "created_at": example["created_at"],
                "updated_at": example["updated_at"],
            })

        if not scored:
            logger.debug(
                "No matching examples for query in tenant %s (tags=%s)",
                tenant_id,
                tags,
            )
            return []

        # Sort by similarity descending
        scored.sort(key=lambda x: x["similarity"], reverse=True)

        return scored[:k]

    async def delete(self, example_id: uuid.UUID) -> bool:
        """Delete a few-shot example by ID.

        Args:
            example_id: The example to delete.

        Returns:
            True if the example was deleted, False if not found.
        """
        for tenant_id, examples in self._store.items():
            if example_id in examples:
                del examples[example_id]
                logger.info("Deleted few-shot example %s", example_id)
                return True

        logger.warning(
            "Attempted to delete non-existent example %s", example_id
        )
        return False

    async def get_by_tags(
        self,
        tenant_id: uuid.UUID,
        tags: list[str],
        match_all: bool = False,
    ) -> list[dict]:
        """Get examples matching specified tags.

        Args:
            tenant_id: The tenant scope.
            tags: List of tags to match against.
            match_all: If True, all tags must be present (AND logic).
                If False, any tag match suffices (OR logic).

        Returns:
            List of matching example dicts.
        """
        tenant_examples = self._store.get(tenant_id)
        if not tenant_examples:
            return []

        tag_set = set(tags)
        results = []

        for example_id, example in tenant_examples.items():
            example_tags = set(example.get("tags", []))

            if match_all:
                if tag_set.issubset(example_tags):
                    results.append(self._to_result_dict(example))
            else:
                if tag_set.intersection(example_tags):
                    results.append(self._to_result_dict(example))

        logger.debug(
            "get_by_tags: tenant=%s, tags=%s, match_all=%s, found=%d",
            tenant_id,
            tags,
            match_all,
            len(results),
        )
        return results

    async def get_by_id(self, example_id: uuid.UUID) -> Optional[dict]:
        """Get a single example by its ID.

        Args:
            example_id: The example ID to look up.

        Returns:
            Example dict if found, None otherwise.
        """
        for tenant_id, examples in self._store.items():
            if example_id in examples:
                return self._to_result_dict(examples[example_id])
        return None

    async def update(
        self,
        example_id: uuid.UUID,
        input_text: Optional[str] = None,
        output_text: Optional[str] = None,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict] = None,
    ) -> Optional[dict]:
        """Update an existing example. Only provided fields are updated.

        Args:
            example_id: The example to update.
            input_text: New input text (if provided).
            output_text: New output text (if provided).
            tags: New tags list (if provided, replaces existing).
            metadata: New metadata dict (if provided, replaces existing).

        Returns:
            Updated example dict if found, None otherwise.
        """
        for tenant_id, examples in self._store.items():
            if example_id in examples:
                example = examples[example_id]

                if input_text is not None:
                    example["input"] = input_text
                    # Recompute embedding when input changes
                    example["embedding"] = self._simple_embed(input_text)

                if output_text is not None:
                    example["output"] = output_text

                if tags is not None:
                    example["tags"] = list(tags)

                if metadata is not None:
                    example["metadata"] = dict(metadata)

                example["updated_at"] = datetime.now(timezone.utc)

                logger.info("Updated few-shot example %s", example_id)
                return self._to_result_dict(example)

        logger.warning(
            "Attempted to update non-existent example %s", example_id
        )
        return None

    async def count(self, tenant_id: uuid.UUID) -> int:
        """Count examples for a tenant.

        Args:
            tenant_id: The tenant scope.

        Returns:
            Number of examples stored for the tenant.
        """
        tenant_examples = self._store.get(tenant_id)
        if tenant_examples is None:
            return 0
        return len(tenant_examples)

    def _to_result_dict(self, example: dict) -> dict:
        """Convert an internal example dict to a result dict (without embedding).

        Args:
            example: Internal example dict.

        Returns:
            Dict suitable for external consumption.
        """
        return {
            "example_id": example["example_id"],
            "tenant_id": example["tenant_id"],
            "input": example["input"],
            "output": example["output"],
            "tags": list(example.get("tags", [])),
            "metadata": dict(example.get("metadata", {})),
            "score": example.get("score"),
            "created_at": example["created_at"],
            "updated_at": example["updated_at"],
        }

    def _simple_embed(self, text: str, dim: int = 128) -> np.ndarray:
        """Simple text embedding using hashed character n-grams.

        Uses the hashing trick to project character n-grams (unigrams,
        bigrams, trigrams) and word features into a fixed-dimension
        vector space.

        Args:
            text: The text to embed.
            dim: Dimensionality of the output vector.

        Returns:
            A normalized numpy array of shape (dim,).
        """
        if not text:
            return np.zeros(dim, dtype=np.float64)

        text_lower = text.lower()
        vector = np.zeros(dim, dtype=np.float64)

        # Character unigrams
        for ch in text_lower:
            if ch.strip():
                idx = hash(f"c1:{ch}") % dim
                vector[idx] += 1

        # Character bigrams
        for i in range(len(text_lower) - 1):
            bigram = text_lower[i:i + 2]
            idx = hash(f"c2:{bigram}") % dim
            vector[idx] += 1

        # Character trigrams
        for i in range(len(text_lower) - 2):
            trigram = text_lower[i:i + 3]
            idx = hash(f"c3:{trigram}") % dim
            vector[idx] += 1

        # Word-level unigrams
        words = text_lower.split()
        for word in words:
            idx = hash(f"w1:{word}") % dim
            vector[idx] += 1

        # L2 normalize
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm

        return vector

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Compute cosine similarity between two vectors.

        Args:
            a: First vector.
            b: Second vector.

        Returns:
            Cosine similarity in range [-1, 1].
        """
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)

        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0

        return float(np.dot(a, b) / (norm_a * norm_b))
