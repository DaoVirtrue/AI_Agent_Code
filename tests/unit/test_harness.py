"""Unit tests for the Harness layer (guard / verify / transaction / checkpoint)."""

import pytest

from src.harness.guard import Harness, HarnessConfig, HarnessViolation
from src.harness.verify import (
    SchemaVerifier,
    ContainsVerifier,
    CompositeVerifier,
    VerificationResult,
)
from src.harness.transaction import TransactionManager
from src.harness.checkpoint import CheckpointStore, Snapshot


class TestHarnessGuard:
    """Tests for the Harness guardrails."""

    def test_max_steps_enforced(self):
        h = Harness(HarnessConfig(max_steps=5))
        assert h.check_step(3).passed is True
        assert h.check_step(6).passed is False

    def test_cost_budget_exceeded(self):
        h = Harness(HarnessConfig(max_cost_usd=0.5))
        h.track_cost(0.3)
        with pytest.raises(HarnessViolation):
            h.track_cost(0.3)  # 0.6 > 0.5

    def test_token_budget_exceeded(self):
        h = Harness(HarnessConfig(max_tokens=100))
        h.track_tokens(60, 20)  # 80
        with pytest.raises(HarnessViolation):
            h.track_tokens(30, 10)  # 120 > 100

    def test_blocked_tool(self):
        h = Harness(HarnessConfig(blocked_tools=["delete_file"]))
        assert h.check_tool("delete_file").passed is False

    def test_approval_required(self):
        h = Harness(HarnessConfig(require_approval_for=["send_email"]))
        check = h.check_tool("send_email")
        assert check.passed is False
        assert check.details.get("requires_approval") is True

    def test_output_validator(self):
        h = Harness(HarnessConfig(output_validator=lambda a: (len(a) > 10, "too short")))
        ok, _ = h.validate_output("a long enough answer")
        assert ok is True
        ok, reason = h.validate_output("short")
        assert ok is False
        assert reason == "too short"


class TestVerifier:
    """Tests for the independent verifiers (non-LLM)."""

    def test_schema_verifier(self):
        v = SchemaVerifier(["answer", "sources"])
        assert v.verify({"answer": "x", "sources": []}).passed is True
        assert v.verify({"answer": "x"}).passed is False

    def test_schema_verifier_json_string(self):
        v = SchemaVerifier(["answer"])
        assert v.verify('{"answer": "x"}').passed is True
        assert v.verify("not json").passed is False

    def test_contains_verifier(self):
        v = ContainsVerifier(["paris", "capital"])
        assert v.verify("Paris is the capital of France").passed is True
        assert v.verify("London is in England").passed is False

    def test_composite_verifier(self):
        v = CompositeVerifier([
            ContainsVerifier(["paris"]),
            ContainsVerifier(["capital"]),
        ])
        assert v.verify("Paris is the capital").passed is True
        assert v.verify("Paris is a city").passed is False


class TestTransactionManager:
    """Tests for business transaction lifecycle."""

    def test_commit(self):
        tm = TransactionManager()
        tm.prepare("search", {"query": "x"})
        result = tm.commit()
        assert result.status == "committed"
        assert result.applied == ["search"]

    @pytest.mark.asyncio
    async def test_abort_rolls_back_undoable(self):
        calls = []
        tm = TransactionManager()

        async def undo(path):
            calls.append(path)

        op = tm.prepare("write_file", {"path": "x"})
        op.undo_supported = True
        op.undo = undo

        # A non-undoable op should be skipped
        op2 = tm.prepare("send_email", {})
        op2.undo_supported = False

        result = await tm.abort()
        assert result.status == "aborted"
        assert "write_file" in result.applied
        assert "send_email" not in result.applied
        assert calls == ["x"]

    def test_idempotency_key(self):
        tm = TransactionManager(transaction_id="idem-123")
        assert tm.idempotency_key == "idem-123"


class TestCheckpointStore:
    """Tests for snapshot / checkpoint."""

    def test_save_and_latest(self):
        store = CheckpointStore()
        store.save(Snapshot(task_id="t1", step_index=0))
        store.save(Snapshot(task_id="t1", step_index=1))
        latest = store.latest("t1")
        assert latest.step_index == 1

    def test_history(self):
        store = CheckpointStore()
        store.save(Snapshot(task_id="t1", step_index=0))
        store.save(Snapshot(task_id="t1", step_index=1))
        history = store.history("t1")
        assert len(history) == 2

    def test_clear(self):
        store = CheckpointStore()
        store.save(Snapshot(task_id="t1", step_index=0))
        store.clear("t1")
        assert store.latest("t1") is None
