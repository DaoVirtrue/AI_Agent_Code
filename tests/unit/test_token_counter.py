"""Unit tests for the unified TokenCounter (sync interface)."""

import pytest

from src.token_management.counter import TokenCounter


@pytest.fixture
def counter() -> TokenCounter:
    return TokenCounter()


class TestTokenCounter:
    """Tests for the sync TokenCounter.count()/count_messages() interface."""

    def test_count_simple_text(self, counter):
        count = counter.count("Hello world", "gpt-4o")
        assert count > 0
        assert isinstance(count, int)

    def test_count_empty_text_returns_zero(self, counter):
        assert counter.count("", "gpt-4o") == 0

    def test_count_messages_list(self, counter):
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "What is AI?"},
        ]
        count = counter.count_messages(messages, "gpt-4o")
        assert count > 0
        assert isinstance(count, int)

    def test_count_different_openai_models(self, counter):
        text = "Hello, this is a test message for token counting."
        for model in ["gpt-4o", "gpt-4o-mini", "gpt-4", "gpt-3.5-turbo"]:
            count = counter.count(text, model)
            assert count > 0, f"Model {model} returned {count}"

    def test_count_unicode_text(self, counter):
        text = "Hello world 你好世界 こんにちは мир"
        count = counter.count(text, "gpt-4o")
        assert count > 0

    def test_count_long_text(self, counter):
        text = "Test " * 10000
        count = counter.count(text, "gpt-4o")
        assert count > 0
        assert count >= 5000  # ~half the words

    def test_count_unknown_model_falls_back(self, counter):
        # Unknown model should fall back through encoders to heuristic
        count = counter.count("Hello", "unknown-model-xyz")
        assert count > 0

    def test_count_special_characters(self, counter):
        text = "```python\nprint('hello')\n```\n\n**bold** and *italic*"
        count = counter.count(text, "gpt-4o")
        assert count > 0

    def test_count_consistent_results(self, counter):
        text = "Consistency test text."
        assert counter.count(text, "gpt-4o") == counter.count(text, "gpt-4o")


class TestTokenCounterCJK:
    """Edge cases for CJK / heuristic estimation."""

    @pytest.fixture
    def counter(self) -> TokenCounter:
        return TokenCounter()

    def test_cjk_estimation(self, counter):
        # Unknown model triggers heuristic estimation (CJK-aware)
        count = counter.count("人工智能改变世界", "unknown-model")
        assert count > 0

    def test_empty_messages_returns_zero(self, counter):
        assert counter.count_messages([], "gpt-4o") == 0

    def test_multimodal_content(self, counter):
        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": "Describe this image"},
                {"type": "image_url", "image_url": {"url": "http://x/y.png"}},
            ],
        }]
        count = counter.count_messages(messages, "gpt-4o")
        assert count > 0
