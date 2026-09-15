"""Unit tests for the circuit breaker - state transitions (async interface)."""

import asyncio

import pytest

from src.ai_gateway.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerManager,
    CircuitConfig,
    CircuitState,
)


def make_config(**overrides) -> CircuitConfig:
    """Build a CircuitConfig with fast timeouts for testing."""
    defaults = dict(
        failure_threshold=3,
        failure_window=60.0,
        timeout=0.05,  # 50ms -> fast OPEN -> HALF_OPEN transition
        half_open_max_requests=2,
        success_threshold=2,
    )
    defaults.update(overrides)
    return CircuitConfig(**defaults)


@pytest.fixture
def breaker() -> CircuitBreaker:
    return CircuitBreaker(name="test-breaker", config=make_config())


class TestCircuitBreakerStates:
    """Test state transitions: CLOSED -> OPEN -> HALF_OPEN -> CLOSED."""

    @pytest.mark.asyncio
    async def test_initial_state_is_closed(self, breaker):
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0
        assert await breaker.before_call() is True

    @pytest.mark.asyncio
    async def test_closed_to_open_transition(self, breaker):
        for _ in range(3):
            await breaker.on_failure()
        assert breaker.state == CircuitState.OPEN
        assert await breaker.before_call() is False

    @pytest.mark.asyncio
    async def test_open_state_rejects_requests(self, breaker):
        for _ in range(5):
            await breaker.on_failure()
        assert breaker.state == CircuitState.OPEN
        for _ in range(10):
            assert await breaker.before_call() is False

    async def _trip_to_open(self, breaker: CircuitBreaker):
        """Trip the breaker OPEN and wait out its short timeout."""
        for _ in range(3):
            await breaker.on_failure()
        assert breaker.state == CircuitState.OPEN
        # Wait until the OPEN timeout expires (50ms) with margin.
        await asyncio.sleep(0.1)

    @pytest.mark.asyncio
    async def test_open_to_half_open_after_timeout(self, breaker):
        await self._trip_to_open(breaker)
        assert await breaker.before_call() is True
        assert breaker.state == CircuitState.HALF_OPEN

    @pytest.mark.asyncio
    async def test_half_open_success_closes(self, breaker):
        await self._trip_to_open(breaker)
        await breaker.before_call()  # -> HALF_OPEN
        assert breaker.state == CircuitState.HALF_OPEN

        await breaker.on_success()
        await breaker.on_success()  # success_threshold = 2
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0

    @pytest.mark.asyncio
    async def test_half_open_failure_reopens(self, breaker):
        await self._trip_to_open(breaker)
        await breaker.before_call()  # -> HALF_OPEN
        await breaker.on_failure()  # -> OPEN
        assert breaker.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_get_status(self, breaker):
        for _ in range(3):
            await breaker.on_failure()
        status = breaker.get_status()
        assert status["name"] == "test-breaker"
        assert status["state"] == "open"
        assert status["failure_count"] == 3


class TestCircuitBreakerManager:
    """Tests for the CircuitBreakerManager (multi-provider)."""

    @pytest.fixture
    def manager(self) -> CircuitBreakerManager:
        return CircuitBreakerManager(default_config=make_config())

    @pytest.mark.asyncio
    async def test_get_or_create_same_instance(self, manager):
        b1 = await manager.get_or_create("openai")
        b2 = await manager.get_or_create("openai")
        assert b1 is b2

    @pytest.mark.asyncio
    async def test_manager_on_failure_opens_breaker(self, manager):
        for _ in range(3):
            await manager.on_failure("anthropic")
        assert await manager.before_call("anthropic") is False

    @pytest.mark.asyncio
    async def test_health_report(self, manager):
        await manager.on_failure("openai")
        report = await manager.health_report()
        assert len(report) == 1
        assert report[0]["name"] == "openai"

    @pytest.mark.asyncio
    async def test_reset_all(self, manager):
        for _ in range(3):
            await manager.on_failure("openai")
        assert await manager.before_call("openai") is False
        await manager.reset_all()
        assert await manager.before_call("openai") is True
