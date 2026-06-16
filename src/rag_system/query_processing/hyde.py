"""HyDE (Hypothetical Document Embeddings) generation."""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class HyDEGenerator:
    """Generate hypothetical documents for improved retrieval.

    HyDE (Hypothetical Document Embeddings) works by:
    1. Using an LLM to generate a hypothetical document that answers the query
    2. Embedding the hypothetical document
    3. Using that embedding for dense retrieval instead of the query embedding

    This bridges the gap between short queries and document-length text,
    often improving retrieval quality significantly.

    Reference: "Precise Zero-Shot Dense Retrieval without Relevance Labels"
    """

    def __init__(self, llm_client=None):
        """Initialize HyDE generator.

        Args:
            llm_client: LLM client for generating hypothetical documents.
                       Must have generate() async method.
        """
        self.llm_client = llm_client
        logger.info("HyDEGenerator initialized (llm=%s)", "available" if llm_client else "template-based")

    async def generate(self, query: str, num_docs: int = 1) -> list[str]:
        """Generate hypothetical documents for a query.

        Args:
            query: User query
            num_docs: Number of hypothetical documents

        Returns:
            List of hypothetical document texts
        """
        if self.llm_client:
            return await self._llm_generate(query, num_docs)
        else:
            return self._template_generate(query, num_docs)

    async def _llm_generate(self, query: str, num_docs: int) -> list[str]:
        """Use LLM to generate realistic hypothetical documents."""
        prompt = f"""Write a short passage (3-5 sentences) that answers or provides information about the following query.
Write in a factual, encyclopedic style as if it were a real document or article. Do NOT mention that this is a hypothetical document.

Query: {query}

Passage:"""

        docs = []
        for i in range(num_docs):
            try:
                if hasattr(self.llm_client, 'generate'):
                    response = await self.llm_client.generate(prompt)
                else:
                    response = str(self.llm_client(prompt))

                doc = str(response).strip()
                if not doc.startswith("Passage:"):
                    doc = doc.lstrip("Passage:").strip()

                if doc and len(doc) > 20:
                    docs.append(doc)
            except Exception as e:
                logger.error("HyDE generation error: %s", e)
                docs.append(self._template_single(query, i))

        return docs if docs else self._template_generate(query, num_docs)

    def _template_generate(self, query: str, num_docs: int) -> list[str]:
        """Generate templated hypothetical documents without LLM."""
        return [self._template_single(query, i) for i in range(num_docs)]

    def _template_single(self, query: str, variant: int = 0) -> str:
        """Generate a single templated document."""
        templates = [
            f"This document discusses {query}. It provides detailed information about the topic, including key concepts, relevant examples, and practical applications. The content covers both fundamental principles and advanced considerations related to {query}.",
            f"An analysis of {query} reveals important insights. Multiple sources confirm that understanding {query} requires consideration of several interconnected factors. Research indicates growing interest and development in this area.",
            f"A comprehensive overview of {query}. The topic encompasses various dimensions including theoretical foundations, practical implementations, and future directions. Experts in the field have documented significant findings related to {query}.",
        ]
        return templates[variant % len(templates)]

    def is_available(self) -> bool:
        """Check if HyDE generation is functional."""
        return self.llm_client is not None
