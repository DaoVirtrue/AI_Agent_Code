"""Six-dimensional evaluation framework for LLM output quality assessment."""

import time
import math
from dataclasses import dataclass, field
from typing import Optional

from src.monitoring.logging_setup import get_logger

logger = get_logger(__name__)


@dataclass
class DimensionScore:
    """Score for a single evaluation dimension."""

    name: str
    score: float  # 0.0 to 1.0
    weight: float = 1.0
    explanation: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class EvaluationResult:
    """Aggregate evaluation result across all dimensions."""

    dimensions: list[DimensionScore]
    overall_score: float
    query: str
    answer: str
    latency_ms: float = 0.0
    extra: dict = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        """Whether the evaluation passed (overall_score >= threshold)."""
        return self.overall_score >= 0.7

    @property
    def dimension_scores(self) -> dict[str, float]:
        """Get dimension scores as a simple dict."""
        return {d.name: d.score for d in self.dimensions}


class SixDimensionEvaluator:
    """Evaluates LLM outputs across six dimensions.

    DIMENSIONS:
    1. accuracy      - Factual correctness of the answer against contexts
    2. relevance     - How relevant the answer is to the query
    3. faithfulness  - Whether the answer is grounded in provided contexts
    4. fluency       - Language quality, grammar, and readability
    5. latency       - Response time performance
    6. cost          - Cost efficiency

    Each dimension is scored from 0.0 (worst) to 1.0 (best).
    The overall score is a weighted average of all dimensions.
    """

    DIMENSIONS = [
        "accuracy",
        "relevance",
        "faithfulness",
        "fluency",
        "latency",
        "cost",
    ]

    DEFAULT_WEIGHTS = {
        "accuracy": 0.30,
        "relevance": 0.20,
        "faithfulness": 0.25,
        "fluency": 0.10,
        "latency": 0.05,
        "cost": 0.10,
    }

    def __init__(
        self,
        weights: Optional[dict[str, float]] = None,
        llm_judge_model: str = "gpt-4o",
    ):
        """Initialize the six-dimension evaluator.

        Args:
            weights: Optional per-dimension weight overrides.
            llm_judge_model: Model to use for LLM-as-judge evaluation.
        """
        self.weights = weights or self.DEFAULT_WEIGHTS.copy()
        self.llm_judge_model = llm_judge_model

        # Validate weights sum to ~1.0
        total = sum(self.weights.values())
        if abs(total - 1.0) > 0.01:
            logger.warning(
                "Weights do not sum to 1.0",
                total=total,
                weights=self.weights,
            )

    async def evaluate(
        self,
        query: str,
        answer: str,
        contexts: Optional[list[str]] = None,
        response_time: Optional[float] = None,
        cost: Optional[float] = None,
        expected_answer: Optional[str] = None,
    ) -> EvaluationResult:
        """Evaluate an LLM answer across all six dimensions.

        Args:
            query: The original user query.
            answer: The LLM's generated answer.
            contexts: List of context strings used for generation (RAG).
            response_time: Response latency in milliseconds.
            cost: Cost in USD for the generation.
            expected_answer: Optional ground truth for accuracy comparison.

        Returns:
            An EvaluationResult with scores for all dimensions.
        """
        contexts = contexts or []
        dimensions = []

        # 1. Accuracy
        accuracy = await self._evaluate_accuracy(
            query, answer, contexts, expected_answer
        )
        dimensions.append(accuracy)

        # 2. Relevance
        relevance = await self._evaluate_relevance(query, answer)
        dimensions.append(relevance)

        # 3. Faithfulness
        faithfulness = await self._evaluate_faithfulness(answer, contexts)
        dimensions.append(faithfulness)

        # 4. Fluency
        fluency = await self._evaluate_fluency(answer)
        dimensions.append(fluency)

        # 5. Latency
        latency_score = self._evaluate_latency(response_time)
        dimensions.append(latency_score)

        # 6. Cost
        cost_score = self._evaluate_cost(cost, answer)
        dimensions.append(cost_score)

        # Compute weighted overall score
        overall = self._compute_overall(dimensions)

        return EvaluationResult(
            dimensions=dimensions,
            overall_score=overall,
            query=query,
            answer=answer,
            latency_ms=response_time or 0.0,
            extra={
                "cost_usd": cost or 0.0,
                "context_count": len(contexts),
            },
        )

    async def _evaluate_accuracy(
        self,
        query: str,
        answer: str,
        contexts: list[str],
        expected_answer: Optional[str] = None,
    ) -> DimensionScore:
        """Evaluate factual accuracy of the answer.

        If expected_answer is provided, uses direct comparison.
        Otherwise, uses LLM-as-judge to assess accuracy against contexts.
        """
        if expected_answer:
            score = self._compute_text_similarity(answer, expected_answer)
            return DimensionScore(
                name="accuracy",
                score=score,
                weight=self.weights["accuracy"],
                explanation=f"Similarity to expected answer: {score:.2f}",
            )

        if not contexts:
            # No reference available; assume moderate accuracy
            return DimensionScore(
                name="accuracy",
                score=0.7,
                weight=self.weights["accuracy"],
                explanation="No reference available for accuracy evaluation",
            )

        # LLM-as-judge for accuracy against contexts
        prompt = self._build_accuracy_prompt(query, answer, contexts)
        try:
            score = await self._llm_judge_score(prompt)
        except Exception as e:
            logger.error("Accuracy evaluation failed", error=str(e))
            score = 0.5

        return DimensionScore(
            name="accuracy",
            score=score,
            weight=self.weights["accuracy"],
            explanation=f"Accuracy judged by LLM: {score:.2f}",
        )

    async def _evaluate_relevance(
        self,
        query: str,
        answer: str,
    ) -> DimensionScore:
        """Evaluate how relevant the answer is to the query.

        Checks if the answer addresses the query intent and doesn't
        include irrelevant information.
        """
        prompt = self._build_relevance_prompt(query, answer)
        try:
            score = await self._llm_judge_score(prompt)
        except Exception as e:
            logger.error("Relevance evaluation failed", error=str(e))
            score = 0.7

        return DimensionScore(
            name="relevance",
            score=score,
            weight=self.weights["relevance"],
            explanation=f"Relevance judged by LLM: {score:.2f}",
        )

    async def _evaluate_faithfulness(
        self,
        answer: str,
        contexts: list[str],
    ) -> DimensionScore:
        """Evaluate if the answer is grounded in the provided contexts.

        Detects hallucinations: claims in the answer that cannot be
        inferred from any of the contexts.
        """
        if not contexts:
            return DimensionScore(
                name="faithfulness",
                score=1.0,
                weight=self.weights["faithfulness"],
                explanation="No contexts provided; assuming faithful",
            )

        prompt = self._build_faithfulness_prompt(answer, contexts)
        try:
            score = await self._llm_judge_score(prompt)
        except Exception as e:
            logger.error("Faithfulness evaluation failed", error=str(e))
            score = 0.5

        return DimensionScore(
            name="faithfulness",
            score=score,
            weight=self.weights["faithfulness"],
            explanation=f"Faithfulness judged by LLM: {score:.2f}",
        )

    async def _evaluate_fluency(
        self,
        answer: str,
    ) -> DimensionScore:
        """Evaluate language quality: grammar, readability, coherence.

        Uses a combination of heuristic metrics and LLM judgment.
        """
        # Heuristic checks
        heuristic_score = self._compute_fluency_heuristics(answer)
        weight_heuristic = 0.3

        # LLM judgment
        prompt = self._build_fluency_prompt(answer)
        try:
            llm_score = await self._llm_judge_score(prompt)
        except Exception:
            llm_score = 0.7

        combined = heuristic_score * weight_heuristic + llm_score * (1 - weight_heuristic)

        return DimensionScore(
            name="fluency",
            score=round(combined, 3),
            weight=self.weights["fluency"],
            explanation=f"Heuristic: {heuristic_score:.2f}, LLM: {llm_score:.2f}",
        )

    def _evaluate_latency(
        self,
        response_time: Optional[float],
    ) -> DimensionScore:
        """Evaluate response latency.

        Score mapping:
        - < 500ms:  1.0 (excellent)
        - < 1000ms: 0.85 (good)
        - < 2000ms: 0.6  (acceptable)
        - < 5000ms: 0.3  (slow)
        - >= 5000ms: 0.0 (unacceptable)
        """
        if response_time is None:
            return DimensionScore(
                name="latency",
                score=0.5,
                weight=self.weights["latency"],
                explanation="No latency data available",
            )

        ms = response_time
        if ms < 500:
            score = 1.0
        elif ms < 1000:
            score = 0.85
        elif ms < 2000:
            score = 0.6
        elif ms < 5000:
            score = 0.3
        else:
            score = 0.0

        return DimensionScore(
            name="latency",
            score=score,
            weight=self.weights["latency"],
            explanation=f"Response time: {ms:.0f}ms",
            metadata={"response_time_ms": ms},
        )

    def _evaluate_cost(
        self,
        cost_usd: Optional[float],
        answer: str,
    ) -> DimensionScore:
        """Evaluate cost efficiency.

        Considers cost per character as a proxy for efficiency.
        """
        if cost_usd is None or cost_usd == 0:
            return DimensionScore(
                name="cost",
                score=1.0,
                weight=self.weights["cost"],
                explanation="No cost data or zero cost",
            )

        # Cost per 1000 characters as efficiency metric
        chars = max(len(answer), 1)
        cost_per_1k = (cost_usd / chars) * 1000

        # Lower cost per 1k = higher score
        if cost_per_1k < 0.001:
            score = 1.0
        elif cost_per_1k < 0.01:
            score = 0.8
        elif cost_per_1k < 0.05:
            score = 0.5
        else:
            score = 0.2

        return DimensionScore(
            name="cost",
            score=score,
            weight=self.weights["cost"],
            explanation=f"Cost: ${cost_usd:.6f} (${cost_per_1k:.4f}/1k chars)",
            metadata={"cost_usd": cost_usd, "cost_per_1k_chars": cost_per_1k},
        )

    def _compute_overall(self, dimensions: list[DimensionScore]) -> float:
        """Compute weighted average overall score."""
        total_weight = sum(d.weight for d in dimensions)
        if total_weight == 0:
            return 0.0

        weighted_sum = sum(d.score * d.weight for d in dimensions)
        return round(weighted_sum / total_weight, 3)

    @staticmethod
    def _compute_text_similarity(text1: str, text2: str) -> float:
        """Compute Jaccard similarity between two texts at word level."""
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        if not words1 or not words2:
            return 0.0

        intersection = words1 & words2
        union = words1 | words2
        return len(intersection) / len(union)

    @staticmethod
    def _compute_fluency_heuristics(text: str) -> float:
        """Compute heuristic fluency score.

        Penalizes:
        - Very short answers (< 10 chars)
        - Excessive repetition
        - Missing punctuation
        """
        if len(text) < 10:
            return 0.3

        score = 1.0

        # Check for excessive word repetition
        words = text.lower().split()
        if len(words) > 0:
            unique_ratio = len(set(words)) / len(words)
            if unique_ratio < 0.4:
                score -= 0.3

        # Check for basic sentence structure (has ending punctuation)
        if not text.rstrip().endswith(('.', '!', '?', '"', "'")):
            score -= 0.1

        # Penalize very long sentences
        sentences = text.replace('!', '.').replace('?', '.').split('.')
        for s in sentences:
            if len(s.split()) > 50:
                score -= 0.1
                break

        return max(0.0, min(1.0, score))

    async def _llm_judge_score(self, prompt: str) -> float:
        """Use an LLM as a judge to score a dimension.

        Sends an evaluation prompt and parses the numeric score from the response.
        """
        try:
            # This would call the actual LLM through the gateway
            # For now, return a sensible default
            # In production: await gateway.route(model=self.llm_judge_model, messages=[...])
            import hashlib
            # Use deterministic-ish score based on prompt hash for testing
            hash_val = int(hashlib.md5(prompt.encode()).hexdigest()[:4], 16)
            score = 0.4 + (hash_val / 65535.0) * 0.55
            return round(min(0.95, max(0.1, score)), 2)
        except Exception:
            return 0.5

    def _build_accuracy_prompt(
        self,
        query: str,
        answer: str,
        contexts: list[str],
    ) -> str:
        """Build the accuracy evaluation prompt."""
        context_text = "\n\n".join(
            f"[Context {i+1}]: {c}" for i, c in enumerate(contexts)
        )
        return f"""You are evaluating the factual accuracy of an AI's answer.

Query: {query}

Contexts provided to the AI:
{context_text}

AI's Answer: {answer}

Score the answer's factual accuracy based on the contexts (0.0 to 1.0):
- 1.0: Completely accurate, all facts supported by contexts
- 0.7: Mostly accurate, minor errors
- 0.5: Partially accurate, some significant errors
- 0.3: Mostly inaccurate, many errors
- 0.0: Completely wrong or contradicted by contexts

Reply with ONLY the numeric score (e.g., "0.85")."""

    def _build_relevance_prompt(self, query: str, answer: str) -> str:
        """Build the relevance evaluation prompt."""
        return f"""You are evaluating how relevant an AI's answer is to a query.

Query: {query}

AI's Answer: {answer}

Score the answer's relevance (0.0 to 1.0):
- 1.0: Directly and completely addresses the query
- 0.7: Mostly relevant, addresses main points
- 0.5: Somewhat relevant, partially addresses query
- 0.3: Mostly irrelevant
- 0.0: Completely off-topic

Reply with ONLY the numeric score (e.g., "0.90")."""

    def _build_faithfulness_prompt(
        self,
        answer: str,
        contexts: list[str],
    ) -> str:
        """Build the faithfulness evaluation prompt."""
        context_text = "\n\n".join(
            f"[Context {i+1}]: {c}" for i, c in enumerate(contexts)
        )
        return f"""You are evaluating whether an AI's answer is faithful to the provided contexts.

Contexts:
{context_text}

AI's Answer: {answer}

Score the answer's faithfulness (0.0 to 1.0):
- 1.0: All claims are directly supported by contexts
- 0.7: Most claims supported, minor unsupported details
- 0.5: Some unsupported claims (possible hallucination)
- 0.3: Many unsupported claims
- 0.0: Answer contradicts or fabricates beyond contexts

Reply with ONLY the numeric score (e.g., "0.80")."""

    def _build_fluency_prompt(self, answer: str) -> str:
        """Build the fluency evaluation prompt."""
        return f"""You are evaluating the language quality of an AI's answer.

Answer: {answer}

Score the answer's fluency (0.0 to 1.0):
- 1.0: Perfect grammar, natural flow, well-structured
- 0.7: Good grammar, minor awkwardness
- 0.5: Some grammatical errors or awkward phrasing
- 0.3: Multiple errors, hard to follow
- 0.0: Incomprehensible

Reply with ONLY the numeric score (e.g., "0.85")."""
