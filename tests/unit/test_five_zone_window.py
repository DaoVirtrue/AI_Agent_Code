"""Unit tests for the FiveZoneWindow context management (real interface).

FiveZoneWindow is a *context window manager*, not a rate limiter. It
organizes content into five priority zones and evicts/compresses the
lowest-priority zones on overflow.
"""

import pytest

from src.context_management.five_zone_window import FiveZoneWindow
from src.token_management.counter import TokenCounter


@pytest.fixture
def counter() -> TokenCounter:
    return TokenCounter()


@pytest.fixture
def window(counter) -> FiveZoneWindow:
    return FiveZoneWindow(context_window=1000, model="gpt-4o", token_counter=counter)


class TestFiveZoneWindow:
    """Tests for zone management and context building."""

    def test_add_to_zone(self, window):
        key = window.add_to_zone("pinned", {"role": "system", "content": "Rules"})
        assert isinstance(key, str)
        assert window.get_zone_tokens("pinned") > 0

    def test_invalid_zone_raises(self, window):
        with pytest.raises(ValueError):
            window.add_to_zone("nonexistent_zone", "content")

    def test_build_context_orders_by_priority(self, window):
        window.add_to_zone("archive", {"role": "user", "content": "old"})
        window.add_to_zone("pinned", {"role": "system", "content": "system prompt"})
        context = window.build_context()
        # pinned (priority 99) should come before archive (priority 10)
        assert context[0]["content"] == "system prompt"

    def test_remove_from_zone(self, window):
        key = window.add_to_zone("working", {"role": "user", "content": "hi"})
        assert window.remove_from_zone("working", key) is True
        assert window.remove_from_zone("working", "nonexistent") is False

    def test_get_fill_percentage(self, window):
        window.add_to_zone("working", {"role": "user", "content": "some content"})
        pct = window.get_fill_percentage()
        assert pct > 0.0

    def test_clear_zone(self, window):
        window.add_to_zone("reference", {"role": "system", "content": "doc"})
        assert window.get_zone_tokens("reference") > 0
        window.clear_zone("reference")
        assert window.get_zone_tokens("reference") == 0

    def test_report_structure(self, window):
        window.add_to_zone("working", {"role": "user", "content": "hello"})
        report = window.report()
        assert "context_window" in report
        assert "zones" in report
        assert "pinned" in report["zones"]
        assert "fill_pct" in report


class TestFiveZoneWindowOverflow:
    """Tests that low-priority zones get evicted on overflow."""

    def test_overflow_truncates_low_priority(self, counter):
        # Tiny window to force overflow
        w = FiveZoneWindow(context_window=50, model="gpt-4o", token_counter=counter)
        # Pinned content stays; archive content should be evicted first
        w.add_to_zone("pinned", {"role": "system", "content": "system rules here"})
        w.add_to_zone("archive", {"role": "user", "content": "a" * 1000})
        # The pinned zone should still be present after overflow handling
        assert w.get_zone_tokens("pinned") > 0
        report = w.report()
        assert "is_overflow" in report
