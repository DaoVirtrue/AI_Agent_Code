"""Query expansion for improved recall."""

import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)


class QueryExpander:
    """Expand queries with related terms to improve recall.

    Generates multiple expanded query variants using:
    - Synonym expansion
    - Hyponym/hypernym addition
    - Factoid-based expansion (who/what/when/where/how)
    - LLM-based expansion

    The expanded queries are searched independently and results
    are fused in the pipeline.
    """

    # Simple synonym pairs (production would use WordNet or embeddings)
    SYNONYMS = {
        "fast": ["quick", "rapid", "speedy"],
        "slow": ["sluggish", "gradual"],
        "big": ["large", "huge", "enormous", "massive"],
        "small": ["tiny", "little", "compact", "miniature"],
        "good": ["excellent", "great", "superb", "quality"],
        "bad": ["poor", "terrible", "inferior", "faulty"],
        "important": ["critical", "crucial", "essential", "vital"],
        "easy": ["simple", "straightforward", "effortless"],
        "hard": ["difficult", "challenging", "complex"],
        "create": ["build", "develop", "construct", "make"],
        "fix": ["repair", "resolve", "correct", "address"],
        "improve": ["enhance", "optimize", "upgrade", "refine"],
        "price": ["cost", "fee", "rate", "charge"],
        "security": ["safety", "protection", "defense"],
        "performance": ["speed", "efficiency", "throughput"],
        "error": ["bug", "issue", "defect", "fault", "problem"],
    }

    def __init__(self, llm_client=None):
        """Initialize query expander.

        Args:
            llm_client: Optional LLM client for advanced expansion
        """
        self.llm_client = llm_client
        logger.info("QueryExpander initialized (llm=%s)", "available" if llm_client else "synonym-based")

    async def expand(self, query: str, num_expansions: int = 3) -> list[str]:
        """Generate expanded query variants.

        Args:
            query: Original query
            num_expansions: Number of expansion variants

        Returns:
            List of expanded query strings
        """
        expansions = []

        # Synonym-based expansion
        synonym_expansions = self._synonym_expand(query)
        expansions.extend(synonym_expansions)

        # Factoid-based expansion
        factoid_expansions = self._factoid_expand(query)
        expansions.extend(factoid_expansions)

        # LLM-based expansion
        if self.llm_client:
            llm_expansions = await self._llm_expand(query, num_expansions)
            expansions.extend(llm_expansions)

        # Deduplicate
        seen = set()
        unique = []
        for exp in expansions:
            if exp.lower() not in seen and exp.strip() != query.strip():
                seen.add(exp.lower())
                unique.append(exp)

        logger.debug("Query expanded: %d variants", len(unique))
        return unique[:num_expansions]

    def _synonym_expand(self, query: str) -> list[str]:
        """Expand query by replacing words with synonyms."""
        words = query.lower().split()
        expansions = []

        for i, word in enumerate(words):
            clean_word = word.strip(".,;:!?()\"'")
            if clean_word in self.SYNONYMS:
                for synonym in self.SYNONYMS[clean_word][:2]:  # Top 2 synonyms
                    new_words = words.copy()
                    new_words[i] = synonym + (word[-1] if word[-1] in ".,;:!?" else "")
                    expansions.append(" ".join(new_words))

        return expansions

    def _factoid_expand(self, query: str) -> list[str]:
        """Expand query based on factoid type (who/what/when/where/why/how)."""
        expansions = []
        lower = query.lower().strip()

        factoid_patterns = {
            "who": ["Who is involved?", "What is the background?"],
            "what": ["What is the definition?", "What are examples?"],
            "when": ["What is the timeline?", "What is the historical context?"],
            "where": ["Where is this located?", "What is the geographical context?"],
            "why": ["What are the reasons?", "What is the motivation?"],
            "how": ["What is the process?", "What are the steps?", "What is the methodology?"],
        }

        for keyword, facets in factoid_patterns.items():
            if keyword in lower.lower().split() or lower.startswith(keyword):
                for facet in facets:
                    expansions.append(f"{query} {facet}")

        return expansions

    async def _llm_expand(self, query: str, num_expansions: int) -> list[str]:
        """Use LLM to generate query expansions."""
        prompt = f"""Generate {num_expansions} alternative search queries that expand on the original query.
Each expansion should use different synonyms, related terms, or broader/narrower perspectives.

Original query: {query}

Return each expansion on a new line. Only the queries, no numbering or explanation."""

        try:
            if hasattr(self.llm_client, 'generate'):
                response = await self.llm_client.generate(prompt)
            else:
                response = str(self.llm_client(prompt))

            lines = str(response).strip().split("\n")
            expansions = []
            for line in lines:
                cleaned = re.sub(r'^\d+[\.\):：]\s*', '', line).strip()
                if cleaned and cleaned != query:
                    expansions.append(cleaned)

            return expansions[:num_expansions]
        except Exception as e:
            logger.error("LLM expansion error: %s", e)
            return []
