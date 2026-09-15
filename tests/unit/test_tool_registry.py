"""Unit tests for the ToolRegistry (real BaseTool-based interface)."""

import pytest

from src.core.tools import BaseTool, ToolDefinition, ToolResult, ToolStatus
from src.agent_system.tools.registry import ToolRegistry


class _FakeTool(BaseTool):
    """A minimal tool implementation for testing the registry."""

    def __init__(self, name, description="A test tool", category="general",
                 requires_approval=False, result_data=None):
        self._name = name
        self._description = description
        self._category = category
        self._requires_approval = requires_approval
        self._result_data = result_data if result_data is not None else {"result": "ok"}

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self._name,
            description=self._description,
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            category=self._category,
            requires_approval=self._requires_approval,
        )

    async def execute(self, **kwargs) -> ToolResult:
        return ToolResult(status=ToolStatus.SUCCESS, data=self._result_data)


@pytest.fixture
def registry() -> ToolRegistry:
    return ToolRegistry()


class TestToolRegistry:
    """Tests for tool registration and querying."""

    def test_register_tool(self, registry):
        registry.register(_FakeTool("search"))
        assert "search" in registry
        assert len(registry) == 1

    def test_register_duplicate_raises(self, registry):
        registry.register(_FakeTool("search"))
        with pytest.raises(ValueError, match="already registered"):
            registry.register(_FakeTool("search"))

    def test_list_all(self, registry):
        registry.register(_FakeTool("a"))
        registry.register(_FakeTool("b"))
        defs = registry.list_all()
        names = {d.name for d in defs}
        assert names == {"a", "b"}

    def test_get_tool(self, registry):
        registry.register(_FakeTool("calculator"))
        tool = registry.get_tool("calculator")
        assert tool.definition.name == "calculator"

    def test_get_nonexistent_tool_raises(self, registry):
        with pytest.raises(KeyError):
            registry.get_tool("nonexistent")

    def test_unregister(self, registry):
        registry.register(_FakeTool("temp"))
        assert "temp" in registry
        registry.unregister("temp")
        assert "temp" not in registry

    def test_get_openai_tools(self, registry):
        registry.register(_FakeTool("web_search"))
        tools = registry.get_openai_tools()
        assert len(tools) == 1
        assert tools[0]["type"] == "function"
        assert tools[0]["function"]["name"] == "web_search"


class TestToolRegistryExecution:
    """Tests for tool execution through the registry."""

    @pytest.fixture
    def registry(self) -> ToolRegistry:
        r = ToolRegistry()
        r.register(_FakeTool("counter", result_data={"called": True}))
        return r

    @pytest.mark.asyncio
    async def test_execute_tool(self, registry):
        result = await registry.execute("counter", query="hello")
        assert result.status == ToolStatus.SUCCESS
        assert result.data == {"called": True}

    @pytest.mark.asyncio
    async def test_execute_missing_required_arg(self, registry):
        # "query" is required but not provided
        result = await registry.execute("counter")
        assert result.status == ToolStatus.INVALID_ARGS

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self, registry):
        result = await registry.execute("nonexistent")
        assert result.status == ToolStatus.FATAL_ERROR
        assert "Unknown tool" in result.error


class TestToolRegistrySearch:
    """Tests for the keyword-based tool search."""

    def test_search_finds_by_name(self):
        r = ToolRegistry()
        r.register(_FakeTool("web_search", description="Search the internet"))
        results = r.search("search")
        assert len(results) >= 1
        assert results[0].name == "web_search"

    def test_search_empty_registry(self):
        r = ToolRegistry()
        assert r.search("anything") == []
