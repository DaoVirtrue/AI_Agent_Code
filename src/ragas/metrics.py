"""RAGAS metrics facade — 五指标统一入口.

Wraps ``src/evaluation/ragas_wrapper.RAGASWrapper`` behind a single high-level
``evaluate`` call that returns a plain dict (ready for API serialization). The
five RAGAS metrics are:

- faithfulness（忠实度）
- answer_relevancy（答案相关性）
- context_precision（上下文精确率）
- context_recall（上下文召回率）
- answer_correctness（答案正确性，需 ground truth）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class RAGASReport:
    """Aggregated RAGAS scores across a batch."""

    faithfulness: float = 0.0
    answer_relevancy: float = 0.0
    context_precision: float = 0.0
    context_recall: float = 0.0
    answer_correctness: Optional[float] = None
    overall: float = 0.0
    per_query: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        out = {
            "faithfulness": round(self.faithfulness, 4),
            "answer_relevancy": round(self.answer_relevancy, 4),
            "context_precision": round(self.context_precision, 4),
            "context_recall": round(self.context_recall, 4),
            "overall": round(self.overall, 4),
        }
        if self.answer_correctness is not None:
            out["answer_correctness"] = round(self.answer_correctness, 4)
        out["per_query"] = self.per_query
        return out


class RAGASEvaluator:
    """High-level RAGAS evaluator.

    Args:
        llm_model: Model for LLM-as-judge (unused in heuristic mode).
        use_ragas_lib: If True and ragas is installed, use the official lib.
    """

    def __init__(self, llm_model: str = "deepseek-chat", use_ragas_lib: bool = False):
        from src.evaluation.ragas_wrapper import RAGASWrapper

        self.llm_model = llm_model
        self.wrapper = RAGASWrapper(llm_model=llm_model, use_ragas_lib=use_ragas_lib)

    async def evaluate(
        self,
        queries: list[str],
        answers: list[str],
        contexts_list: list[list[str]],
        ground_truths: Optional[list[str]] = None,
    ) -> RAGASReport:
        """Evaluate a batch and return an aggregated report."""
        results = await self.wrapper.evaluate_batch(
            queries=queries,
            answers=answers,
            contexts_list=contexts_list,
            ground_truths=ground_truths,
        )

        n = len(results) or 1
        report = RAGASReport(
            faithfulness=sum(r.faithfulness for r in results) / n,
            answer_relevancy=sum(r.answer_relevancy for r in results) / n,
            context_precision=sum(r.context_precision for r in results) / n,
            context_recall=sum(r.context_recall for r in results) / n,
            overall=sum(r.overall for r in results) / n,
        )

        has_correctness = any(r.answer_correctness is not None for r in results)
        if has_correctness:
            report.answer_correctness = sum(
                r.answer_correctness for r in results if r.answer_correctness is not None
            ) / n

        report.per_query = [
            {
                "query": q,
                "faithfulness": r.faithfulness,
                "answer_relevancy": r.answer_relevancy,
                "context_precision": r.context_precision,
                "context_recall": r.context_recall,
                "overall": r.overall,
            }
            for q, r in zip(queries, results)
        ]

        return report
