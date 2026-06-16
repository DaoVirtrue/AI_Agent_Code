"""Unit tests for the token counter module."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestTokenCounter:
    """Tests for the TokenCounter class."""

    @pytest.fixture
    def counter(self):
        """Create a token counter instance for testing."""
        from src.gateway.token_counter import TokenCounter
        return TokenCounter()

    @pytest.mark.asyncio
    async def test_count_tokens_simple_text(self, counter):
        """Test counting tokens in simple text."""
        count = await counter.count_tokens(model="gpt-4o", text="Hello world")
        assert count > 0
        assert isinstance(count, int)

    @pytest.mark.asyncio
    async def test_count_tokens_empty_text(self, counter):
        """Test counting tokens in empty text returns 0."""
        count = await counter.count_tokens(model="gpt-4o", text="")
        assert count == 0

    @pytest.mark.asyncio
    async def test_count_tokens_messages_list(self, counter):
        """Test counting tokens in a list of messages."""
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "What is AI?"},
        ]
        count = await counter.count_tokens(model="gpt-4o", messages=messages)
        assert count > 0
        assert isinstance(count, int)

    @pytest.mark.asyncio
    async def test_count_tokens_with_tools(self, counter):
        """Test counting tokens with tool definitions included."""
        messages = [{"role": "user", "content": "Search for cats"}]
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "search",
                    "description": "Search the web",
                    "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
                },
            }
        ]
        count = await counter.count_tokens(
            model="gpt-4o",
            messages=messages,
            tools=tools,
        )
        assert count > 0

    @pytest.mark.asyncio
    async def test_count_tokens_different_models(self, counter):
        """Test that different models produce valid token counts."""
        text = "Hello, this is a test message for token counting."
        for model in ["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo", "claude-3-opus"]:
            count = await counter.count_tokens(model=model, text=text)
            assert count > 0, f"Model {model} returned {count}"
            assert isinstance(count, int)

    @pytest.mark.asyncio
    async def test_count_tokens_unicode_text(self, counter):
        """Test counting tokens in Unicode/multilingual text."""
        text = "Hello world 你好世界 こんにちは мир"
        count = await counter.count_tokens(model="gpt-4o", text=text)
        assert count > 0

    @pytest.mark.asyncio
    async def test_count_tokens_long_text(self, counter):
        """Test counting tokens in very long text."""
        text = "Test " * 10000
        count = await counter.count_tokens(model="gpt-4o", text=text)
        assert count > 0
        assert count >= 5000  # Should be at least half the words

    @pytest.mark.asyncio
    async def test_count_tokens_none_model_fallback(self, counter):
        """Test that None model falls back to default counting."""
        count = await counter.count_tokens(model=None, text="Hello")
        assert count > 0


class TestTokenCounterEdgeCases:
    """Edge case tests for token counter."""

    @pytest.fixture
    def counter(self):
        from src.gateway.token_counter import TokenCounter
        return TokenCounter()

    @pytest.mark.asyncio
    async def test_count_with_special_characters(self, counter):
        """Test counting tokens with special characters and markdown."""
        text = "```python\nprint('hello')\n```\n\n**bold** and *italic*"
        count = await counter.count_tokens(model="gpt-4o", text=text)
        assert count > 0

    @pytest.mark.asyncio
    async def test_load_tokenizers(self, counter):
        """Test that tokenizers can be loaded without errors."""
        await counter.load_tokenizers()
        # Should not raise any exception

    @pytest.mark.asyncio
    async def test_cache_behavior(self, counter):
        """Test that repeated calls for same text return consistent results."""
        text = "Consistency test text."
        count1 = await counter.count_tokens(model="gpt-4o", text=text)
        count2 = await counter.count_tokens(model="gpt-4o", text=text)
        assert count1 == count2
