"""RAGAS evaluation framework wrapper."""

import logging
from typing import Any, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

try:
    from ragas import evaluate
    from ragas.metrics import (
        faithfulness, answer_relevancy, context_precision,
        context_recall, context_relevancy, answer_correctness,
    )
    from datasets import Dataset
    HAS_RAGAS = True
except ImportError:
    HAS_RAGAS = False
    logger.info("ragas not installed - using built-in metric approximations")


@dataclass
class RAGASEvaluationResult:
    """Container for RAGAS evaluation results."""
    faithfulness: float = 0.0
    answer_relevancy: float = 0.0
    context_precision: float = 0.0
    context_recall: float = 0.0
    context_relevancy: float = 0.0
    answer_correctness: float = 0.0
    overall_score: float = 0.0
    per_question: list[dict] = field(default_factory=list)


class RAGASWrapper:
    """Wrapper around RAGAS for evaluating RAG pipeline quality.

    RAGAS (Retrieval Augmented Generation Assessment) provides
    a suite of metrics for evaluating RAG systems:
    - Faithfulness: Is the answer faithful to the retrieved context?
    - Answer Relevancy: Is the answer relevant to the question?
    - Context Precision: Are the retrieved documents relevant?
    - Context Recall: Were all relevant documents retrieved?
    - Context Relevancy: Is the retrieved context relevant?
    - Answer Correctness: Is the answer factually correct?
    """

    def __init__(self, llm_client=None, embedding_model=None):
        """Initialize RAGAS wrapper.

        Args:
            llm_client: LLM for evaluation (required for RAGAS)
            embedding_model: Embedding model for context metrics
        """
        self.llm_client = llm_client
        self.embedding_model = embedding_model
        self._use_ragas = HAS_RAGAS and llm_client is not None
        logger.info("RAGASWrapper initialized (ragas=%s)", self._use_ragas)

    async def evaluate(
        self,
        questions: list[str],
        answers: list[str],
        contexts: list[list[str]],
        ground_truths: Optional[list[str]] = None,
    ) -> RAGASEvaluationResult:
        """Evaluate RAG pipeline on a set of question-answer pairs.

        Args:
            questions: List of questions
            answers: List of generated answers
            contexts: List of context lists (one list per question)
            ground_truths: Optional list of ground truth answers

        Returns:
            RAGASEvaluationResult with all metric scores
        """
        if not questions:
            return RAGASEvaluationResult()

        if self._use_ragas:
            return await self._ragas_evaluate(questions, answers, contexts, ground_truths)
        else:
            return self._approximate_evaluate(questions, answers, contexts, ground_truths)

    async def _ragas_evaluate(
        self,
        questions: list[str],
        answers: list[str],
        contexts: list[list[str]],
        ground_truths: Optional[list[str]],
    ) -> RAGASEvaluationResult:
        """Evaluate using actual RAGAS library."""
        import asyncio

        data = {
            "question": questions,
            "answer": answers,
            "contexts": contexts,
        }
        if ground_truths:
            data["ground_truth"] = ground_truths

        dataset = Dataset.from_dict(data)

        metrics = [
            faithfulness,
            answer_relevancy,
            context_precision,
            context_recall,
            context_relevancy,
        ]
        if ground_truths:
            metrics.append(answer_correctness)

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: evaluate(dataset, metrics=metrics)
            )

            scores = {}
            for metric_name in ["faithfulness", "answer_relevancy", "context_precision",
                               "context_recall", "context_relevancy", "answer_correctness"]:
                metric_key = f"eval_{metric_name}"
                if metric_key in result:
                    scores[metric_name] = float(result[metric_key])

            overall = sum(scores.values()) / max(len(scores), 1)

            return RAGASEvaluationResult(
                faithfulness=scores.get("faithfulness", 0.0),
                answer_relevancy=scores.get("answer_relevancy", 0.0),
                context_precision=scores.get("context_precision", 0.0),
                context_recall=scores.get("context_recall", 0.0),
                context_relevancy=scores.get("context_relevancy", 0.0),
                answer_correctness=scores.get("answer_correctness", 0.0),
                overall_score=overall,
            )

        except Exception as e:
            logger.error("RAGAS evaluation error: %s", e)
            return self._approximate_evaluate(questions, answers, contexts, ground_truths)

    def _approximate_evaluate(
        self,
        questions: list[str],
        answers: list[str],
        contexts: list[list[str]],
        ground_truths: Optional[list[str]],
    ) -> RAGASEvaluationResult:
        """Approximate RAGAS metrics without the library."""
        per_question = []
        total_faithfulness = 0.0
        total_relevancy = 0.0
        total_precision = 0.0

        for i, (question, answer, ctx) in enumerate(zip(questions, answers, contexts)):
            # Faithfulness: Check if answer content appears in context
            faith_score = self._approximate_faithfulness(answer, ctx)

            # Relevancy: Check if answer addresses the question
            rel_score = self._approximate_relevancy(question, answer)

            # Precision: Check if context is relevant to question
            prec_score = self._approximate_precision(question, ctx)

            total_faithfulness += faith_score
            total_relevancy += rel_score
            total_precision += prec_score

            per_question.append({
                "question": question,
                "faithfulness": faith_score,
                "relevancy": rel_score,
                "precision": prec_score,
            })

        n = len(questions)

        return RAGASEvaluationResult(
            faithfulness=total_faithfulness / n if n else 0,
            answer_relevancy=total_relevancy / n if n else 0,
            context_precision=total_precision / n if n else 0,
            context_recall=total_precision / n if n else 0,  # Approximation
            context_relevancy=total_precision / n if n else 0,  # Approximation
            answer_correctness=0.0,  # Can't approximate without ground truth
            overall_score=(total_faithfulness + total_relevancy + total_precision) / (3 * n) if n else 0,
            per_question=per_question,
        )

    def _approximate_faithfulness(self, answer: str, contexts: list[str]) -> float:
        """Check how much of the answer is supported by context."""
        if not contexts:
            return 0.0

        combined_context = " ".join(contexts).lower()
        answer_lower = answer.lower()

        # Count answer words that appear in context
        answer_words = set(answer_lower.split())
        context_words = set(combined_context.split())

        if not answer_words:
            return 1.0

        overlap = len(answer_words & context_words) / len(answer_words)
        return min(overlap, 1.0)

    def _approximate_relevancy(self, question: str, answer: str) -> float:
        """Check how relevant the answer is to the question."""
        q_words = set(question.lower().split())
        a_words = set(answer.lower().split())

        if not q_words:
            return 0.5

        overlap = len(q_words & a_words) / len(q_words)
        return min(overlap + 0.2, 1.0)  # Slight boost

    def _approximate_precision(self, question: str, contexts: list[str]) -> float:
        """Check how relevant each context is to the question."""
        if not contexts:
            return 0.0

        q_words = set(question.lower().split())
        scores = []

        for ctx in contexts:
            ctx_words = set(ctx.lower().split())
            if not ctx_words:
                continue
            overlap = len(q_words & ctx_words) / len(ctx_words)
            scores.append(overlap)

        return sum(scores) / len(scores) if scores else 0.0

    async def evaluate_single(
        self,
        question: str,
        answer: str,
        contexts: list[str],
        ground_truth: Optional[str] = None,
    ) -> dict:
        """Evaluate a single question-answer pair."""
        result = await self.evaluate(
            questions=[question],
            answers=[answer],
            contexts=[contexts],
            ground_truths=[ground_truth] if ground_truth else None,
        )
        return {
            "faithfulness": result.faithfulness,
            "answer_relevancy": result.answer_relevancy,
            "context_precision": result.context_precision,
            "overall_score": result.overall_score,
        }
