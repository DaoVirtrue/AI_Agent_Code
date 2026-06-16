"""Answer voting for ensemble RAG generation.

Generates multiple answer candidates using different strategies/models
and votes on the best answer to improve reliability.
"""

import logging
import re
from collections import Counter
from typing import Any, Optional

logger = logging.getLogger(__name__)


class AnswerVoting:
    """Ensemble answer generation with voting.

    Generates multiple candidate answers and selects the best one
    through voting. Strategies:

    1. Majority voting: Pick the most common answer format
    2. Weighted voting: Weight answers by quality scores
    3. Consensus: Synthesize a consensus from multiple answers
    4. Best-of-N: Pick the answer with highest quality score
    """

    def __init__(self, llm_client=None, num_candidates: int = 3):
        """Initialize answer voting.

        Args:
            llm_client: LLM client for answer generation and synthesis
            num_candidates: Number of candidate answers to generate
        """
        self.llm_client = llm_client
        self.num_candidates = num_candidates
        logger.info("AnswerVoting initialized (candidates=%d)", num_candidates)

    async def vote(
        self,
        query: str,
        candidates: list[dict],
        sources: Optional[list[dict]] = None,
        method: str = "weighted",
    ) -> dict:
        """Vote on the best answer from candidates.

        Args:
            query: Original query
            candidates: List of {answer, score, source_count, metadata} dicts
            sources: Source documents
            method: Voting method: "majority", "weighted", "consensus", "best"

        Returns:
            Dict with {answer, confidence, method, votes, all_candidates}
        """
        if not candidates:
            return {"answer": "No candidates available", "confidence": 0.0, "method": "none", "votes": {}}

        if method == "majority":
            result = self._majority_vote(candidates)
        elif method == "weighted":
            result = self._weighted_vote(candidates)
        elif method == "consensus":
            result = await self._consensus_vote(query, candidates, sources)
        elif method == "best":
            result = self._best_of_n(candidates)
        else:
            result = self._weighted_vote(candidates)

        return {
            **result,
            "all_candidates": candidates,
        }

    def _majority_vote(self, candidates: list[dict]) -> dict:
        """Simple majority voting: pick the most frequent answer (normalized)."""
        # Normalize and count answers
        answer_counts = Counter()
        normalized_map = {}

        for i, candidate in enumerate(candidates):
            normalized = self._normalize_for_comparison(candidate.get("answer", ""))
            answer_counts[normalized] += 1
            if normalized not in normalized_map:
                normalized_map[normalized] = i

        # Find the most common (first tie-breaking by original order)
        most_common_normalized = answer_counts.most_common(1)[0][0]
        best_idx = normalized_map[most_common_normalized]
        best = candidates[best_idx]

        return {
            "answer": best.get("answer", ""),
            "confidence": answer_counts[most_common_normalized] / len(candidates),
            "method": "majority",
            "votes": dict(answer_counts),
        }

    def _weighted_vote(self, candidates: list[dict]) -> dict:
        """Weighted voting based on answer scores."""
        if not candidates:
            return {"answer": "", "confidence": 0.0, "method": "weighted", "votes": {}}

        # Weight by score and source count
        weights = []
        for c in candidates:
            score = float(c.get("score", 0.5))
            sources = int(c.get("source_count", 0))
            # Bonus for using more sources
            weight = score * (1.0 + 0.1 * min(sources, 5))
            weights.append(weight)

        total_weight = sum(weights)
        if total_weight == 0:
            return {"answer": candidates[0].get("answer", ""), "confidence": 0.0, "method": "weighted", "votes": {"none": 1}}

        # Normalize weights
        norm_weights = [w / total_weight for w in weights]

        # Select highest weighted
        best_idx = max(range(len(norm_weights)), key=lambda i: norm_weights[i])

        return {
            "answer": candidates[best_idx].get("answer", ""),
            "confidence": norm_weights[best_idx],
            "method": "weighted",
            "weights": norm_weights,
        }

    async def _consensus_vote(
        self, query: str, candidates: list[dict], sources: Optional[list[dict]]
    ) -> dict:
        """Synthesize a consensus answer from all candidates."""
        if not self.llm_client:
            return self._weighted_vote(candidates)

        # Present all candidates to LLM for synthesis
        candidate_text = "\n\n---\n\n".join([
            f"Candidate {i+1} (score: {c.get('score', 'N/A')}):\n{c.get('answer', '')}"
            for i, c in enumerate(candidates)
        ])

        prompt = f"""Synthesize a single consensus answer from the following candidate answers.
Combine the best elements, resolve contradictions, and produce a comprehensive final answer.

Query: {query}

{candidate_text}

Consensus answer:"""

        try:
            if hasattr(self.llm_client, 'generate'):
                consensus = await self.llm_client.generate(prompt)
            else:
                consensus = str(self.llm_client(prompt))

            return {
                "answer": str(consensus).strip(),
                "confidence": 0.85,  # Consensus is generally more reliable
                "method": "consensus",
                "candidate_count": len(candidates),
            }
        except Exception as e:
            logger.error("Consensus voting error: %s", e)
            return self._weighted_vote(candidates)

    def _best_of_n(self, candidates: list[dict]) -> dict:
        """Pick the single best candidate by quality score."""
        best = max(candidates, key=lambda c: (
            float(c.get("score", 0)) * 0.6 +
            float(c.get("source_count", 0)) * 0.2 +
            len(str(c.get("answer", ""))) * 0.0002  # Prefer substantive answers
        ))

        return {
            "answer": best.get("answer", ""),
            "confidence": float(best.get("score", 0.5)),
            "method": "best_of_n",
            "best_index": candidates.index(best),
        }

    def _normalize_for_comparison(self, text: str) -> str:
        """Normalize answer text for comparison."""
        text = text.lower().strip()
        # Remove common prefixes/suffixes
        text = re.sub(r'^(answer|response|result)[\s:]+', '', text)
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text)
        # Truncate for comparison
        return text[:200]

    @staticmethod
    def rank_candidates(
        candidates: list[dict],
        metric: str = "score",
    ) -> list[dict]:
        """Rank candidates by a given metric."""
        reverse = True  # Higher is better
        return sorted(candidates, key=lambda c: float(c.get(metric, 0)), reverse=reverse)
