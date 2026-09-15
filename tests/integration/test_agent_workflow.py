"""Integration tests for the agent workflow from request to execution."""

import pytest
pytestmark = pytest.mark.skip(reason='M0: 引用不存在的旧模块 (src.agent.* / src.gateway.* / src.rag.*) 或缺 fixture (test_redis/test_db_session/test_app)，待 M2/M3 真实链路接通后重写。')
from unittest.mock import AsyncMock, MagicMock, patch


class TestAgentWorkflow:
    """Integration tests for agent execution workflow."""

    @pytest.fixture
    def agent_executor(self):
        """Create an agent executor with mocked tools."""
        from src.agent.executor import AgentExecutor
        from src.agent.tool_registry import ToolRegistry

        tool_registry = ToolRegistry()

        async def search_tool(**kwargs):
            return {"results": ["Result 1", "Result 2"]}

        async def calculator_tool(**kwargs):
            return {"result": 42}

        tool_registry.register("search", "Search the web", search_tool, {})
        tool_registry.register("calculator", "Do math", calculator_tool, {})

        executor = AgentExecutor(
            tool_registry=tool_registry,
            default_model="gpt-4o",
            max_steps=10,
        )

        return executor

    def test_executor_initialization(self, agent_executor):
        """Test that the executor initializes correctly."""
        assert agent_executor.default_model == "gpt-4o"
        assert agent_executor.max_steps == 10
        assert len(agent_executor.tool_registry.list_tools()) == 2

    @pytest.mark.asyncio
    async def test_execute_basic_task(self, agent_executor):
        """Test executing a simple task."""
        # Mock the LLM call to return a simple response
        with patch.object(agent_executor, '_call_llm', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = {
                "content": "Final Answer: The answer is 42.",
                "finish_reason": "stop",
            }

            result = await agent_executor.execute(
                task="What is the meaning of life?",
                agent_type="react",
                max_steps=5,
                tenant_id="test-tenant",
            )

            assert result.status == "completed"
            assert len(result.final_output) > 0

    @pytest.mark.asyncio
    async def test_execute_with_tool_calls(self, agent_executor):
        """Test executing a task that requires tool usage."""
        with patch.object(agent_executor, '_call_llm', new_callable=AsyncMock) as mock_llm:
            # First call: tool call for search
            # Second call: final answer
            responses = iter([
                {
                    "content": 'Thought: I need to search.\nAction: search\nAction Input: {"query": "test"}',
                    "finish_reason": "tool_calls",
                    "tool_calls": [{"function": {"name": "search", "arguments": '{"query": "test"}'}}],
                },
                {
                    "content": "Final Answer: Based on the search results, the answer is found.",
                    "finish_reason": "stop",
                },
            ])

            async def mock_call(*args, **kwargs):
                return next(responses)

            mock_llm.side_effect = mock_call

            result = await agent_executor.execute(
                task="Search for something",
                agent_type="react",
                tools=["search"],
                max_steps=5,
                tenant_id="test-tenant",
            )

            assert result.status == "completed"

    @pytest.mark.asyncio
    async def test_max_steps_enforcement(self, agent_executor):
        """Test that max steps limit is enforced."""
        with patch.object(agent_executor, '_call_llm', new_callable=AsyncMock) as mock_llm:
            # Return tool calls indefinitely to force max steps
            mock_llm.return_value = {
                "content": 'Thought: Keep going.\nAction: search\nAction Input: {"query": "x"}',
                "finish_reason": "tool_calls",
                "tool_calls": [{"function": {"name": "search", "arguments": '{"query": "x"}'}}],
            }

            result = await agent_executor.execute(
                task="Keep searching forever",
                agent_type="react",
                tools=["search"],
                max_steps=3,
                tenant_id="test-tenant",
            )

            assert result.status == "max_steps_reached"
            assert len(result.steps) <= 3

    @pytest.mark.asyncio
    async def test_loop_detection(self, agent_executor):
        """Test that agent loops are detected."""
        with patch.object(agent_executor, '_call_llm', new_callable=AsyncMock) as mock_llm:
            # Return the same action repeatedly to trigger loop detection
            mock_llm.return_value = {
                "content": 'Thought: Searching...\nAction: search\nAction Input: {"query": "same query"}',
                "finish_reason": "tool_calls",
                "tool_calls": [{"function": {"name": "search", "arguments": '{"query": "same query"}'}}],
            }

            result = await agent_executor.execute(
                task="Search for same thing repeatedly",
                agent_type="react",
                tools=["search"],
                max_steps=10,
                tenant_id="test-tenant",
            )

            assert result.loop_detected is True

    @pytest.mark.asyncio
    async def test_human_approval_required(self, agent_executor):
        """Test that human approval is requested for sensitive tools."""
        from src.agent.tool_registry import ToolRegistry

        async def delete_file_tool(**kwargs):
            return {"deleted": True}

        agent_executor.tool_registry.register(
            "delete_file",
            "Delete a file",
            delete_file_tool,
            {},
            requires_approval=True,
        )

        with patch.object(agent_executor, '_call_llm', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = {
                "content": 'Thought: Need to delete.\nAction: delete_file\nAction Input: {"path": "test.txt"}',
                "finish_reason": "tool_calls",
                "tool_calls": [{"function": {"name": "delete_file", "arguments": '{"path": "test.txt"}'}}],
            }

            result = await agent_executor.execute(
                task="Delete test file",
                agent_type="react",
                tools=["delete_file"],
                max_steps=3,
                require_approval=True,
                tenant_id="test-tenant",
            )

            # Should have paused for approval or completed depending on implementation
            assert result.status in ("completed", "max_steps_reached", "requires_approval")
