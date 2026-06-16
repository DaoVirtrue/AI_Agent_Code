"""Clarification engine for ambiguous queries.

Proactively detects ambiguity in user queries, generates clarifying
questions, and resolves ambiguity using user follow-up responses.
"""

from __future__ import annotations

from typing import Any


class ClarificationEngine:
    """Proactively ask clarifying questions when user intent is ambiguous.

    Uses an LLM client to:
    1. Detect whether a query requires clarification
    2. Generate a targeted clarifying question
    3. Merge user clarification with the original query to resolve ambiguity

    Usage:
        engine = ClarificationEngine(llm_client)
        if await engine.should_clarify(query, context):
            question = await engine.generate_clarification_question(query, context)
            # Ask user the question, get their_clarification
            resolved = await engine.resolve_ambiguity(query, user_clarification)
    """

    def __init__(self, llm_client: Any) -> None:
        """Initialize with an LLM client.

        Args:
            llm_client: An async LLM client with a `generate` method.
        """
        self._llm = llm_client
        self._ambiguity_threshold = 0.5

    async def should_clarify(self, query: str, context: dict | None = None) -> bool:
        """Determine whether a query is ambiguous enough to warrant clarification.

        Uses the LLM to assess ambiguity level. Falls back to heuristic
        checks if the LLM is unavailable.

        Args:
            query: The user's query string.
            context: Optional dictionary with context keys like "history",
                     "entities", "topics", "slot_progress".

        Returns:
            True if clarification is recommended.
        """
        context = context or {}

        # Heuristic pre-checks (fast path)
        if self._heuristic_is_ambiguous(query):
            return True

        if self._heuristic_is_clear(query):
            return False

        # LLM-based assessment
        prompt = self._build_ambiguity_prompt(query, context)
        try:
            result = await self._llm.generate(prompt)
            # Parse score from result (expect a number between 0 and 1)
            score = self._parse_ambiguity_score(result)
            return score >= self._ambiguity_threshold
        except Exception:
            # Fallback to heuristic on LLM failure
            return self._heuristic_is_ambiguous(query)

    async def generate_clarification_question(self, query: str, context: dict | None = None) -> str:
        """Generate a targeted clarification question for an ambiguous query.

        Args:
            query: The ambiguous user query.
            context: Optional context dictionary.

        Returns:
            A natural-language clarification question.
        """
        context = context or {}
        prompt = (
            "You are a clarification assistant. The user has asked an ambiguous question. "
            "Your job is to ask a SINGLE, concise, natural clarification question that "
            "will resolve the ambiguity without overwhelming the user.\n\n"
            f"User's question: {query}\n\n"
        )
        if context.get("entities"):
            prompt += f"Known entities: {', '.join(context['entities'])}\n"
        if context.get("topics"):
            prompt += f"Discussion topics: {', '.join(context['topics'])}\n"
        if context.get("history_summary"):
            prompt += f"Recent context: {context['history_summary']}\n"

        prompt += (
            "\nClarification question (one sentence only, in the same language as the user's question):"
        )

        try:
            result = await self._llm.generate(prompt)
            question = result.strip() if result else ""
            if question:
                return question
        except Exception:
            pass

        # Fallback: generic clarification questions
        return self._generate_fallback_clarification(query)

    async def resolve_ambiguity(self, query: str, user_clarification: str) -> str:
        """Merge the user's clarification with the original query to produce a
        disambiguated query.

        Args:
            query: The original ambiguous query.
            user_clarification: The user's response to the clarification question.

        Returns:
            A resolved, unambiguous query string.
        """
        prompt = (
            "You are a query resolution assistant. Given an original ambiguous query "
            "and the user's clarification, produce a single, clear, unambiguous query "
            "that incorporates the clarification.\n\n"
            f"Original query: {query}\n"
            f"User clarification: {user_clarification}\n\n"
            "Resolved query (preserve the original language and intent):"
        )

        try:
            result = await self._llm.generate(prompt)
            resolved = result.strip() if result else query
            return resolved
        except Exception:
            # Fallback: simple concatenation
            return f"{query} ({user_clarification})"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _heuristic_is_ambiguous(self, query: str) -> bool:
        """Fast heuristic check: is the query likely ambiguous?

        Returns True for:
        - Very short queries (< 10 chars)
        - Queries with vague demonstratives without context
        - Queries that are just entity names or single words
        - Queries with multiple interpretations
        """
        q = query.strip()

        # Very short queries are often ambiguous
        if len(q) < 6:
            return True

        # Single-word queries
        if len(q.split()) == 1 and len(q) < 15:
            return True

        # Queries that are just comparisons without specifics
        comparison_patterns = [
            r'^(哪个|哪一个)更?好',
            r'^which (is|one) better',
            r'^(这|那)个怎么样',
            r'^(what about|how about) (this|that|it)',
            r'^(帮我|help me).{0,5}$',
        ]
        import re
        for pat in comparison_patterns:
            if re.match(pat, q, re.IGNORECASE):
                return True

        # Queries asking for recommendations without criteria
        recommend_patterns = [
            r'^(推荐|建议|有什么).{0,5}$',
            r'^(recommend|suggest).{0,5}$',
        ]
        for pat in recommend_patterns:
            if re.match(pat, q, re.IGNORECASE):
                return True

        return False

    def _heuristic_is_clear(self, query: str) -> bool:
        """Fast heuristic check: is the query clearly unambiguous?

        Returns True for long, detailed queries with specific entities.
        """
        q = query.strip()

        # Long, detailed queries are usually clear
        if len(q) > 100:
            return True

        # Queries with specific numbers/dates/entities are usually clear
        import re
        has_specifics = (
            re.search(r'\d{4}[-/年]', q)  # dates
            or re.search(r'\d+\.?\d*\s*[%百分]', q)  # percentages
            or re.search(r'[¥$]\s*\d+', q)  # money
            or re.search(r'(?:公司|集团|银行|医院|大学|部门)', q)  # entities
            or re.search(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b', q)  # proper nouns
        )
        if has_specifics and len(q) > 20:
            return True

        return False

    def _build_ambiguity_prompt(self, query: str, context: dict) -> str:
        """Build the ambiguity detection prompt."""
        prompt = (
            "Analyze whether the following user query is ambiguous and requires clarification. "
            "Rate ambiguity on a scale of 0.0 (completely clear) to 1.0 (completely ambiguous). "
            "Consider: missing subjects, vague references, multiple interpretations, "
            "unspecified criteria, incomplete information.\n\n"
            f"User query: {query}\n"
        )
        if context.get("history_summary"):
            prompt += f"Conversation context: {context['history_summary']}\n"
        prompt += "\nReturn ONLY a number between 0.0 and 1.0:"
        return prompt

    def _parse_ambiguity_score(self, result: str) -> float:
        """Parse an ambiguity score from LLM output."""
        import re
        # Try to find a float in the result
        match = re.search(r'(\d+\.?\d*)', result)
        if match:
            score = float(match.group(1))
            return max(0.0, min(1.0, score))
        # If the result contains ambiguity keywords
        if any(word in result.lower() for word in ['ambiguous', 'unclear', 'vague', '模糊', '不明确']):
            return 0.7
        if any(word in result.lower() for word in ['clear', 'specific', '明确', '清楚']):
            return 0.3
        return 0.5

    def _generate_fallback_clarification(self, query: str) -> str:
        """Generate a generic clarification question when LLM is unavailable."""
        q = query.strip()
        if len(q) < 10:
            return f"Could you provide more details about '{q}'?"
        if len(q.split()) <= 2:
            return f"Could you be more specific about what you mean by '{q}'?"
        return "Could you clarify what specifically you're looking for?"
