"""Self-RAG processor with reflection tokens.

Self-RAG uses special reflection tokens to control retrieval and
generation behavior: whether to retrieve, whether passages are
relevant, whether the answer is supported, and whether it's useful.
"""

import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)


class SelfRAGProcessor:
    """Self-RAG: Self-Reflective Retrieval-Augmented Generation.

    Uses reflection tokens to guide the generation process:
    [Retrieve] - Decide whether retrieval is needed
    [IsRel] - Check if retrieved passages are relevant
    [IsSup] - Check if the answer is supported by passages
    [IsUse] - Check if the answer is useful/complete

    Each reflection step can trigger corrective actions:
    - If [Retrieve]=yes -> perform retrieval
    - If [IsRel]=no -> retrieve again
    - If [IsSup]=no -> regenerate with more context
    - If [IsUse]=no -> refine the answer
    """

    REFLECTION_TOKENS = ["[Retrieve]", "[IsRel]", "[IsSup]", "[IsUse]"]

    def __init__(self, llm_client=None, max_reflection_rounds: int = 3):
        """Initialize Self-RAG processor.

        Args:
            llm_client: LLM client with generate() method
            max_reflection_rounds: Maximum refinement iterations
        """
        self.llm_client = llm_client
        self.max_reflection_rounds = max_reflection_rounds
        logger.info("SelfRAGProcessor: max_rounds=%d", max_reflection_rounds)

    async def process(
        self,
        query: str,
        retriever=None,
        context: Optional[list[dict]] = None,
    ) -> dict:
        """Process a query with self-reflection.

        Args:
            query: User query
            retriever: Async callable to retrieve documents
            context: Optional pre-retrieved context

        Returns:
            Dict with {answer, reflection_trail, documents_used, rounds}
        """
        reflection_trail = []
        documents = context or []
        answer = ""
        rounds = 0

        # Step 1: Decide whether to retrieve
        should_retrieve = await self._decide_retrieve(query)
        reflection_trail.append({"step": "retrieve_decision", "decision": "yes" if should_retrieve else "no"})

        if should_retrieve and retriever and not documents:
            documents = await self._retrieve(query, retriever)
            reflection_trail.append({"step": "retrieval", "count": len(documents)})

        # Step 2: Check relevance of retrieved docs
        if documents:
            relevance_results = await self._check_relevance(query, documents)
            relevant_docs = [doc for doc, is_rel in zip(documents, relevance_results) if is_rel]
            reflection_trail.append({
                "step": "relevance_check",
                "total": len(documents),
                "relevant": len(relevant_docs),
            })
        else:
            relevant_docs = []

        # Step 3: Generate answer
        for round_num in range(self.max_reflection_rounds):
            rounds += 1

            if relevant_docs:
                answer = await self._generate_with_docs(query, relevant_docs)
            else:
                answer = await self._generate_direct(query)

            # Step 4: Check if answer is supported
            is_supported = await self._check_support(answer, relevant_docs)
            reflection_trail.append({
                "step": f"support_check_r{round_num}",
                "is_supported": is_supported,
            })

            if is_supported:
                # Step 5: Check if answer is useful
                is_useful = await self._check_usefulness(query, answer)
                reflection_trail.append({
                    "step": f"usefulness_check_r{round_num}",
                    "is_useful": is_useful,
                })

                if is_useful:
                    break  # Answer is good enough
                else:
                    # Refine the answer
                    new_answer = await self._refine_answer(query, answer, reflection_trail)
                    if new_answer != answer:
                        answer = new_answer
                    else:
                        break  # No improvement
            else:
                # Try to retrieve more documents
                if retriever and round_num == 0:
                    more_docs = await self._retrieve(query, retriever)
                    relevant_docs.extend(more_docs)
                    logger.debug("Self-RAG: Retrieved %d more documents", len(more_docs))
                else:
                    break  # Can't improve further

        return {
            "answer": answer,
            "reflection_trail": reflection_trail,
            "documents_used": len(relevant_docs),
            "rounds": rounds,
        }

    async def _decide_retrieve(self, query: str) -> bool:
        """Decide whether retrieval is needed."""
        if not self.llm_client:
            # Heuristic: short factual queries need retrieval
            return len(query.split()) < 20

        prompt = f"""Decide if retrieving external documents would help answer this query.
Respond with only "yes" or "no".

Query: {query}

Need retrieval?"""

        try:
            if hasattr(self.llm_client, 'generate'):
                response = await self.llm_client.generate(prompt)
                return "yes" in str(response).lower()
            return True
        except Exception:
            return True

    async def _retrieve(self, query: str, retriever) -> list[dict]:
        """Retrieve documents."""
        try:
            if hasattr(retriever, 'retrieve'):
                return await retriever.retrieve(query, top_k=5)
            else:
                result = await retriever(query)
                return result if isinstance(result, list) else []
        except Exception as e:
            logger.error("Self-RAG retrieval error: %s", e)
            return []

    async def _check_relevance(self, query: str, documents: list[dict]) -> list[bool]:
        """Check which documents are relevant to the query."""
        results = []

        for doc in documents[:10]:  # Check top-10
            content = doc.get("content", "")[:300]

            if self.llm_client:
                prompt = f"""Is this document relevant to the query? Reply only "yes" or "no".

Query: {query}
Document: {content}

Relevant?"""
                try:
                    if hasattr(self.llm_client, 'generate'):
                        response = await self.llm_client.generate(prompt)
                        is_rel = "yes" in str(response).lower()
                    else:
                        is_rel = self._heuristic_relevant(query, content)
                except Exception:
                    is_rel = self._heuristic_relevant(query, content)
            else:
                is_rel = self._heuristic_relevant(query, content)

            results.append(is_rel)

        return results

    def _heuristic_relevant(self, query: str, content: str) -> bool:
        """Heuristic relevance check."""
        q_terms = set(query.lower().split())
        c_terms = set(content.lower().split())
        if not q_terms:
            return True
        overlap = len(q_terms & c_terms) / len(q_terms)
        return overlap > 0.1

    async def _generate_with_docs(self, query: str, documents: list[dict]) -> str:
        """Generate answer using documents."""
        if not self.llm_client:
            return f"Answer for: {query}"

        context = "\n\n".join([
            f"[{i+1}] {doc.get('content', '')[:300]}"
            for i, doc in enumerate(documents[:5])
        ])

        prompt = f"""Answer based on the provided documents. Only use information from the documents.

Documents:
{context}

Query: {query}

Answer:"""

        try:
            if hasattr(self.llm_client, 'generate'):
                response = await self.llm_client.generate(prompt)
                return str(response)
            return f"Answer for: {query}"
        except Exception:
            return f"Error generating answer for: {query}"

    async def _generate_direct(self, query: str) -> str:
        """Generate answer without documents."""
        if not self.llm_client:
            return f"Direct answer for: {query}"

        prompt = f"Answer the following question: {query}"
        try:
            if hasattr(self.llm_client, 'generate'):
                response = await self.llm_client.generate(prompt)
                return str(response)
            return f"Answer for: {query}"
        except Exception:
            return f"Error answering: {query}"

    async def _check_support(self, answer: str, documents: list[dict]) -> bool:
        """Check if answer is supported by documents."""
        if not documents:
            return True

        if not self.llm_client:
            # Heuristic: check term overlap
            doc_text = " ".join(doc.get("content", "")[:200] for doc in documents).lower()
            ans_words = set(answer.lower().split())
            doc_words = set(doc_text.split())
            if not ans_words:
                return True
            return len(ans_words & doc_words) / len(ans_words) > 0.3

        context = " ".join(doc.get("content", "")[:200] for doc in documents[:3])
        prompt = f"""Is this answer fully supported by the provided context? Reply only "yes" or "no".

Context: {context[:500]}
Answer: {answer[:300]}

Supported?"""

        try:
            if hasattr(self.llm_client, 'generate'):
                response = await self.llm_client.generate(prompt)
                return "yes" in str(response).lower()
            return True
        except Exception:
            return True

    async def _check_usefulness(self, query: str, answer: str) -> bool:
        """Check if the answer is useful."""
        if not self.llm_client:
            return len(answer) > 20  # At least somewhat substantive

        prompt = f"""Is this answer useful and complete for the query? Reply only "yes" or "no".

Query: {query}
Answer: {answer[:500]}

Useful?"""

        try:
            if hasattr(self.llm_client, 'generate'):
                response = await self.llm_client.generate(prompt)
                return "yes" in str(response).lower()
            return True
        except Exception:
            return True

    async def _refine_answer(self, query: str, answer: str, trail: list) -> str:
        """Refine an answer that was deemed not useful."""
        if not self.llm_client:
            return answer

        issues = [t for t in trail if not t.get("is_useful", True) or not t.get("is_supported", True)]
        issues_text = "\n".join(str(i) for i in issues[-3:])

        prompt = f"""Improve this answer. The following issues were identified:
{issues_text}

Original query: {query}
Current answer: {answer}

Improved answer:"""

        try:
            if hasattr(self.llm_client, 'generate'):
                response = await self.llm_client.generate(prompt)
                return str(response)
            return answer
        except Exception:
            return answer
