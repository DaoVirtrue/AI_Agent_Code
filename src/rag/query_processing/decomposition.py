"""Query decomposition for multi-hop reasoning."""

import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)


class QueryDecomposer:
    """Decompose complex queries into sub-queries for multi-hop retrieval.

    Some questions require information from multiple documents.
    Decomposing them into simpler sub-questions allows:
    - Parallel retrieval
    - Step-by-step reasoning
    - Better coverage of multi-faceted questions

    Example:
    "What was the revenue of the company that acquired Instagram?"
    -> ["Who acquired Instagram?", "What was that company's revenue?"]
    """

    def __init__(self, llm_client=None):
        """Initialize query decomposer.

        Args:
            llm_client: Optional LLM client for decomposition.
                       Should have generate() async method.
        """
        self.llm_client = llm_client
        logger.info("QueryDecomposer initialized (llm=%s)", "available" if llm_client else "rule-based")

    async def decompose(
        self, query: str, max_sub_queries: int = 5
    ) -> list[dict]:
        """Decompose a complex query into simpler sub-queries.

        Args:
            query: Complex query to decompose
            max_sub_queries: Maximum number of sub-queries

        Returns:
            List of {query, dependency, reasoning} dicts
            dependency: None or index of prerequisite sub-query
        """
        # Detect if decomposition is needed
        if not self._needs_decomposition(query):
            return [{"query": query, "dependency": None, "reasoning": "simple query, no decomposition needed"}]

        if self.llm_client:
            return await self._llm_decompose(query, max_sub_queries)
        else:
            return self._rule_based_decompose(query, max_sub_queries)

    async def _llm_decompose(self, query: str, max_sub_queries: int) -> list[dict]:
        """Use LLM for query decomposition."""
        prompt = f"""Break down the following complex question into simpler sub-questions that can be answered independently.
Each sub-question should be self-contained and answerable from a single document.
If sub-questions depend on each other, note the dependency.

Complex question: {query}

Respond in JSON format:
{{
  "sub_questions": [
    {{"question": "...", "dependency": null or index of prerequisite question (0-based)"}},
    ...
  ]
}}

Do not include more than {max_sub_queries} sub-questions."""

        try:
            import json
            if hasattr(self.llm_client, 'generate'):
                response = await self.llm_client.generate(prompt)
            else:
                response = str(self.llm_client(prompt))

            result = json.loads(str(response))
            sub_questions = result.get("sub_questions", [])

            return [
                {
                    "query": sq["question"],
                    "dependency": sq.get("dependency"),
                    "reasoning": "LLM-decomposed",
                }
                for sq in sub_questions[:max_sub_queries]
            ]
        except Exception as e:
            logger.error("LLM decomposition error: %s", e)
            return self._rule_based_decompose(query, max_sub_queries)

    def _rule_based_decompose(self, query: str, max_sub_queries: int) -> list[dict]:
        """Rule-based query decomposition using linguistic patterns."""
        # Detect comparison questions
        if re.search(r'(vs\.?|versus|compared?\s+(to|with)|difference\s+between)', query, re.IGNORECASE):
            return self._decompose_comparison(query)

        # Detect multi-hop patterns (entity -> relation -> attribute)
        if self._is_multi_hop(query):
            return self._decompose_multi_hop(query)

        # Detect conjunctive questions (and/or)
        if " and " in query.lower() or " or " in query.lower():
            return self._decompose_conjunctive(query, max_sub_queries)

        # Default: return as is
        return [{"query": query, "dependency": None, "reasoning": "rule-based: no decomposition pattern matched"}]

    def _decompose_comparison(self, query: str) -> list[dict]:
        """Decompose comparison questions: 'A vs B' -> ['What is A?', 'What is B?']."""
        sub_queries = []

        # Try to split on comparison keywords
        parts = re.split(r'\s+(?:vs\.?|versus|compared?\s+(?:to|with))\s+', query, maxsplit=1, flags=re.IGNORECASE)
        if len(parts) == 2:
            for part in parts:
                sub_queries.append({
                    "query": f"What is {part.strip()}?",
                    "dependency": None,
                    "reasoning": "comparison decomposition",
                })

        if not sub_queries:
            sub_queries.append({"query": query, "dependency": None, "reasoning": "comparison (could not split)"})

        return sub_queries

    def _decompose_multi_hop(self, query: str) -> list[dict]:
        """Decompose multi-hop questions."""
        # Pattern: "What is the X of the Y that Z?"
        # -> ["What Y Z?", "What is the X of that Y?"]
        sub_queries = []

        # Extract 'that/who/which' clauses
        match = re.search(r'(?:about|of|for)\s+(?:the\s+)?(\w[\w\s]+?)\s+(?:that|who|which)\s+(.+)', query, re.IGNORECASE)
        if match:
            entity = match.group(1).strip()
            condition = match.group(2).strip()

            sub_queries.append({
                "query": f"Which {entity} {condition}?",
                "dependency": None,
                "reasoning": "multi-hop: find entity first",
            })

            prefix = re.match(r'^(.*?)(?:of|about|for)\s+(?:the\s+)?(\w[\w\s]+?)\s+(?:that|who|which)', query, re.IGNORECASE)
            if prefix:
                attribute = prefix.group(1).strip()
                sub_queries.append({
                    "query": f"{attribute} of {entity}?",
                    "dependency": 0,
                    "reasoning": "multi-hop: use entity from step 1",
                })

        if not sub_queries:
            sub_queries.append({"query": query, "dependency": None, "reasoning": "multi-hop (fallback)"})

        return sub_queries

    def _decompose_conjunctive(self, query: str, max_sub: int) -> list[dict]:
        """Decompose conjunctive questions."""
        sub_queries = []

        # Split on 'and' or 'or' at sentence level
        parts = re.split(r'\s+(?:and|or)\s+', query)
        for part in parts[:max_sub]:
            part = part.strip().rstrip("?") + "?"
            sub_queries.append({
                "query": part,
                "dependency": None,
                "reasoning": "conjunctive decomposition",
            })

        return sub_queries if sub_queries else [{"query": query, "dependency": None, "reasoning": "no decomposition"}]

    def _needs_decomposition(self, query: str) -> bool:
        """Heuristic to detect if query needs decomposition."""
        # Comparison
        if re.search(r'(vs\.?|versus|compared?\s+(to|with)|difference\s+between)', query, re.IGNORECASE):
            return True
        # Multi-hop
        if re.search(r'(?:that|who|which)\s+\w', query, re.IGNORECASE):
            return True
        # Multiple 'and' or long query
        if query.lower().count(" and ") >= 2:
            return True
        if len(query.split()) > 30:
            return True
        return False

    def _is_multi_hop(self, query: str) -> bool:
        """Detect if query requires multi-hop reasoning."""
        patterns = [
            r'(?:of|about|for)\s+(?:the\s+)?\w.*\s+(?:that|who|which)\s+',
            r'(?:first|then|after|before)\s+',
            r'(?:lead\s+to|result\s+in|cause\s+of|because)'
        ]
        return any(re.search(p, query, re.IGNORECASE) for p in patterns)
