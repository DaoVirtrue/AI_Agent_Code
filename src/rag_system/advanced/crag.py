"""Corrective RAG (CRAG) processor.

CRAG evaluates retrieved documents and decides whether to use them,
seek more information, or skip retrieval entirely.
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class CRAGProcessor:
    """Corrective RAG: Evaluate retrieved documents and take corrective action.

    CRAG adds a document evaluation step after retrieval:
    1. Evaluate each retrieved document for relevance
    2. If documents are relevant: use them for generation
    3. If partially relevant: supplement with web search
    4. If not relevant: fall back to web search or pure LLM

    This prevents the LLM from being misled by irrelevant retrieved docs.
    """

    EVALUATION_PROMPT = """Evaluate the relevance of this document to the query on a scale of 1-5.
1 = completely irrelevant, 5 = highly relevant.

Query: {query}
Document: {document}

Respond ONLY with a number 1-5."""

    def __init__(self, llm_client=None, relevance_threshold: float = 3.0):
        """Initialize CRAG processor.

        Args:
            llm_client: LLM for document evaluation and generation
            relevance_threshold: Threshold (1-5) for considering a document relevant
        """
        self.llm_client = llm_client
        self.relevance_threshold = relevance_threshold
        logger.info("CRAGProcessor: threshold=%.1f", relevance_threshold)

    async def process(
        self,
        query: str,
        documents: list[dict],
        retrieval_callable=None,
    ) -> dict:
        """Process retrieved documents with corrective evaluation.

        Args:
            query: User query
            documents: Retrieved documents
            retrieval_callable: Optional async function to retrieve more docs

        Returns:
            Dict with {action, documents, answer}
        """
        if not documents:
            return {
                "action": "no_documents",
                "documents": [],
                "answer": "No documents available for retrieval.",
                "evaluation_scores": [],
            }

        # Step 1: Evaluate each document
        evaluations = await self._evaluate_documents(query, documents)

        # Step 2: Classify each document
        relevant_docs = []
        partial_docs = []
        irrelevant_docs = []

        for doc, score in zip(documents, evaluations):
            if score >= self.relevance_threshold:
                relevant_docs.append(doc)
            elif score >= self.relevance_threshold - 1.0:
                partial_docs.append(doc)
            else:
                irrelevant_docs.append(doc)

        logger.debug("CRAG evaluation: %d relevant, %d partial, %d irrelevant",
                      len(relevant_docs), len(partial_docs), len(irrelevant_docs))

        # Step 3: Determine action
        if relevant_docs or partial_docs:
            action = "use_retrieved"
            final_docs = relevant_docs + partial_docs
        else:
            action = "fallback_to_generation"
            final_docs = []
            logger.warning("All documents irrelevant, falling back to LLM generation")

        # Step 4: Generate with corrective context
        if self.llm_client and final_docs:
            answer = await self._generate_with_docs(query, final_docs)
        elif self.llm_client:
            answer = await self._generate_without_docs(query)
        else:
            answer = f"CRAG generated answer for: {query}"

        return {
            "action": action,
            "documents": final_docs,
            "answer": answer,
            "evaluation_scores": evaluations,
            "relevant_count": len(relevant_docs),
            "partial_count": len(partial_docs),
            "irrelevant_count": len(irrelevant_docs),
        }

    async def _evaluate_documents(self, query: str, documents: list[dict]) -> list[float]:
        """Evaluate relevance of each document to the query.

        Returns list of scores 1-5 for each document.
        """
        scores = []

        for doc in documents:
            content = doc.get("content", "")[:500]

            if self.llm_client:
                prompt = self.EVALUATION_PROMPT.format(query=query, document=content)
                try:
                    if hasattr(self.llm_client, 'generate'):
                        response = await self.llm_client.generate(prompt)
                    else:
                        response = str(self.llm_client(prompt))

                    score_text = str(response).strip()
                    score = float(''.join(c for c in score_text if c.isdigit() or c == '.'))
                    scores.append(max(1.0, min(5.0, score)))
                except Exception as e:
                    logger.warning("CRAG evaluation error: %s", e)
                    scores.append(self._heuristic_relevance(query, content))
            else:
                scores.append(self._heuristic_relevance(query, content))

        return scores

    def _heuristic_relevance(self, query: str, content: str) -> float:
        """Heuristic relevance score based on term overlap."""
        q_terms = set(query.lower().split())
        c_terms = set(content.lower().split())

        if not q_terms:
            return 3.0

        overlap = len(q_terms & c_terms) / len(q_terms)
        # Map 0-1 overlap to 1-5 scale
        return 1.0 + overlap * 4.0

    async def _generate_with_docs(self, query: str, documents: list[dict]) -> str:
        """Generate answer using retrieved documents."""
        context = "\n\n".join([
            f"[Doc {i+1}] {doc.get('content', '')[:500]}"
            for i, doc in enumerate(documents)
        ])

        prompt = f"""Based on the following documents, answer the query. Only use information from the documents. If the documents don't contain the answer, say so.

Documents:
{context}

Query: {query}

Answer:"""

        try:
            if hasattr(self.llm_client, 'generate'):
                response = await self.llm_client.generate(prompt)
                return str(response)
            return f"Generated answer for: {query}"
        except Exception as e:
            logger.error("CRAG generation error: %s", e)
            return f"Error generating answer: {str(e)}"

    async def _generate_without_docs(self, query: str) -> str:
        """Generate answer without documents (fallback)."""
        prompt = f"""Answer the following query to the best of your knowledge. If you are unsure, be honest about your uncertainty.

Query: {query}

Answer:"""

        try:
            if hasattr(self.llm_client, 'generate'):
                response = await self.llm_client.generate(prompt)
                return str(response)
            return f"Direct answer for: {query}"
        except Exception as e:
            return f"Unable to generate answer: {str(e)}"
