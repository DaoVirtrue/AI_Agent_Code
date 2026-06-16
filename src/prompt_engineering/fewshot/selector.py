"""Few-shot example selector based on embedding similarity.

Selects the most relevant few-shot examples by computing cosine similarity
between the query embedding and candidate example embeddings.
"""

import numpy as np
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class FewShotSelector:
    """Select most relevant few-shot examples by embedding similarity.

    Embeds the query, computes cosine similarity with all candidate
    examples, and returns the top-k most similar ones. Supports both
    custom embedding models and a simple bag-of-words fallback.
    """

    def __init__(self, embedding_model=None):
        """Initialize with optional embedding model callable.

        Args:
            embedding_model: A callable that takes text and returns a numpy
                array. If None, uses a simple bag-of-words fallback.
        """
        self.embedding_model = embedding_model
        logger.info(
            "FewShotSelector initialized (model=%s)",
            "custom" if embedding_model else "bag-of-words",
        )

    def select_by_similarity(
        self, query: str, examples: list[dict], k: int = 5
    ) -> list[dict]:
        """Select top-k most similar examples to the query.

        Each example dict must have at least an 'input' key containing
        the text content for similarity computation.

        Args:
            query: The query text to find similar examples for.
            examples: List of example dicts, each with at least 'input' key.
            k: Number of top examples to return.

        Returns:
            List of up to k example dicts with an added 'similarity_score'
            key, sorted by similarity descending.
        """
        if not examples:
            logger.warning("select_by_similarity called with empty examples list")
            return []

        if k <= 0:
            return []

        # Embed the query
        query_embedding = self._embed(query)

        # Embed all examples and compute similarities
        scored_examples = []
        for example in examples:
            # Use 'input' key, fallback to first text-like value
            example_text = example.get("input")
            if example_text is None:
                # Try common alternative keys
                for alt_key in ("text", "content", "output"):
                    if alt_key in example:
                        example_text = example[alt_key]
                        break

            if example_text is None:
                logger.warning(
                    "Example has no 'input' or text key; skipping: %s",
                    example.get("id", str(example)[:50]),
                )
                continue

            example_embedding = self._embed(str(example_text))
            similarity = self._cosine_similarity(query_embedding, example_embedding)

            scored_examples.append({
                **example,
                "similarity_score": float(similarity),
            })

        if not scored_examples:
            logger.warning("No examples could be scored")
            return []

        # Sort by similarity descending and take top-k
        scored_examples.sort(key=lambda x: x["similarity_score"], reverse=True)

        return scored_examples[:k]

    def _embed(self, text: str) -> np.ndarray:
        """Embed text into a vector.

        If embedding_model is provided, delegates to it.
        Otherwise uses a bag-of-words fallback based on word overlap
        with a global vocabulary accumulated from all texts seen.

        Args:
            text: The text to embed.

        Returns:
            A numpy array representing the text embedding.
        """
        if not text:
            return np.zeros(1, dtype=np.float64)

        if self.embedding_model is not None:
            try:
                result = self.embedding_model(text)
                if isinstance(result, np.ndarray):
                    return result
                elif isinstance(result, list):
                    return np.array(result, dtype=np.float64)
                else:
                    # Try to convert
                    return np.array(result, dtype=np.float64)
            except Exception as e:
                logger.warning(
                    "Custom embedding model failed: %s; falling back to bag-of-words",
                    e,
                )

        # Bag-of-words fallback
        return self._bag_of_words_embed(text)

    def _bag_of_words_embed(self, text: str) -> np.ndarray:
        """Create a simple bag-of-words embedding.

        Uses character n-grams (n=1,2,3) with a hashing trick to produce
        a fixed-dimensional vector.

        Args:
            text: The text to embed.

        Returns:
            A 128-dimensional numpy array.
        """
        text = text.lower()
        dim = 128

        vector = np.zeros(dim, dtype=np.float64)

        # Character unigrams (1-grams)
        for ch in text:
            if ch.strip():
                idx = hash(ch) % dim
                vector[idx] += 1

        # Character bigrams (2-grams)
        for i in range(len(text) - 1):
            bigram = text[i:i + 2]
            idx = hash(bigram) % dim
            vector[idx] += 1

        # Character trigrams (3-grams)
        for i in range(len(text) - 2):
            trigram = text[i:i + 3]
            idx = hash(trigram) % dim
            vector[idx] += 1

        # Word-level unigrams
        words = text.split()
        for word in words:
            idx = hash(word) % dim
            vector[idx] += 1

        # Normalize to unit length
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
