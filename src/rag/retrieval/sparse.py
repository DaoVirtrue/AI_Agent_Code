"""Sparse retrieval using BM25 and keyword matching."""

import logging
import math
import re
from collections import Counter, defaultdict
from typing import Any, Optional

import numpy as np

logger = logging.getLogger(__name__)


class SparseRetriever:
    """Sparse retrieval using BM25 algorithm.

    BM25 (Best Match 25) is a probabilistic retrieval function that ranks
    documents based on term frequency, inverse document frequency, and
    document length normalization.

    Good for:
    - Keyword-heavy queries
    - Code search
    - Technical documentation
    - Complementing dense retrieval in hybrid setups
    """

    def __init__(
        self,
        k1: float = 1.5,
        b: float = 0.75,
        tokenizer_pattern: str = r'\w+',
    ):
        """Initialize BM25 retriever.

        Args:
            k1: Term frequency saturation parameter (typically 1.2-2.0)
            b: Document length normalization parameter (typically 0.75)
            tokenizer_pattern: Regex for tokenization
        """
        self.k1 = k1
        self.b = b
        self._tokenizer = re.compile(tokenizer_pattern)
        self._documents: list[dict] = []
        self._doc_term_freqs: list[Counter] = []
        self._doc_lengths: list[int] = []
        self._avg_doc_length: float = 0.0
        self._idf: dict[str, float] = {}
        self._total_docs = 0
        self._doc_map: dict[str, int] = {}  # doc_id -> index
        logger.info("SparseRetriever: k1=%.2f, b=%.2f", k1, b)

    def index(self, documents: list[dict]) -> None:
        """Index documents for BM25 retrieval.

        Args:
            documents: List of {id, content, metadata} dicts
        """
        self._documents = documents
        self._total_docs = len(documents)
        self._doc_term_freqs = []
        self._doc_lengths = []
        self._doc_map = {}

        # Compute document frequencies
        doc_freq = defaultdict(int)

        for idx, doc in enumerate(documents):
            content = doc.get("content", "")
            tokens = self._tokenize(content)
            tf = Counter(tokens)
            self._doc_term_freqs.append(tf)
            self._doc_lengths.append(len(tokens))
            self._doc_map[doc.get("id", str(idx))] = idx

            for term in set(tokens):
                doc_freq[term] += 1

        # Compute IDF
        total = self._total_docs
        self._idf = {}
        for term, df in doc_freq.items():
            self._idf[term] = math.log(1 + (total - df + 0.5) / (df + 0.5))

        self._avg_doc_length = np.mean(self._doc_lengths) if self._doc_lengths else 0.0

        logger.info("BM25 indexed %d documents, avg length=%.1f, vocab=%d",
                     total, self._avg_doc_length, len(self._idf))

    async def retrieve(
        self,
        query: str,
        top_k: int = 10,
        filters: Optional[dict] = None,
    ) -> list[dict]:
        """Retrieve documents using BM25 scoring.

        Args:
            query: Query text
            top_k: Number of results
            filters: Metadata filters (post-retrieval)

        Returns:
            List of {id, content, score, metadata} dicts
        """
        if not self._documents:
            logger.warning("BM25 not indexed - call index() first")
            return []

        query_tokens = self._tokenize(query)
        query_tf = Counter(query_tokens)

        scores = []
        for doc_idx, doc in enumerate(self._documents):
            # Apply filters
            if filters and not self._matches_filters(doc.get("metadata", {}), filters):
                continue

            score = self._bm25_score(query_tf, doc_idx)
            if score > 0:
                scores.append((doc_idx, score))

        # Sort by score descending
        scores.sort(key=lambda x: x[1], reverse=True)
        top_scores = scores[:top_k]

        results = []
        for doc_idx, score in top_scores:
            doc = self._documents[doc_idx]
            results.append({
                "id": doc.get("id", f"doc_{doc_idx}"),
                "content": doc.get("content", ""),
                "score": float(score),
                "metadata": doc.get("metadata", {}),
                "source": "sparse_bm25",
            })

        logger.debug("BM25 retrieval: %d results for '%s...'", len(results), query[:50])
        return results

    def _bm25_score(self, query_tf: Counter, doc_idx: int) -> float:
        """Compute BM25 score for a query-document pair."""
        doc_tf = self._doc_term_freqs[doc_idx]
        doc_len = self._doc_lengths[doc_idx]

        score = 0.0
        for term, q_tf in query_tf.items():
            if term not in self._idf:
                continue

            idf = self._idf[term]
            d_tf = doc_tf.get(term, 0)

            if d_tf == 0:
                continue

            numerator = d_tf * (self.k1 + 1)
            denominator = d_tf + self.k1 * (1 - self.b + self.b * doc_len / self._avg_doc_length)
            score += idf * numerator / denominator * q_tf

        return score

    def _tokenize(self, text: str) -> list[str]:
        """Tokenize text into terms (lowercase, remove short terms)."""
        text = text.lower()
        tokens = self._tokenizer.findall(text)
        return [t for t in tokens if len(t) >= 2]

    def _matches_filters(self, metadata: dict, filters: dict) -> bool:
        """Check metadata against filters."""
        for key, value in filters.items():
            if key not in metadata:
                return False
            if isinstance(value, list) and metadata[key] not in value:
                return False
            elif not isinstance(value, list) and metadata[key] != value:
                return False
        return True

    def remove_document(self, doc_id: str) -> bool:
        """Remove a document from the index."""
        if doc_id not in self._doc_map:
            return False
        idx = self._doc_map.pop(doc_id)
        self._documents.pop(idx)
        self._doc_term_freqs.pop(idx)
        self._doc_lengths.pop(idx)
        # Rebuild mapping
        self._doc_map = {
            doc.get("id", str(i)): i
            for i, doc in enumerate(self._documents)
        }
        # Recompute IDF
        self.index(self._documents)
        return True

    def clear(self) -> None:
        """Clear the index."""
        self._documents = []
        self._doc_term_freqs = []
        self._doc_lengths = []
        self._avg_doc_length = 0.0
        self._idf = {}
        self._total_docs = 0
        self._doc_map = {}
        logger.info("BM25 index cleared")
