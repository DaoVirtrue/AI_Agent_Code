"""Unit tests for the RAGAS metrics facade."""

import pytest

from src.ragas.metrics import RAGASEvaluator, RAGASReport
from src.ragas.report import EvalRunStore


class TestRAGASEvaluator:
    """Tests for the RAGAS evaluation facade."""

    @pytest.mark.asyncio
    async def test_evaluate_batch_returns_report(self):
        evaluator = RAGASEvaluator()
        report = await evaluator.evaluate(
            queries=["What is AI?"],
            answers=["AI is artificial intelligence."],
            contexts_list=[["AI refers to machines that can learn."]],
        )
        assert isinstance(report, RAGASReport)
        assert 0.0 <= report.faithfulness <= 1.0
        assert report.overall >= 0.0

    @pytest.mark.asyncio
    async def test_evaluate_with_ground_truth(self):
        evaluator = RAGASEvaluator()
        report = await evaluator.evaluate(
            queries=["What is the capital?"],
            answers=["Paris"],
            contexts_list=[["Paris is the capital of France."]],
            ground_truths=["Paris"],
        )
        assert report.answer_correctness is not None

    @pytest.mark.asyncio
    async def test_report_to_dict(self):
        evaluator = RAGASEvaluator()
        report = await evaluator.evaluate(
            queries=["q"],
            answers=["a"],
            contexts_list=[["c"]],
        )
        d = report.to_dict()
        assert "faithfulness" in d
        assert "overall" in d
        assert "per_query" in d


class TestEvalRunStore:
    """Tests for the evaluation run store."""

    def test_save_and_list(self):
        store = EvalRunStore()
        store.save({"overall": 0.85})
        store.save({"overall": 0.90})
        runs = store.list_runs()
        assert len(runs) == 2

    def test_get_run(self):
        store = EvalRunStore()
        run = store.save({"overall": 0.7})
        fetched = store.get_run(run.run_id)
        assert fetched is not None
        assert fetched["scores"]["overall"] == 0.7

    def test_trend(self):
        store = EvalRunStore()
        store.save({"overall": 0.8})
        store.save({"overall": 0.9})
        trend = store.trend(metric="overall")
        assert len(trend) == 2
        assert trend[0]["overall"] == 0.8
        assert trend[1]["overall"] == 0.9
