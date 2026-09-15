"""Adaptive RAG router for dynamic retrieval strategy selection."""

import logging
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class RAGStrategy(str, Enum):
    """Available RAG strategies."""
    NO_RETRIEVAL = "no_retrieval"
    SINGLE_STEP = "single_step"
    MULTI_STEP = "multi_step"
    ITERATIVE = "iterative"
    SUMMARY_BASED = "summary_based"


class AdaptiveRAGRouter:
    """Adaptively select the best RAG strategy based on query complexity.

    Dynamically chooses the appropriate retrieval strategy:
    - No Retrieval: Simple questions, greetings, common knowledge
    - Single Step: Factoid, straightforward lookup
    - Multi Step: Multi-hop questions requiring decomposition
    - Iterative: Complex questions needing refinement
    - Summary Based: Broad topics needing document synthesis

    The router can learn from feedback to improve future routing.
    """

    def __init__(self, llm_client=None):
        """Initialize adaptive router.

        Args:
            llm_client: Optional LLM for classification
        """
        self.llm_client = llm_client
        self._strategy_stats: dict[str, dict] = {
            s.value: {"uses": 0, "successes": 0}
            for s in RAGStrategy
        }
        logger.info("AdaptiveRAGRouter initialized")

    async def route(
        self,
        query: str,
        conversation_history: Optional[list[dict]] = None,
    ) -> dict:
        """Route a query to the best RAG strategy.

        Returns dict with {strategy, confidence, reasoning, params}.
        """
        # Check if retrieval is even needed
        if self._is_trivial(query):
            return self._make_result(RAGStrategy.NO_RETRIEVAL, 0.95, "simple conversational query")

        # Classify query complexity
        if self.llm_client:
            return await self._llm_classify(query, conversation_history)
        else:
            return self._heuristic_classify(query)

    async def _llm_classify(self, query: str, history=None) -> dict:
        """Use LLM to classify query complexity."""
        prompt = f"""Classify this query into one of these categories:
- no_retrieval: Simple greeting, chitchat, or common knowledge
- single_step: Factoid question, single fact lookup
- multi_step: Multi-hop question requiring multiple information sources
- iterative: Question that may need follow-up or refinement
- summary_based: Broad topic requiring synthesis of many sources

Query: {query}

Respond in JSON: {{"category": "...", "confidence": 0.0-1.0, "reasoning": "..."}}"""

        try:
            import json
            if hasattr(self.llm_client, 'generate'):
                response = await self.llm_client.generate(prompt)
            else:
                response = str(self.llm_client(prompt))

            result = json.loads(str(response))
            category = result.get("category", "single_step")

            strategy_map = {
                "no_retrieval": RAGStrategy.NO_RETRIEVAL,
                "single_step": RAGStrategy.SINGLE_STEP,
                "multi_step": RAGStrategy.MULTI_STEP,
                "iterative": RAGStrategy.ITERATIVE,
                "summary_based": RAGStrategy.SUMMARY_BASED,
            }

            strategy = strategy_map.get(category, RAGStrategy.SINGLE_STEP)
            return self._make_result(
                strategy,
                float(result.get("confidence", 0.7)),
                result.get("reasoning", "LLM-classified"),
            )
        except Exception as e:
            logger.error("Adaptive routing error: %s", e)
            return self._heuristic_classify(query)

    def _heuristic_classify(self, query: str) -> dict:
        """Heuristic-based query classification."""
        words = query.lower().split()
        length = len(words)

        # Very short = no retrieval
        if length <= 3:
            return self._make_result(RAGStrategy.NO_RETRIEVAL, 0.8, "very short query")

        # Long + comparison keywords = multi_step
        if length > 20 and any(w in words for w in ["compare", "vs", "versus", "difference"]):
            return self._make_result(RAGStrategy.MULTI_STEP, 0.7, "comparison query")

        # Contains "why" or "explain" = iterative
        if any(w in words for w in ["why", "explain", "analyze", "reason"]):
            return self._make_result(RAGStrategy.ITERATIVE, 0.6, "analytical query")

        # Contains summarization keywords = summary_based
        if any(w in words for w in ["summary", "overview", "summarize", "everything"]):
            return self._make_result(RAGStrategy.SUMMARY_BASED, 0.7, "summarization request")

        # Default
        return self._make_result(RAGStrategy.SINGLE_STEP, 0.5, "default single-step")

    def _is_trivial(self, query: str) -> bool:
        """Check if query is a trivial conversational turn."""
        trivial = {"hi", "hello", "hey", "thanks", "thank you", "bye", "ok", "okay", "yes", "no"}
        cleaned = query.lower().strip().rstrip(".!?")
        return cleaned in trivial or len(cleaned) <= 2

    def _make_result(self, strategy: RAGStrategy, confidence: float, reasoning: str) -> dict:
        """Build consistent result dict."""
        params_map = {
            RAGStrategy.NO_RETRIEVAL: {"skip_retrieval": True},
            RAGStrategy.SINGLE_STEP: {"top_k": 5, "use_hyde": True, "use_rerank": True},
            RAGStrategy.MULTI_STEP: {"top_k": 10, "decompose": True, "max_sub_queries": 3},
            RAGStrategy.ITERATIVE: {"top_k": 8, "max_iterations": 3, "refine": True},
            RAGStrategy.SUMMARY_BASED: {"top_k": 20, "use_compression": True, "max_sources": 10},
        }

        return {
            "strategy": strategy.value,
            "confidence": confidence,
            "reasoning": reasoning,
            "params": params_map.get(strategy, {"top_k": 5}),
        }

    def record_feedback(self, strategy: str, successful: bool) -> None:
        """Record feedback on strategy effectiveness for learning."""
        if strategy in self._strategy_stats:
            self._strategy_stats[strategy]["uses"] += 1
            if successful:
                self._strategy_stats[strategy]["successes"] += 1

    def get_strategy_stats(self) -> dict:
        """Get strategy usage and success statistics."""
        stats = {}
        for strategy, data in self._strategy_stats.items():
            uses = data["uses"]
            successes = data["successes"]
            stats[strategy] = {
                "uses": uses,
                "successes": successes,
                "success_rate": successes / max(uses, 1),
            }
        return stats
