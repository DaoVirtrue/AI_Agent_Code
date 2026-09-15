"""Unit tests for the resilience layer (timeout / retry budget / recovery / reclaimer)."""

import time

import pytest

from src.resilience.timeout import TimeoutPolicy, build_default_policy
from src.resilience.retry_budget import RetryBudget, RetryBudgetConfig, exponential_backoff
from src.resilience.recovery import (
    RecoveryManager,
    check_context_present,
    check_idempotency_complete,
    check_cost_not_negative,
)
from src.resilience.reclaimer import ResourceReclaimer


class TestTimeoutPolicy:
    """Tests for the layered timeout table."""

    def test_default_hierarchy_valid(self):
        policy = build_default_policy()
        assert policy.validate_hierarchy() == []

    def test_get_layer(self):
        policy = build_default_policy()
        assert policy.get("mcp_connect") == 0.5
        assert policy.get("task") == 900.0

    def test_get_unknown_layer_raises(self):
        policy = build_default_policy()
        with pytest.raises(KeyError):
            policy.get("nonexistent")

    def test_hierarchy_violation_detected(self):
        policy = TimeoutPolicy()
        # Invert inner/outer to force a violation
        policy.timeouts["mcp_connect"] = 100.0
        violations = policy.validate_hierarchy()
        assert any("mcp_connect" in v for v in violations)

    def test_remaining(self):
        policy = build_default_policy()
        assert policy.remaining("mcp_read", 1.0) == 2.0
        assert policy.remaining("mcp_read", 5.0) == 0.0


class TestRetryBudget:
    """Tests for retry budget + storm detection."""

    def test_allow_retry_under_budget(self):
        b = RetryBudget(RetryBudgetConfig(window_seconds=60, max_retry_rate=0.5))
        assert b.allow_retry() is True

    def test_retry_rate_tracks(self):
        b = RetryBudget(RetryBudgetConfig(window_seconds=60, max_retry_rate=0.3))
        for _ in range(10):
            b.record_request(is_retry=False)
        for _ in range(10):
            b.record_request(is_retry=True)
        assert b.retry_rate == pytest.approx(0.5, abs=0.01)

    def test_storm_detection(self):
        b = RetryBudget(RetryBudgetConfig(window_seconds=60, storm_threshold=0.5))
        for _ in range(5):
            b.record_request(is_retry=True)
        assert b.is_storm() is True

    def test_no_storm_when_healthy(self):
        b = RetryBudget(RetryBudgetConfig(window_seconds=60, storm_threshold=0.5))
        for _ in range(10):
            b.record_request(is_retry=False)
        assert b.is_storm() is False

    def test_exponential_backoff(self):
        assert exponential_backoff(0) == 0.1
        assert exponential_backoff(1) == 0.2
        assert exponential_backoff(10, cap=5.0) == 5.0


class TestRecoveryManager:
    """Tests for checkpoint recovery + consistency validation."""

    def test_validate_passes_on_good_checkpoint(self):
        mgr = RecoveryManager([check_context_present, check_cost_not_negative])
        report = mgr.validate({"state": {"step": 1}, "cost_usd": 0.5})
        assert report.ok is True

    def test_validate_fails_on_missing_context(self):
        mgr = RecoveryManager([check_context_present])
        report = mgr.validate({"state": {}})
        assert report.ok is False

    def test_validate_fails_on_negative_cost(self):
        mgr = RecoveryManager([check_cost_not_negative])
        report = mgr.validate({"cost_usd": -1.0})
        assert report.ok is False

    def test_idempotency_check(self):
        mgr = RecoveryManager([check_idempotency_complete])
        bad = mgr.validate({"tool_calls": [{"name": "search"}]})
        assert bad.ok is False
        good = mgr.validate({"tool_calls": [{"name": "search", "idempotency_key": "k1"}]})
        assert good.ok is True

    @pytest.mark.asyncio
    async def test_recover_resumes_on_consistent(self):
        calls = []
        async def resume(cp):
            calls.append(cp["checkpoint_id"])

        mgr = RecoveryManager([check_context_present])
        result = await mgr.recover({"checkpoint_id": "ckpt-1", "state": {"step": 3}}, resume)
        assert result.recovered is True
        assert calls == ["ckpt-1"]

    @pytest.mark.asyncio
    async def test_recover_declines_on_inconsistent(self):
        mgr = RecoveryManager([check_context_present])
        result = await mgr.recover({"checkpoint_id": "ckpt-2", "state": {}})
        assert result.recovered is False


class TestResourceReclaimer:
    """Tests for TTL-based resource reclamation."""

    @pytest.mark.asyncio
    async def test_reclaim_expired(self):
        reclaimer = ResourceReclaimer()
        reclaimer.register("r1", kind="sandbox", ttl_seconds=0.0)  # already expired
        reclaimer.register("r2", kind="lock", ttl_seconds=3600.0)
        reclaimed = await reclaimer.reclaim_expired()
        assert "r1" in reclaimed
        assert "r2" not in reclaimed

    def test_unregister(self):
        reclaimer = ResourceReclaimer()
        reclaimer.register("r1", kind="lock", ttl_seconds=10)
        assert reclaimer.unregister("r1") is True
        assert reclaimer.unregister("r1") is False

    @pytest.mark.asyncio
    async def test_cleanup_called(self):
        cleaned = []
        reclaimer = ResourceReclaimer()
        reclaimer.register("r1", kind="sandbox", ttl_seconds=0.0, cleanup=lambda: cleaned.append("r1"))
        await reclaimer.reclaim_expired()
        assert cleaned == ["r1"]
