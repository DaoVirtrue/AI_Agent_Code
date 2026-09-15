"""Unit tests for conversation memory + context compression.

Validates the key requirement: after context compression, key facts must
SURVIVE (as a summary) rather than be dropped.
"""

import pytest

from src.services.conversation_memory import ConversationMemory, ConversationMemoryState


class _FakeLLM:
    """Deterministic LLM stub for summarization."""

    async def ainvoke(self, messages):
        content = messages[-1]["content"] if messages else ""
        if "压缩成简洁的摘要" in content:
            # Return a fixed summary that includes the key fact marker
            return _Msg("[摘要] 用户名字是张三，喜欢喝咖啡，讨论过RAG系统。")
        return _Msg("好的，我记住了。")


class _Msg:
    def __init__(self, content):
        self.content = content


class TestConversationMemory:
    """Tests for conversation memory."""

    def test_add_message_stores_in_stm(self):
        mem = ConversationMemory(max_stm_messages=6)
        mem.add_message("c1", "user", "你好")
        state = mem.get_state("c1")
        assert len(state.stm_messages) == 1
        assert state.stm_messages[0]["content"] == "你好"

    def test_get_or_create_same_conversation(self):
        mem = ConversationMemory()
        mem.add_message("c1", "user", "第一句")
        mem.add_message("c1", "assistant", "回复")
        state = mem.get_state("c1")
        assert len(state.stm_messages) == 2

    @pytest.mark.asyncio
    async def test_compression_preserves_key_facts(self):
        """Key facts must survive compression (as summary), not be dropped."""
        mem = ConversationMemory(max_stm_tokens=100, max_stm_messages=4, llm=_FakeLLM())
        # Add more messages than max_stm_messages to trigger compression
        for i in range(10):
            mem.add_message("c1", "user", f"消息{i}")
            mem.add_message("c1", "assistant", f"回复{i}")

        # build_context triggers compression
        await mem.build_context("c1")

        state = mem.get_state("c1")
        # After compression, a summary should exist
        assert state.compressed is True
        assert len(state.summary) > 0
        # The summary should contain the key facts (from the fake LLM)
        assert "张三" in state.summary
        # STM should be truncated to recent messages (not the full 20)
        assert len(state.stm_messages) <= 8  # ~max_stm_messages worth

    @pytest.mark.asyncio
    async def test_build_context_includes_summary(self):
        mem = ConversationMemory(max_stm_tokens=50, max_stm_messages=2, llm=_FakeLLM())
        for i in range(8):
            mem.add_message("c1", "user", f"问题{i}")
            mem.add_message("c1", "assistant", f"答案{i}")

        context = await mem.build_context("c1")
        # Context should have a system summary at the front
        assert context[0]["role"] == "system"
        assert "张三" in context[0]["content"]

    def test_clear(self):
        mem = ConversationMemory()
        mem.add_message("c1", "user", "hi")
        mem.clear("c1")
        state = mem.get_state("c1")
        assert len(state.stm_messages) == 0

    @pytest.mark.asyncio
    async def test_deterministic_fallback_without_llm(self):
        """Without LLM, compression still produces a summary (truncated text)."""
        mem = ConversationMemory(max_stm_tokens=50, max_stm_messages=2, llm=None)
        for i in range(6):
            mem.add_message("c1", "user", f"用户说了重要的事情{i}")
            mem.add_message("c1", "assistant", f"助手回答了{i}")

        # build_context triggers compression
        await mem.build_context("c1")

        state = mem.get_state("c1")
        assert state.compressed is True
        assert len(state.summary) > 0
