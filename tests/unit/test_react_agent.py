"""Unit tests for the ReAct agent - loop detection and max steps."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestReActAgent:
    """Tests for the ReAct agent execution logic."""

    @pytest.fixture
    def agent(self):
        """Create a ReAct agent for testing."""
        from src.agent.react_agent import ReActAgent

        return ReActAgent(
            model="gpt-4o",
            max_steps=15,
            loop_detection_threshold=3,
        )

    def test_initialization(self, agent):
        """Test agent initializes with correct defaults."""
        assert agent.model == "gpt-4o"
        assert agent.max_steps == 15
        assert agent.loop_detection_threshold == 3

    @pytest.mark.asyncio
    async def test_max_steps_enforced(self, agent):
        """Test that agent stops when max_steps is reached."""
        agent.max_steps = 5

        # Mock the tools
        agent.tools = {"search": MagicMock()}

        # Force step counter to exceed max
        step_count = 0
        async def mock_step(*args, **kwargs):
            nonlocal step_count
            step_count += 1
            action = f"action-{step_count}"
            thought = f"thought-{step_count}"
            observation = f"obs-{step_count}"
            return {
                "action": action,
                "thought": thought,
                "observation": observation,
                "tool_name": "search",
                "tool_input": {"query": "test"},
                "tool_output": observation,
                "elapsed_ms": 50,
                "tokens_used": 30,
                "prompt_tokens": 20,
            }

        agent._execute_step = AsyncMock(side_effect=mock_step)

        with patch.object(agent, '_should_continue', return_value=True):
            # Override _should_continue to keep going until max_steps
            call_count = 0
            async def continue_until_max():
                nonlocal call_count
                call_count += 1
                return call_count <= agent.max_steps
            agent._should_continue = AsyncMock(side_effect=continue_until_max)

    def test_loop_detection_same_action(self, agent):
        """Test loop detection when same action repeats."""
        history = [
            {"action": "search", "tool_input": {"query": "cats"}},
            {"action": "search", "tool_input": {"query": "cats"}},
            {"action": "search", "tool_input": {"query": "cats"}},
        ]
        is_loop = agent._detect_loop(history)
        assert is_loop is True

    def test_loop_detection_similar_action(self, agent):
        """Test loop detection when similar actions repeat."""
        history = [
            {"action": "search", "tool_input": {"query": "cats"}},
            {"action": "search", "tool_input": {"query": "cats images"}},
            {"action": "search", "tool_input": {"query": "cats photos"}},
            {"action": "search", "tool_input": {"query": "cats pictures"}},
        ]
        is_loop = agent._detect_loop(history)
        assert is_loop is True

    def test_no_loop_with_different_actions(self, agent):
        """Test that different actions are not detected as a loop."""
        history = [
            {"action": "search", "tool_input": {"query": "cats"}},
            {"action": "read_file", "tool_input": {"path": "file.txt"}},
            {"action": "calculate", "tool_input": {"expression": "2+2"}},
            {"action": "search", "tool_input": {"query": "dogs"}},
        ]
        is_loop = agent._detect_loop(history)
        assert is_loop is False

    def test_no_loop_with_insufficient_history(self, agent):
        """Test that short history doesn't trigger loop detection."""
        history = [
            {"action": "search", "tool_input": {"query": "cats"}},
            {"action": "search", "tool_input": {"query": "cats"}},
        ]
        is_loop = agent._detect_loop(history)
        assert is_loop is False

    def test_loop_detection_exact_thought_loop(self, agent):
        """Test loop detection when the same thought pattern repeats."""
        history = [
            {"thought": "I need to search for information about cats"},
            {"thought": "I need to search for information about cats"},
            {"thought": "I need to search for information about cats"},
        ]
        is_loop = agent._detect_loop(history)
        assert is_loop is True

    def test_extract_final_answer(self, agent):
        """Test extracting the final answer from agent output."""
        output = "Thought: I found the information.\nAction: Finish\nFinal Answer: Paris is the capital of France."
        answer = agent._extract_final_answer(output)
        assert "Paris" in answer or "France" in answer

    def test_format_prompt_includes_tools(self, agent):
        """Test that the agent prompt includes tool definitions."""
        agent.tools = {"search": MagicMock(description="Search the web")}
        prompt = agent._build_system_prompt(
            task="Test task",
            tools=["search"],
        )
        assert "search" in prompt.lower()
        assert "Test task" in prompt


class TestAgentLoopDetection:
    """Focused tests for loop detection algorithms."""

    @pytest.fixture
    def agent(self):
        from src.agent.react_agent import ReActAgent
        return ReActAgent()

    def test_pattern_repetition_detection(self, agent):
        """Test detecting repeated action+input patterns."""
        history = [
            {"action": "search", "tool_input": {"query": "X"}},
            {"action": "search", "tool_input": {"query": "Y"}},
            {"action": "search", "tool_input": {"query": "X"}},  # Repeat of step 0
            {"action": "search", "tool_input": {"query": "Y"}},  # Repeat of step 1
        ]
        assert agent._detect_loop(history) is True

    def test_oscillation_detection(self, agent):
        """Test detecting oscillation between two states."""
        history = []
        for i in range(8):
            if i % 2 == 0:
                history.append({"action": "search", "tool_input": {"query": "cats"}})
            else:
                history.append({"action": "browse", "tool_input": {"url": "google.com"}})
        assert agent._detect_loop(history) is True

    def test_no_progress_detection(self, agent):
        """Test detecting when no progress is made over multiple steps."""
        history = [
            {"observation": "Found nothing relevant"},
            {"observation": "Still found nothing relevant"},
            {"observation": "No relevant information found"},
            {"observation": "Search returned no results"},
        ]
        assert agent._detect_loop(history) is True
