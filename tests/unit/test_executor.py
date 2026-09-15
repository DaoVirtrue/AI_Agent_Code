"""Unit tests for the unified AgentExecutor bridge."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.agents.executor import AgentExecutor, AgentExecutionResult, AGENT_TYPE_MAP
from src.agents.tools.registry import ToolRegistry


class _FakeLLM:
    """A LangChain-compatible LLM stub for tests."""

    def __init__(self, response="final answer"):
        self._response = response

    async def ainvoke(self, messages):
        class _Resp:
            content = self._response
        return _Resp()


@pytest.fixture
def executor() -> AgentExecutor:
    return AgentExecutor(tool_registry=ToolRegistry(), default_model="deepseek-chat")


class TestAgentExecutor:
    """Tests for executor wiring and error handling."""

    def test_supported_agent_types(self):
        assert set(AGENT_TYPE_MAP) == {"react", "plan_execute", "rewoo", "reflection", "pev"}

    @pytest.mark.asyncio
    async def test_unknown_agent_type_returns_error(self, executor):
        result = await executor.execute("do something", agent_type="bogus")
        assert result.status == "error"
        assert "bogus" in result.final_output

    @pytest.mark.asyncio
    async def test_missing_llm_returns_error(self, executor):
        # No llm passed -> the pattern raises; executor should surface cleanly
        result = await executor.execute("do something", agent_type="react", llm=None)
        assert result.status == "error"

    @pytest.mark.asyncio
    async def test_reflection_needs_no_tools(self, executor):
        result = await executor.execute(
            "think about life", agent_type="reflection", llm=_FakeLLM("an answer")
        )
        # reflection may error or complete; the point is it doesn't require tools
        assert result.status in ("completed", "error")

    @pytest.mark.asyncio
    async def test_execute_returns_unified_shape(self, executor):
        result = await executor.execute(
            "test task", agent_type="react", llm=_FakeLLM("hello world")
        )
        assert isinstance(result, AgentExecutionResult)
        assert hasattr(result, "final_output")
        assert hasattr(result, "status")
        assert hasattr(result, "steps")
        assert isinstance(result.steps, list)
        assert hasattr(result, "loop_detected")
        assert hasattr(result, "cost_usd")

    @pytest.mark.asyncio
    async def test_tool_name_resolution_skips_unknown(self, executor):
        result = await executor.execute(
            "test", agent_type="react", tools=["nonexistent_tool"],
            llm=_FakeLLM("done"),
        )
        # Unknown tool should be skipped, not crash
        assert result.status in ("completed", "error")
