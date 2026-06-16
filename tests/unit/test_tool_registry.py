"""Unit tests for the tool registry module."""

import pytest
from unittest.mock import AsyncMock, MagicMock


class TestToolRegistry:
    """Tests for the ToolRegistry class."""

    @pytest.fixture
    def registry(self):
        """Create a tool registry for testing."""
        from src.agent.tool_registry import ToolRegistry
        return ToolRegistry()

    def test_register_tool(self, registry):
        """Test registering a new tool."""
        async def my_tool(**kwargs):
            return {"result": "success"}

        registry.register(
            name="search",
            description="Search the web",
            func=my_tool,
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                },
                "required": ["query"],
            },
        )

        assert "search" in registry.list_tools()

    def test_register_duplicate_tool(self, registry):
        """Test that registering a duplicate tool raises an error."""
        async def tool1(**kwargs):
            return {}

        registry.register("test_tool", "A test tool", tool1, {})

        async def tool2(**kwargs):
            return {}

        with pytest.raises(ValueError, match="already registered"):
            registry.register("test_tool", "Another test tool", tool2, {})

    def test_list_tools(self, registry):
        """Test listing all registered tools."""
        async def tool_a(**kwargs):
            return {}

        async def tool_b(**kwargs):
            return {}

        registry.register("tool_a", "Tool A", tool_a, {})
        registry.register("tool_b", "Tool B", tool_b, {})

        tools = registry.list_tools()
        assert "tool_a" in tools
        assert "tool_b" in tools
        assert len(tools) == 2

    def test_get_tool(self, registry):
        """Test getting a specific tool by name."""
        async def my_tool(**kwargs):
            return {"answer": 42}

        registry.register("calculator", "Calculate math", my_tool, {})

        tool = registry.get_tool("calculator")
        assert tool is not None
        assert tool.name == "calculator"

    def test_get_nonexistent_tool(self, registry):
        """Test that getting a nonexistent tool raises an error."""
        with pytest.raises(KeyError):
            registry.get_tool("nonexistent")

    def test_unregister_tool(self, registry):
        """Test unregistering a tool."""
        async def my_tool(**kwargs):
            return {}

        registry.register("temp_tool", "Temporary", my_tool, {})
        assert "temp_tool" in registry.list_tools()

        registry.unregister("temp_tool")
        assert "temp_tool" not in registry.list_tools()

    @pytest.mark.asyncio
    async def test_execute_tool(self, registry):
        """Test executing a registered tool."""
        calls = []

        async def counting_tool(**kwargs):
            calls.append(kwargs)
            return {"called_with": kwargs}

        registry.register("counter", "Count calls", counting_tool, {})

        result = await registry.execute("counter", param1="hello", param2=123)
        assert len(calls) == 1
        assert calls[0]["param1"] == "hello"
        assert calls[0]["param2"] == 123
        assert result["called_with"]["param1"] == "hello"

    @pytest.mark.asyncio
    async def test_execute_nonexistent_tool(self, registry):
        """Test that executing a nonexistent tool raises an error."""
        with pytest.raises(KeyError):
            await registry.execute("nonexistent")

    def test_get_tool_schema(self, registry):
        """Test getting the OpenAI-format tool schema."""
        async def my_tool(**kwargs):
            return {}

        registry.register(
            name="web_search",
            description="Search the web for information",
            func=my_tool,
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query"},
                },
                "required": ["query"],
            },
        )

        schema = registry.get_tool_schema("web_search")
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "web_search"
        assert "description" in schema["function"]

    def test_get_all_schemas(self, registry):
        """Test getting all tool schemas at once."""
        async def t1(**kwargs):
            return {}

        async def t2(**kwargs):
            return {}

        registry.register("tool1", "First tool", t1, {"type": "object", "properties": {}})
        registry.register("tool2", "Second tool", t2, {"type": "object", "properties": {}})

        schemas = registry.get_all_schemas()
        assert len(schemas) == 2

    def test_requires_approval_flag(self, registry):
        """Test the requires_approval flag for tools."""
        async def dangerous_tool(**kwargs):
            return {}

        registry.register(
            name="delete_file",
            description="Delete a file",
            func=dangerous_tool,
            parameters={},
            requires_approval=True,
        )

        tool = registry.get_tool("delete_file")
        assert tool.requires_approval is True
