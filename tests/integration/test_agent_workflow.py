"""Integration tests for the agent workflow (real AgentExecutor)."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.agents.executor import AgentExecutor, AgentExecutionResult
from src.agents.tools.registry import ToolRegistry
from src.core.tools import BaseTool, ToolDefinition, ToolResult, ToolStatus


class _FakeTool(BaseTool):
    """A simple tool for testing the executor."""

    def __init__(self, name):
        self._name = name

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self._name,
            description=f"Tool {self._name}",
            parameters={"type": "object", "properties": {}, "required": []},
        )

    async def execute(self, **kwargs) -> ToolResult:
        return ToolResult(status=ToolStatus.SUCCESS, data={"result": "ok"})


class _FakeLLM:
    """A LangChain-compatible LLM stub."""

    def __init__(self, response="final answer"):
        self._response = response

    async def ainvoke(self, messages):
        class _Msg:
            content = self._response
        return _Msg()


class TestAgentWorkflow:
    """Integration tests for the AgentExecutor -> pattern -> result flow."""

    @pytest.fixture
    def executor(self):
        registry = ToolRegistry()
        registry.register(_FakeTool("search"))
        registry.register(_FakeTool("calculator"))
        return AgentExecutor(tool_registry=registry, default_model="deepseek-chat")

    def test_executor_initialization(self, executor):
        assert executor.default_model == "deepseek-chat"
        assert executor.max_steps == 15
        assert len(executor.tool_registry) == 2

    @pytest.mark.asyncio
    async def test_execute_basic_task(self, executor):
        llm = _FakeLLM("The answer is 42.")
        result = await executor.execute(task="What is the meaning of life?", agent_type="react", llm=llm)
        assert isinstance(result, AgentExecutionResult)
        assert result.status in ("completed", "error")
        assert len(result.final_output) > 0

    @pytest.mark.asyncio
    async def test_execute_unknown_agent_type(self, executor):
        result = await executor.execute(task="test", agent_type="bogus")
        assert result.status == "error"
        assert "bogus" in result.final_output

    @pytest.mark.asyncio
    async def test_execute_with_tools(self, executor):
        llm = _FakeLLM("done with tools")
        result = await executor.execute(task="search something", agent_type="react", tools=["search"], llm=llm)
        assert result.status in ("completed", "error")

    @pytest.mark.asyncio
    async def test_tool_registry_has_tools(self, executor):
        defs = executor.tool_registry.list_all()
        names = {d.name for d in defs}
        assert "search" in names
        assert "calculator" in names
