"""Unit tests for the circuit breaker module - all 3 state transitions."""

import asyncio
import time
import pytest
from unittest.mock import MagicMock


class TestCircuitBreakerStates:
    """Test circuit breaker state transitions: CLOSED -> OPEN -> HALF_OPEN -> CLOSED."""

    @pytest.fixture
    def breaker(self):
        """Create a circuit breaker for testing with short timeouts."""
        from src.gateway.circuit_breaker import CircuitBreaker

        return CircuitBreaker(
            name="test-breaker",
            failure_threshold=3,
            timeout=0.5,  # 500ms timeout for fast testing
            half_open_max_requests=2,
        )

    def test_initial_state_is_closed(self, breaker):
        """Test that circuit breaker starts in CLOSED state."""
        assert breaker.state == "CLOSED"
        assert breaker.failure_count == 0
        assert breaker.is_allowed() is True

    def test_closed_to_open_transition(self, breaker):
        """Test CLOSED -> OPEN transition when failure threshold exceeded."""
        # Record failures
        for _ in range(3):
            breaker.record_failure()

        assert breaker.failure_count == 3
        assert breaker.state == "OPEN"
        assert breaker.is_allowed() is False

    def test_open_state_rejects_requests(self, breaker):
        """Test that OPEN state rejects all requests."""
        # Trip the breaker
        for _ in range(5):
            breaker.record_failure()
        assert breaker.state == "OPEN"

        # Verify requests are rejected
        for _ in range(10):
            assert breaker.is_allowed() is False

    def test_open_to_half_open_transition(self, breaker):
        """Test OPEN -> HALF_OPEN transition after timeout expires."""
        # Trip the breaker
        for _ in range(3):
            breaker.record_failure()
        assert breaker.state == "OPEN"

        # Wait for timeout
        time.sleep(0.6)

        # Next check should transition to HALF_OPEN
        assert breaker.is_allowed() is True
        assert breaker.state == "HALF_OPEN"

    def test_half_open_success_closes_circuit(self, breaker):
        """Test HALF_OPEN -> CLOSED after successful requests."""
        # Trip and then wait for timeout
        for _ in range(3):
            breaker.record_failure()
        time.sleep(0.6)
        breaker.is_allowed()  # Transition to HALF_OPEN

        assert breaker.state == "HALF_OPEN"

        # Record successes
        breaker.record_success()
        breaker.record_success()

        assert breaker.state == "CLOSED"
        assert breaker.failure_count == 0

    def test_half_open_failure_reopens_circuit(self, breaker):
        """Test HALF_OPEN -> OPEN on failure during half-open."""
        # Trip and wait
        for _ in range(3):
            breaker.record_failure()
        time.sleep(0.6)
        breaker.is_allowed()  # HALF_OPEN

        # Failure in HALF_OPEN should go back to OPEN
        breaker.record_failure()
        assert breaker.state == "OPEN"

    def test_success_resets_failure_count_in_closed(self, breaker):
        """Test that successes reset the failure count in CLOSED state."""
        breaker.record_failure()
        breaker.record_failure()  # 2 failures

        breaker.record_success()
        assert breaker.failure_count == 0

    def test_multiple_cycles(self, breaker):
        """Test full CLOSED -> OPEN -> HALF_OPEN -> CLOSED cycle multiple times."""
        for cycle in range(3):
            # CLOSED -> OPEN
            for _ in range(3):
                breaker.record_failure()
            assert breaker.state == "OPEN", f"Cycle {cycle}: should be OPEN"

            # Wait and transition to HALF_OPEN
            time.sleep(0.6)
            assert breaker.is_allowed()
            assert breaker.state == "HALF_OPEN", f"Cycle {cycle}: should be HALF_OPEN"

            # HALF_OPEN -> CLOSED
            breaker.record_success()
            breaker.record_success()
            assert breaker.state == "CLOSED", f"Cycle {cycle}: should be CLOSED"


class TestCircuitBreakerRegistry:
    """Tests for the CircuitBreakerRegistry."""

    @pytest.fixture
    def registry(self):
        from src.gateway.circuit_breaker import CircuitBreakerRegistry
        return CircuitBreakerRegistry()

    def test_register_breaker(self, registry):
        """Test registering a new circuit breaker."""
        breaker = registry.get_or_create("openai-gpt-4o")
        assert breaker.name == "openai-gpt-4o"
        assert breaker.state == "CLOSED"

    def test_get_same_breaker_twice(self, registry):
        """Test that get_or_create returns the same instance."""
        b1 = registry.get_or_create("test")
        b2 = registry.get_or_create("test")
        assert b1 is b2

    def test_get_all_breakers(self, registry):
        """Test listing all registered breakers."""
        registry.get_or_create("a")
        registry.get_or_create("b")
        registry.get_or_create("c")
        all_breakers = registry.get_all()
        assert len(all_breakers) == 3

    def test_reset_all(self, registry):
        """Test resetting all circuit breakers."""
        b = registry.get_or_create("test")
        for _ in range(3):
            b.record_failure()
        assert b.state == "OPEN"

        registry.reset_all()
        assert b.state == "CLOSED"

    def test_register_with_custom_params(self, registry):
        """Test registering a breaker with custom parameters."""
        breaker = registry.get_or_create(
            "custom",
            failure_threshold=5,
            timeout=60,
        )
        assert breaker.failure_threshold == 5
        assert breaker.timeout == 60
