"""Query router for adaptive RAG strategies."""

import logging
import re
from typing import Any, Optional, Literal

logger = logging.getLogger(__name__)

# Define possible routing paths
RouteType = Literal[
    "simple",        # Single-hop, answerable from one doc
    "multi_hop",     # Requires multiple documents
    "comparison",    # Comparing multiple entities
    "summarization", # Needs summarization of many docs
    "factoid",       # Simple fact lookup
    "analytical",    # Needs reasoning and analysis
    "code",          # Code-related query
    "direct",        # Answer without retrieval (greetings, etc.)
    "unknown",       # Cannot determine
]


class QueryRouter:
    """Route queries to appropriate retrieval strategies.

    Different query types benefit from different retrieval approaches:
    - Simple factoid questions: basic dense retrieval
    - Multi-hop questions: decomposed retrieval
    - Comparison questions: parallel entity retrieval
    - Summarization: broad retrieval + compression

    This router analyzes the query and determines the optimal strategy.
    """

    # Patterns for routing classification
    PATTERNS = {
        "factoid": [
            r'^(?:what|who|when|where)\s+(?:is|was|are|were)\s+',
            r'^(?:how\s+(?:many|much|tall|big|old|far|long))\s+',
            r'^(?:define|definition\s+of)\s+',
        ],
        "comparison": [
            r'\b(?:vs\.?|versus|compared?\s+(?:to|with)|difference\s+between|similarities?\s+between)\b',
            r'\b(?:better|worse|faster|slower|cheaper|more\s+expensive)\s+(?:than|between)\b',
        ],
        "multi_hop": [
            r'\b(?:that|who|which)\s+\w.*\b(?:of|from|in|by)\b',
            r'\b(?:first|then|after|before|subsequently|following)\b.*\b(?:then|next|after)\b',
            r'\b(?:relationship\s+between|connection\s+between|impact\s+of.*on)\b',
        ],
        "summarization": [
            r'\b(?:summarize|summary|overview|sum\s+up|tldr|recap|digest)\b',
            r'\b(?:what\s+are\s+the\s+(?:main|key|major|important))\b',
            r'\b(?:tell\s+me\s+(?:about|everything|all))\b',
        ],
        "analytical": [
            r'\b(?:why|how\s+come|what\s+(?:causes?|makes?|leads?\s+to))\b',
            r'\b(?:analyze|analysis|explain|reason|justify)\b',
            r'\b(?:cause|effect|consequence|implication|significance)\b',
        ],
        "code": [
            r'\b(?:code|function|class|method|api|endpoint|sdk|library|framework|bug|error|exception)\b',
            r'\b(?:programming|python|javascript|java|golang|rust|typescript|react|vue)\b',
            r'\b(?:how\s+(?:to|do\s+I)\s+(?:write|code|implement|build|create|fix|debug))\b',
        ],
        "direct": [
            r'^(?:hi|hello|hey|good\s+(?:morning|afternoon|evening)|thanks?|thank\s+you|bye|ok|okay)$',
        ],
    }

    def __init__(self, llm_client=None):
        """Initialize query router.

        Args:
            llm_client: Optional LLM for more accurate routing classification
        """
        self.llm_client = llm_client
        logger.info("QueryRouter initialized (llm=%s)", "available" if llm_client else "pattern-based")

    async def route(self, query: str) -> dict:
        """Route a query to the appropriate retrieval strategy.

        Args:
            query: User query text

        Returns:
            Dict with {path, confidence, reasoning, strategy_params}
        """
        # Quick check for direct/no-retrieval queries
        if self._is_direct(query):
            return {
                "path": "direct",
                "confidence": 1.0,
                "reasoning": "Greeting or simple statement, no retrieval needed",
                "strategy_params": {"skip_retrieval": True},
            }

        if self.llm_client:
            return await self._llm_route(query)
        else:
            return self._pattern_route(query)

    async def _llm_route(self, query: str) -> dict:
        """Use LLM for query routing classification."""
        prompt = f"""Classify the following query into one of these categories:
- simple: A straightforward question answerable from a single document
- multi_hop: Requires information from multiple documents to answer
- comparison: Comparing two or more entities/concepts
- summarization: Asking for a summary or overview of a broad topic
- factoid: A simple fact-based question
- analytical: Requires reasoning, analysis, or explanation
- code: Related to programming, code, or technical implementation
- direct: A greeting or simple statement not needing retrieval

Query: {query}

Respond in JSON: {{"category": "...", "confidence": 0.0-1.0, "reasoning": "..."}}"""

        try:
            import json
            if hasattr(self.llm_client, 'generate'):
                response = await self.llm_client.generate(prompt)
            else:
                response = str(self.llm_client(prompt))

            result = json.loads(str(response))

            path = result.get("category", "simple")
            if path not in ["simple", "multi_hop", "comparison", "summarization", "factoid", "analytical", "code", "direct"]:
                path = "simple"

            return {
                "path": path,
                "confidence": float(result.get("confidence", 0.7)),
                "reasoning": result.get("reasoning", "LLM-classified"),
                "strategy_params": self._get_strategy_params(path, query),
            }
        except Exception as e:
            logger.error("LLM routing error: %s", e)
            return self._pattern_route(query)

    def _pattern_route(self, query: str) -> dict:
        """Pattern-based routing using regex matching."""
        lower = query.lower()
        scores: dict[str, float] = {}

        for category, patterns in self.PATTERNS.items():
            score = 0.0
            for pattern in patterns:
                if re.search(pattern, lower):
                    score += 1.0
            if score > 0:
                scores[category] = min(score / len(patterns), 1.0)

        if not scores:
            return {
                "path": "simple",
                "confidence": 0.5,
                "reasoning": "No specific patterns matched, defaulting to simple retrieval",
                "strategy_params": {"top_k": 5},
            }

        # Pick highest scoring category
        best_category = max(scores, key=scores.get)
        confidence = scores[best_category]

        return {
            "path": best_category,
            "confidence": confidence,
            "reasoning": f"Matched {best_category} patterns (score: {confidence:.2f})",
            "strategy_params": self._get_strategy_params(best_category, query),
        }

    def _get_strategy_params(self, path: str, query: str) -> dict:
        """Get retrieval strategy parameters for a given path."""
        strategies = {
            "simple": {"top_k": 5, "use_hyde": True, "use_rerank": True},
            "multi_hop": {"top_k": 10, "decompose": True, "use_hyde": True, "max_sub_queries": 3},
            "comparison": {"top_k": 8, "use_hyde": True, "parallel_entities": True},
            "summarization": {"top_k": 15, "use_hyde": False, "use_summarization_compression": True},
            "factoid": {"top_k": 3, "use_hyde": False, "focus_on_accuracy": True},
            "analytical": {"top_k": 10, "use_hyde": True, "use_rerank": True, "chain_of_thought": True},
            "code": {"top_k": 5, "use_hyde": False, "bm25_weight": 0.7, "code_snippets": True},
            "direct": {"skip_retrieval": True, "top_k": 0},
        }
        return strategies.get(path, {"top_k": 5})

    def _is_direct(self, query: str) -> bool:
        """Check if query is a direct conversational turn (no retrieval needed)."""
        cleaned = query.lower().strip().rstrip(".!?")

        greetings = {"hi", "hello", "hey", "good morning", "good afternoon", "good evening",
                     "thanks", "thank you", "thx", "bye", "goodbye", "see you", "ok", "okay"}

        if cleaned in greetings or len(cleaned) <= 3:
            return True

        for pattern in self.PATTERNS["direct"]:
            if re.match(pattern, cleaned):
                return True

        return False
