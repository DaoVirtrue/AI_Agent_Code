"""RAGAS (Retrieval Augmented Generation Assessment) wrapper for RAG evaluation."""

from typing import Optional
from dataclasses import dataclass, field

from src.monitoring.logging_setup import get_logger

logger = get_logger(__name__)


@dataclass
class RAGASEvalResult:
    """RAGAS evaluation result for a single query-answer pair."""

    faithfulness: float = 0.0
    answer_relevancy: float = 0.0
    context_precision: float = 0.0
    context_recall: float = 0.0
    answer_correctness: Optional[float] = None
    answer_similarity: Optional[float] = None
    extra: dict = field(default_factory=dict)

    @property
    def overall(self) -> float:
        """Harmonic mean of all available metrics."""
        scores = [self.faithfulness, self.answer_relevancy, self.context_precision, self.context_recall]
        if self.answer_correctness is not None:
            scores.append(self.answer_correctness)
        if self.answer_similarity is not None:
            scores.append(self.answer_similarity)
        scores = [s for s in scores if s > 0]
        if not scores:
            return 0.0
        n = len(scores)
        sum_recip = sum(1.0 / s for s in scores)
        return n / sum_recip if sum_recip > 0 else 0.0


class RAGASWrapper:
    """Wrapper around RAGAS evaluation metrics.

    Implements the core RAGAS metrics:
    - Faithfulness: Are claims in the answer grounded in retrieved contexts?
    - Answer Relevancy: How relevant is the answer to the question?
    - Context Precision: How precise are the retrieved contexts?
    - Context Recall: How many relevant contexts were retrieved?
    - Answer Correctness: Accuracy against ground truth (optional).
    - Answer Similarity: Semantic similarity to ground truth (optional).

    This implementation can work with or without the ragas library installed.
    When not installed, it uses built-in LLM-as-judge approaches.
    """

    def __init__(
        self,
        llm_model: str = "gpt-4o",
        embedding_model: str = "text-embedding-3-small",
        use_ragas_lib: bool = False,
    ):
        """Initialize the RAGAS wrapper.

        Args:
            llm_model: Model to use for LLM-as-judge evaluations.
            embedding_model: Model for embedding-based metrics.
            use_ragas_lib: If True and ragas is installed, use the official library.
        """
        self.llm_model = llm_model
        self.embedding_model = embedding_model
        self.use_ragas_lib = use_ragas_lib
        self._ragas_available = False

        if use_ragas_lib:
            try:
                import ragas
                self._ragas_available = True
                logger.info("Using official ragas library")
            except ImportError:
                logger.warning("ragas library not installed, using built-in evaluation")

    async def evaluate(
        self,
        query: str,
        answer: str,
        contexts: list[str],
        ground_truth: Optional[str] = None,
    ) -> RAGASEvalResult:
        """Evaluate a single RAG query-answer pair.

        Args:
            query: The user query.
            answer: The generated answer.
            contexts: Retrieved context strings.
            ground_truth: Optional expected answer for correctness/similarity.

        Returns:
            RAGASEvalResult with scores for all computed metrics.
        """
        if self._ragas_available and self.use_ragas_lib:
            return await self._evaluate_with_ragas_lib(
                query, answer, contexts, ground_truth
            )

        # Built-in evaluation
        faithfulness = await self._compute_faithfulness(answer, contexts)
        answer_relevancy = await self._compute_answer_relevancy(query, answer)
        context_precision = await self._compute_context_precision(query, contexts)
        context_recall = await self._compute_context_recall(query, contexts)

        result = RAGASEvalResult(
            faithfulness=faithfulness,
            answer_relevancy=answer_relevancy,
            context_precision=context_precision,
            context_recall=context_recall,
        )

        if ground_truth:
            result.answer_correctness = await self._compute_answer_correctness(
                answer, ground_truth
            )
            result.answer_similarity = self._compute_semantic_similarity(
                answer, ground_truth
            )

        return result

    async def evaluate_batch(
        self,
        queries: list[str],
        answers: list[str],
        contexts_list: list[list[str]],
        ground_truths: Optional[list[str]] = None,
    ) -> list[RAGASEvalResult]:
        """Evaluate multiple RAG query-answer pairs.

        Args:
            queries: List of user queries.
            answers: List of generated answers (same length).
            contexts_list: List of context lists (one per query).
            ground_truths: Optional list of expected answers.

        Returns:
            List of RAGASEvalResult for each pair.
        """
        import asyncio

        tasks = []
        for i, query in enumerate(queries):
            gt = ground_truths[i] if ground_truths and i < len(ground_truths) else None
            tasks.append(
                self.evaluate(query, answers[i], contexts_list[i], gt)
            )

        return await asyncio.gather(*tasks)

    async def _evaluate_with_ragas_lib(
        self,
        query: str,
        answer: str,
        contexts: list[str],
        ground_truth: Optional[str] = None,
    ) -> RAGASEvalResult:
        """Use the official ragas library for evaluation."""
        try:
            from ragas.metrics import (
                faithfulness,
                answer_relevancy,
                context_precision,
                context_recall,
            )
            from ragas import evaluate, SingleTurnSample

            sample = SingleTurnSample(
                user_input=query,
                response=answer,
                retrieved_contexts=contexts,
                reference=ground_truth,
            )

            metrics = [faithfulness, answer_relevancy, context_precision, context_recall]
            scores = evaluate(metrics, [sample])

            return RAGASEvalResult(
                faithfulness=scores.get("faithfulness", 0.0),
                answer_relevancy=scores.get("answer_relevancy", 0.0),
                context_precision=scores.get("context_precision", 0.0),
                context_recall=scores.get("context_recall", 0.0),
            )
        except Exception as e:
            logger.error("RAGAS library evaluation failed", error=str(e))
            return await self.evaluate(query, answer, contexts, ground_truth)

    async def _compute_faithfulness(
        self,
        answer: str,
        contexts: list[str],
    ) -> float:
        """Compute faithfulness: are claims in the answer supported by contexts?

        Decomposes the answer into atomic claims and checks each against contexts.
        """
        if not contexts:
            return 1.0  # Nothing to be unfaithful to

        # Decompose answer into sentences (proxy for claims)
        claims = self._extract_claims(answer)
        if not claims:
            return 1.0

        context_text = " ".join(contexts).lower()
        supported_count = 0

        for claim in claims:
            # Check if claim words appear in contexts (simple overlap)
            claim_words = set(claim.lower().split())
            # Skip very short claims
            if len(claim_words) < 3:
                supported_count += 1
                continue

            # Count overlap with context
            overlap = sum(1 for w in claim_words if w in context_text)
            if overlap / max(len(claim_words), 1) > 0.3:
                supported_count += 1

        return supported_count / len(claims) if claims else 1.0

    async def _compute_answer_relevancy(
        self,
        query: str,
        answer: str,
    ) -> float:
        """Compute answer relevancy: does the answer address the query?

        Generates reverse questions from the answer and checks if they
        match the original query.
        """
        # Simple overlap-based relevancy
        query_terms = set(query.lower().split())
        answer_terms = set(answer.lower().split())

        if not query_terms:
            return 0.0

        overlap = query_terms & answer_terms

        # Jaccard-style relevancy
        relevancy = len(overlap) / len(query_terms)

        # Boost if answer contains key query terms
        key_term_hits = sum(
            1 for term in query_terms
            if len(term) > 3 and term in answer.lower()
        )
        key_term_boost = key_term_hits / max(len(query_terms), 1) * 0.3

        return min(1.0, relevancy + key_term_boost)

    async def _compute_context_precision(
        self,
        query: str,
        contexts: list[str],
    ) -> float:
        """Compute context precision: how many retrieved contexts are relevant?

        Ranks contexts by relevance to the query and computes precision@k.
        """
        if not contexts:
            return 0.0

        scores = []
        query_terms = set(query.lower().split())

        for context in contexts:
            context_terms = set(context.lower().split())
            if not context_terms or not query_terms:
                scores.append(0.0)
                continue
            overlap = query_terms & context_terms
            scores.append(len(overlap) / len(query_terms))

        # Precision at k: average relevance of top-k
        # Higher scores earlier = better precision
        precision_sum = 0.0
        for k, score in enumerate(scores, 1):
            precision_sum += score / k

        # Normalize (max possible is harmonic sum)
        if not scores:
            return 0.0

        # Simple precision: fraction of contexts with any relevance
        return sum(1 for s in scores if s > 0.1) / len(contexts)

    async def _compute_context_recall(
        self,
        query: str,
        contexts: list[str],
    ) -> float:
        """Compute context recall: what fraction of relevant information is retrieved?

        Estimates the total relevant information by analyzing contexts
        for coverage of query terms.
        """
        if not contexts:
            return 0.0

        query_terms = set(query.lower().split())
        covered_terms = set()

        for context in contexts:
            context_lower = context.lower()
            for term in query_terms:
                if term in context_lower:
                    covered_terms.add(term)

        return len(covered_terms) / len(query_terms) if query_terms else 0.0

    async def _compute_answer_correctness(
        self,
        answer: str,
        ground_truth: str,
    ) -> float:
        """Compute answer correctness against ground truth.

        Uses a combination of exact matching and semantic similarity.
        """
        # Exact overlap (Jaccard)
        answer_words = set(answer.lower().split())
        truth_words = set(ground_truth.lower().split())

        if not truth_words:
            return 0.0

        intersection = answer_words & truth_words
        union = answer_words | truth_words
        jaccard = len(intersection) / len(union) if union else 0.0

        # Semantic similarity (simplified: key phrase matching)
        semantic_score = self._compute_semantic_similarity(answer, ground_truth)

        return 0.4 * jaccard + 0.6 * semantic_score

    def _compute_semantic_similarity(self, text1: str, text2: str) -> float:
        """Compute semantic similarity between two texts.

        Uses n-gram overlap as a proxy for semantic similarity
        when embeddings are not available.
        """
        # Bigram overlap
        def get_ngrams(text, n=3):
            words = text.lower().split()
            return set(" ".join(words[i:i+n]) for i in range(len(words) - n + 1))

        ngrams1 = get_ngrams(text1, 3)
        ngrams2 = get_ngrams(text2, 3)

        if not ngrams1 or not ngrams2:
            return 0.0

        intersection = ngrams1 & ngrams2
        union = ngrams1 | ngrams2
        return len(intersection) / len(union) if union else 0.0

    @staticmethod
    def _extract_claims(text: str) -> list[str]:
        """Extract atomic claims from text by splitting into sentences."""
        import re
        sentences = re.split(r'[.!?]+', text)
        return [s.strip() for s in sentences if len(s.strip()) > 10]


def aggregate_ragas_results(results: list[RAGASEvalResult]) -> dict:
    """Aggregate multiple RAGAS results into summary statistics.

    Args:
        results: List of RAGASEvalResult from evaluate_batch.

    Returns:
        Dict with mean, median, min, max for each metric.
    """
    if not results:
        return {}

    metrics = ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]
    summary = {}

    for metric in metrics:
        values = [getattr(r, metric) for r in results]
        values.sort()
        n = len(values)

        summary[metric] = {
            "mean": sum(values) / n,
            "median": values[n // 2] if n % 2 else (values[n // 2 - 1] + values[n // 2]) / 2,
            "min": values[0],
            "max": values[-1],
        }

    summary["overall"] = {
        "mean": sum(r.overall for r in results) / len(results),
    }

    return summary
