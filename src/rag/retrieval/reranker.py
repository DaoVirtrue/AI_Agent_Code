"""Cross-encoder and LLM-based reranking for improved precision."""

import logging
from typing import Any, Optional

import numpy as np

logger = logging.getLogger(__name__)


class Reranker:
    """Rerank retrieved documents using cross-encoder models.

    Cross-encoders process query-document pairs jointly, providing more
    accurate relevance scores than bi-encoder (embedding) similarity.

    Supports:
    - Local cross-encoder models (via sentence-transformers)
    - LLM-based reranking (using an LLM to score relevance)
    - Score normalization and threshold filtering
    """

    def __init__(
        self,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
        use_llm: bool = False,
        llm_client=None,
        score_threshold: float = 0.0,
    ):
        """Initialize reranker.

        Args:
            model_name: Cross-encoder model path
            use_llm: Use LLM for reranking instead of cross-encoder
            llm_client: LLM client for LLM-based reranking
            score_threshold: Minimum score to include in results
        """
        self.model_name = model_name
        self.use_llm = use_llm
        self.llm_client = llm_client
        self.score_threshold = score_threshold
        self._model = None

        if not use_llm:
            try:
                from sentence_transformers import CrossEncoder
                self._model = CrossEncoder(
                    model_name,
                    max_length=512,
                )
                logger.info("Reranker loaded: %s", model_name)
            except ImportError:
                logger.warning("sentence-transformers not installed - using score-based reranking")
            except Exception as e:
                logger.error("Cross-encoder load error: %s", e)
        else:
            logger.info("Reranker using LLM-based scoring")

    async def rerank(
        self,
        query: str,
        documents: list[dict],
        top_k: Optional[int] = None,
    ) -> list[dict]:
        """Rerank documents for a query.

        Args:
            query: Query text
            documents: List of {id, content, score, metadata} dicts
            top_k: Max documents to return after reranking

        Returns:
            Reranked documents with updated scores
        """
        if not documents:
            return []

        if top_k is None:
            top_k = len(documents)

        if self._model and not self.use_llm:
            return await self._cross_encoder_rerank(query, documents, top_k)
        elif self.use_llm and self.llm_client:
            return await self._llm_rerank(query, documents, top_k)
        else:
            return await self._heuristic_rerank(query, documents, top_k)

    async def _cross_encoder_rerank(
        self, query: str, documents: list[dict], top_k: int
    ) -> list[dict]:
        """Rerank using cross-encoder model."""
        import asyncio

        # Prepare query-document pairs
        pairs = [(query, doc.get("content", "")) for doc in documents]

        # Score all pairs
        loop = asyncio.get_event_loop()
        scores = await loop.run_in_executor(
            None, lambda: self._model.predict(pairs, show_progress_bar=False)
        )

        # Assign scores and sort
        for i, doc in enumerate(documents):
            doc["rerank_score"] = float(scores[i]) if hasattr(scores[i], '__float__') else float(scores[i])

        sorted_docs = sorted(documents, key=lambda x: x.get("rerank_score", 0), reverse=True)

        # Apply threshold
        filtered = [doc for doc in sorted_docs if doc.get("rerank_score", 0) >= self.score_threshold]

        result = filtered[:top_k]

        # Normalize scores to 0-1 range
        if result:
            max_score = max(doc.get("rerank_score", 0) for doc in result)
            if max_score > 0:
                for doc in result:
                    doc["score"] = doc.get("rerank_score", 0) / max_score

        logger.debug("Cross-encoder reranked: %d -> %d results", len(documents), len(result))
        return result

    async def _llm_rerank(
        self, query: str, documents: list[dict], top_k: int
    ) -> list[dict]:
        """Rerank using LLM-based relevance scoring.

        Asks the LLM to score each document's relevance to the query
        on a scale of 1-10, then normalizes to 0-1.
        """
        scored_docs = []

        for doc in documents:
            content = doc.get("content", "")[:1000]  # Truncate for cost

            prompt = f"""On a scale of 1-10, rate how relevant this document is to the query.
Query: {query}
Document: {content}

Return ONLY a number from 1-10. No explanation needed.
Relevance score:"""

            try:
                if hasattr(self.llm_client, 'generate'):
                    response = await self.llm_client.generate(prompt)
                else:
                    # Fallback: use simple overlap scoring
                    response = str(min(10, max(1, self._simple_overlap_score(query, content) * 10)))

                # Extract numeric score
                score_text = str(response).strip()
                score = float(''.join(c for c in score_text if c.isdigit() or c == '.'))
                score = max(0.0, min(10.0, score)) / 10.0  # Normalize to 0-1

                doc["rerank_score"] = score
                scored_docs.append(doc)
            except Exception as e:
                logger.warning("LLM rerank failed for doc: %s", e)
                doc["rerank_score"] = doc.get("score", 0.5)
                scored_docs.append(doc)

        scored_docs.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)
        result = [doc for doc in scored_docs if doc.get("rerank_score", 0) >= self.score_threshold]

        return result[:top_k]

    async def _heuristic_rerank(
        self, query: str, documents: list[dict], top_k: int
    ) -> list[dict]:
        """Fallback heuristic reranking based on term overlap and position."""
        query_terms = set(query.lower().split())

        for doc in documents:
            content = doc.get("content", "")
            content_terms = set(content.lower().split())
            overlap = len(query_terms & content_terms) / max(len(query_terms), 1)

            # Combine with existing score
            original_score = doc.get("score", 0.5)
            doc["rerank_score"] = original_score * 0.6 + overlap * 0.4

        sorted_docs = sorted(documents, key=lambda x: x.get("rerank_score", 0), reverse=True)
        return sorted_docs[:top_k]

    def _simple_overlap_score(self, query: str, content: str) -> float:
        """Simple term overlap score as fallback."""
        q_terms = set(query.lower().split())
        c_terms = set(content.lower().split())
        if not q_terms:
            return 0.5
        return len(q_terms & c_terms) / len(q_terms)
