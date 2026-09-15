"""Query rewriting for improved retrieval precision."""

import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)


class QueryRewriter:
    """Rewrite user queries to improve retrieval effectiveness.

    Techniques:
    - Resolve pronouns and ambiguous references
    - Expand abbreviations
    - Remove filler words
    - Restructure for search optimization
    - Multi-perspective rewriting

    Supports LLM-based rewriting when an LLM client is provided,
    otherwise falls back to rule-based transformations.
    """

    # Common filler words to remove
    FILLER_WORDS = {
        "um", "uh", "like", "you know", "i mean", "actually", "basically",
        "literally", "sort of", "kind of", "just", "really", "very",
        "嗯", "啊", "那个", "就是", "然后", "所以", "的话",
    }

    # Common abbreviations
    ABBREVIATIONS = {
        "nlp": "natural language processing",
        "rag": "retrieval augmented generation",
        "llm": "large language model",
        "ml": "machine learning",
        "ai": "artificial intelligence",
        "api": "application programming interface",
        "db": "database",
        "ui": "user interface",
        "ux": "user experience",
        "qa": "question answering",
        "sdk": "software development kit",
    }

    def __init__(self, llm_client=None):
        """Initialize query rewriter.

        Args:
            llm_client: Optional LLM client for advanced rewriting.
                       Should have a generate(prompt) async method.
        """
        self.llm_client = llm_client
        logger.info("QueryRewriter initialized (llm=%s)", "available" if llm_client else "rule-based")

    async def rewrite(
        self,
        query: str,
        context: Optional[str] = None,
        num_variants: int = 3,
    ) -> list[str]:
        """Rewrite a query into multiple variants for better retrieval.

        Args:
            query: Original user query
            context: Optional conversation context for reference resolution
            num_variants: Number of rewrite variants to generate

        Returns:
            List of rewritten query strings (includes original as first)
        """
        variants = [query]  # Always include original

        if self.llm_client:
            llm_variants = await self._llm_rewrite(query, context, num_variants)
            variants.extend(llm_variants)
        else:
            rule_variants = self._rule_based_rewrite(query, context)
            variants.extend(rule_variants)

        # Deduplicate while preserving order
        seen = set()
        unique_variants = []
        for v in variants:
            v_lower = v.lower().strip()
            if v_lower not in seen and v.strip():
                seen.add(v_lower)
                unique_variants.append(v.strip())

        logger.debug("Query rewritten: %d variants for '%s...'", len(unique_variants), query[:50])
        return unique_variants[:num_variants + 1]

    async def _llm_rewrite(
        self, query: str, context: Optional[str], num_variants: int
    ) -> list[str]:
        """Use LLM to generate query rewrites."""
        prompt = f"""Rewrite the following search query in {num_variants} different ways to improve document retrieval.
Each rewrite should:
- Be self-contained (no ambiguous pronouns)
- Use precise keywords
- Cover different aspects or perspectives of the query
- Be in the same language as the original

Original query: {query}
{"Context: " + context if context else ""}

Return each rewrite on a new line, numbered 1-{num_variants}. Only return the rewrites, no explanations."""

        try:
            if hasattr(self.llm_client, 'generate'):
                response = await self.llm_client.generate(prompt)
            elif hasattr(self.llm_client, 'chat'):
                response = await self.llm_client.chat(prompt)
            else:
                response = str(self.llm_client(prompt))

            # Parse numbered lines
            lines = str(response).strip().split("\n")
            rewrites = []
            for line in lines:
                # Remove numbering like "1. ", "1) ", "1: "
                cleaned = re.sub(r'^\d+[\.\):：]\s*', '', line).strip()
                if cleaned and cleaned != query:
                    rewrites.append(cleaned)

            return rewrites[:num_variants]
        except Exception as e:
            logger.error("LLM rewrite error: %s", e)
            return self._rule_based_rewrite(query, context)

    def _rule_based_rewrite(self, query: str, context: Optional[str] = None) -> list[str]:
        """Rule-based query rewriting."""
        variants = []

        # Remove filler words
        cleaned = self._remove_filler_words(query)
        if cleaned != query:
            variants.append(cleaned)

        # Expand abbreviations
        expanded = self._expand_abbreviations(cleaned)
        if expanded != cleaned:
            variants.append(expanded)

        # Keyword extraction variant
        keywords = self._extract_keywords(cleaned)
        if keywords and keywords != cleaned:
            variants.append(keywords)

        # Add context if available
        if context:
            context_variant = f"{context.strip()} {cleaned}".strip()
            if context_variant != cleaned:
                variants.append(context_variant)

        return variants

    def _remove_filler_words(self, text: str) -> str:
        """Remove common filler words."""
        words = text.split()
        filtered = [w for w in words if w.lower() not in self.FILLER_WORDS]
        result = " ".join(filtered)
        # Clean up extra spaces
        result = re.sub(r'\s+', ' ', result).strip()
        return result

    def _expand_abbreviations(self, text: str) -> str:
        """Expand known abbreviations."""
        words = text.split()
        expanded_words = []
        for word in words:
            lower = word.lower().strip(".,;:!?")
            if lower in self.ABBREVIATIONS:
                expanded_words.append(self.ABBREVIATIONS[lower])
            else:
                expanded_words.append(word)
        return " ".join(expanded_words)

    def _extract_keywords(self, text: str) -> str:
        """Extract key terms, removing stop words."""
        # Simple stop words for English
        stop_words = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "will",
            "would", "could", "should", "may", "might", "can", "shall",
            "to", "of", "in", "for", "on", "with", "at", "by", "from",
            "about", "as", "into", "through", "during", "before", "after",
            "above", "below", "between", "and", "but", "or", "not", "no",
            "what", "which", "who", "whom", "whose", "when", "where",
            "why", "how", "this", "that", "these", "those", "it", "its",
            "please", "tell", "me", "show", "find", "get", "give",
        }
        words = text.lower().split()
        keywords = [w for w in words if w not in stop_words and len(w) > 1]
        return " ".join(keywords)
