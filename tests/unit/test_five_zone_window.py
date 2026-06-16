"""Unit tests for the Five-Zone Sliding Window rate limiter."""

import time
import pytest
from unittest.mock import MagicMock, AsyncMock


class TestFiveZoneWindow:
    """Tests for the FiveZoneWindow rate limiting algorithm."""

    @pytest.fixture
    def window(self):
        """Create a five-zone window for testing."""
        from src.gateway.five_zone_window import FiveZoneWindow

        return FiveZoneWindow(
            window_size_seconds=60,
            zones=5,
            max_requests=100,
        )

    def test_initial_counts_are_zero(self, window):
        """Test that a new window starts with all zero counts."""
        counts = window.get_zone_counts()
        assert len(counts) == 5
        assert sum(counts) == 0

    def test_record_request_increments_current_zone(self, window):
        """Test that recording a request increments the current zone."""
        window.record_request()
        counts = window.get_zone_counts()
        assert sum(counts) == 1

        window.record_request()
        window.record_request()
        assert sum(window.get_zone_counts()) == 3

    def test_is_allowed_under_limit(self, window):
        """Test that requests under the limit are allowed."""
        result = window.is_allowed(50)
        assert result is True

        window.record_request()
        assert window.is_allowed(100) is True

    def test_is_allowed_over_limit(self, window):
        """Test that requests over the limit are blocked."""
        # Fill up the window
        for _ in range(100):
            window.record_request()

        result = window.is_allowed(100)
        assert result is False

    def test_zone_rotation_clears_oldest(self, window):
        """Test that zone rotation clears the oldest zone."""
        # Fill zone 1
        window._current_zone = 0
        for _ in range(10):
            window.record_request()

        # Rotate to zone 2
        window._current_zone = 1
        for _ in range(5):
            window.record_request()

        # Simulate rotation past window size (zone 1 should be cleared)
        window._advance_zone(5)  # Advance 5 zones
        counts = window.get_zone_counts()
        # Old zone 1 should be cleared
        assert counts[0] == 0

    def test_get_retry_after_seconds(self, window):
        """Test that retry_after returns a reasonable time."""
        # Fill the window
        for _ in range(100):
            window.record_request()

        window.is_allowed(100)  # Triggers rate limit

        retry_after = window.get_retry_after()
        assert retry_after > 0
        assert retry_after <= 60  # Should not exceed window size

    def test_multiple_requests_in_same_zone(self, window):
        """Test handling many requests in the same time zone."""
        window._current_zone = 2
        for i in range(50):
            assert window.is_allowed(100) is True
            window.record_request()
        assert window._zone_counts[2] == 50

    def test_window_size_determines_accuracy(self, window):
        """Test window configuration affects behavior."""
        small_window = type(window)(
            window_size_seconds=10,
            zones=5,
            max_requests=10,
        )
        # Fill it up
        for _ in range(10):
            small_window.record_request()
        assert small_window.is_allowed(10) is False


class TestTokenBucketRateLimiter:
    """Tests for Token Bucket rate limiter implementation."""

    @pytest.fixture
    def limiter(self):
        """Create a token bucket rate limiter."""
        from src.gateway.five_zone_window import TokenBucketRateLimiter

        return TokenBucketRateLimiter(
            rate=10,  # 10 tokens per second
            capacity=20,
        )

    def test_initial_tokens_at_capacity(self, limiter):
        """Test that the bucket starts full."""
        assert limiter.current_tokens == limiter.capacity

    def test_consume_tokens(self, limiter):
        """Test consuming tokens from the bucket."""
        assert limiter.consume(5) is True
        assert limiter.current_tokens == 15

    def test_consume_more_than_available(self, limiter):
        """Test that consuming more tokens than available fails."""
        # Consume all
        limiter.current_tokens = 3
        assert limiter.consume(5) is False
        assert limiter.current_tokens == 3

    def test_token_refill(self, limiter):
        """Test that tokens refill over time."""
        limiter.current_tokens = 0
        time.sleep(0.2)  # Wait for 2 tokens worth
        limiter.consume(1)
        assert limiter.current_tokens >= 0

    def test_capacity_cap(self, limiter):
        """Test that tokens don't exceed capacity."""
        limiter.current_tokens = limiter.capacity
        time.sleep(0.3)
        limiter.consume(0)  # Triggers refill check
        assert limiter.current_tokens <= limiter.capacity
