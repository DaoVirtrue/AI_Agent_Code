"""Maximal Marginal Relevance (MMR) selector for diverse few-shot examples.

Balances relevance to the query against diversity among selected examples
using a greedy selection algorithm.
"""

import numpy as np
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class MMRSelector:
    """Maximal Marginal Relevance selector for diverse few-shot examples.

    MMR balances relevance to the query against diversity among
    selected examples using a greedy selection algorithm.

    MMR = lambda * relevance(d, q) - (1 - lambda) * max_similarity(d, selected)

    Higher lambda -> more relevance-focused (less diverse).
    Lower lambda -> more diversity-focused.

    Reference: Carbonell & Goldstein (1998), "The Use of MMR, Diversity-Based
    Reranking for Reordering Documents and Producing Summaries".
    """

    def __init__(self, lambda_diversity: float = 0.7, embedding_model=None):
        """Initialize MMR selector.

        Args:
            lambda_diversity: Weight for relevance vs diversity (range 0-1).
                Higher values favor relevance; lower values favor diversity.
            embedding_model: Optional callable for embeddings. Falls back to
                simple character n-gram embedding if not provided.

        Raises:
            ValueError: If lambda_diversity is not between 0 and 1.
        """
        if not 0 <= lambda_diversity <= 1:
            raise ValueError(
                f"lambda_diversity must be between 0 and 1, got {lambda_diversity}"
            )
        self.lambda_diversity = lambda_diversity
        self.embedding_model = embedding_model
        logger.info(
            "MMRSelector initialized (lambda=%.2f, model=%s)",
            lambda_diversity,
            "custom" if embedding_model else "simple",
        )

    def select(
        self,
        query_embedding: np.ndarray,
        candidate_embeddings: np.ndarray,
        candidate_examples: list[dict],
        k: int = 5,
    ) -> list[dict]:
        """Select k diverse and relevant examples using greedy MMR algorithm.

        Algorithm:
            1. Compute relevance (cosine similarity) of each candidate to query.
            2. Initially select the most relevant candidate.
            3. Iteratively select candidates that maximize the MMR score:
               MMR = lambda * relevance(d, q) - (1 - lambda) * max_sim_to_selected

        Args:
            query_embedding: Shape (d,) numpy array for the query.
            candidate_embeddings: Shape (n, d) numpy array for candidates.
            candidate_examples: List of n example dicts corresponding to rows
                in candidate_embeddings.
            k: Number of examples to select.

        Returns:
            List of k selected example dicts with '_mmr_score' key added.

        Raises:
            ValueError: If embeddings and examples lengths don't match or
                if k exceeds available candidates.
        """
        n_candidates = len(candidate_examples)
        if n_candidates == 0:
            logger.warning("select called with empty candidates")
            return []

        if candidate_embeddings.shape[0] != n_candidates:
            raise ValueError(
                f"candidate_embeddings has {candidate_embeddings.shape[0]} rows "
                f"but candidate_examples has {n_candidates} entries"
            )

        if k > n_candidates:
            logger.warning(
                "Requested k=%d but only %d candidates available; using all",
                k,
                n_candidates,
            )
            k = n_candidates

        if k <= 0:
            return []

        # Ensure query_embedding is 1-D
        query_embedding = np.asarray(query_embedding, dtype=np.float64).ravel()

        # Compute relevance scores: cosine similarity of each candidate to query
        query_norm = np.linalg.norm(query_embedding)
        if query_norm == 0:
            relevances = np.zeros(n_candidates, dtype=np.float64)
        else:
            candidate_norms = np.linalg.norm(candidate_embeddings, axis=1)
            # Avoid division by zero
            candidate_norms = np.where(candidate_norms == 0, 1.0, candidate_norms)
            dot_products = np.dot(candidate_embeddings, query_embedding)
            relevances = dot_products / (candidate_norms * query_norm)

        # MMR greedy selection
        selected_indices: list[int] = []
        remaining_indices = set(range(n_candidates))

        # Step 1: Select the most relevant candidate
        first_idx = int(np.argmax(relevances))
        selected_indices.append(first_idx)
        remaining_indices.remove(first_idx)

        # Pre-compute pairwise similarities between all candidates for efficiency
        sim_matrix = self._cosine_similarity_matrix(
            candidate_embeddings, candidate_embeddings
        )

        # Step 2-N: Greedy MMR selection
        for step in range(1, k):
            best_idx = -1
            best_mmr_score = float("-inf")

            for idx in remaining_indices:
                # Relevance term
                relevance_score = relevances[idx]

                # Diversity term: max similarity to any already-selected
                max_sim_to_selected = max(
                    sim_matrix[idx, sel_idx] for sel_idx in selected_indices
                )

                # MMR score
                mmr_score = (
                    self.lambda_diversity * relevance_score
                    - (1 - self.lambda_diversity) * max_sim_to_selected
                )

                if mmr_score > best_mmr_score:
                    best_mmr_score = mmr_score
                    best_idx = idx

            if best_idx == -1:
                # Fallback: pick any remaining
                best_idx = next(iter(remaining_indices))
                best_mmr_score = relevances[best_idx]

            selected_indices.append(best_idx)
            remaining_indices.remove(best_idx)

            logger.debug(
                "MMR step %d/%d: selected candidate %d (mmr=%.4f)",
                step + 1,
                k,
                best_idx,
                best_mmr_score,
            )

        # Build result list
        results = []
        for idx in selected_indices:
            example = dict(candidate_examples[idx])
            example["_mmr_score"] = float(relevances[idx])
            results.append(example)

        return results

    def _cosine_similarity_matrix(
        self, a: np.ndarray, b: np.ndarray
    ) -> np.ndarray:
        """Compute pairwise cosine similarity between two sets of vectors.

        Args:
            a: Shape (n, d) numpy array.
            b: Shape (m, d) numpy array.

        Returns:
            Shape (n, m) numpy array of cosine similarities.
        """
        a = np.asarray(a, dtype=np.float64)
        b = np.asarray(b, dtype=np.float64)

        # Normalize row-wise
        a_norms = np.linalg.norm(a, axis=1, keepdims=True)
        b_norms = np.linalg.norm(b, axis=1, keepdims=True)

        # Avoid division by zero
        a_norms = np.where(a_norms == 0, 1.0, a_norms)
        b_norms = np.where(b_norms == 0, 1.0, b_norms)

        a_normalized = a / a_norms
        b_normalized = b / b_norms

        return np.dot(a_normalized, b_normalized.T)

    def _simple_embed(self, texts: list[str]) -> np.ndarray:
        """Simple embedding fallback using character n-gram overlap.

        Builds bag-of-ngrams vectors using character unigrams, bigrams,
        and trigrams. Dimensionality is min(len(texts) * 10, 500).

        Args:
            texts: List of text strings to embed.

        Returns:
            Shape (len(texts), dim) numpy array of embeddings.
        """
        if not texts:
            return np.zeros((0, 0), dtype=np.float64)

        dim = min(len(texts) * 10, 500)
        dim = max(dim, 64)  # minimum dimension

        embeddings = np.zeros((len(texts), dim), dtype=np.float64)

        for i, text in enumerate(texts):
            text_lower = text.lower()

            # Character unigrams
            for ch in text_lower:
                if ch.strip():
                    idx = hash(ch) % dim
                    embeddings[i, idx] += 1

            # Character bigrams
            for j in range(len(text_lower) - 1):
                bigram = text_lower[j:j + 2]
                idx = hash(bigram) % dim
                embeddings[i, idx] += 1

            # Character trigrams
            for j in range(len(text_lower) - 2):
                trigram = text_lower[j:j + 3]
                idx = hash(trigram) % dim
                embeddings[i, idx] += 1

            # Word-level features
            words = text_lower.split()
            for word in words:
                idx = hash(word) % dim
                embeddings[i, idx] += 1

            # L2 normalize each row
            row_norm = np.linalg.norm(embeddings[i])
            if row_norm > 0:
                embeddings[i] /= row_norm

        return embeddings
