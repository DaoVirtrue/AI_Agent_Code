"""
ReAct (Reasoning + Acting) agent pattern with full LangGraph implementation.

Implements the ReAct paradigm: the agent reasons about the task, decides
which tool to use, acts by calling the tool, observes the result, and
continues reasoning until the task is complete.

Includes:
- Step limit enforcement
- Loop detection with force-conclude mechanism
- Tool execution via ToolNode
- Configurable LLM binding
"""

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from src.agent_system.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


@dataclass
class AgentState(TypedDict, total=False):
    """State carried through the ReAct agent graph."""
    messages: list[dict]
    task: str
    current_step: int
    tool_call_history: list[str]
    tool_results: list[dict]
    final_answer: str
    should_stop: bool
    loop_detected: bool


@dataclass
class AgentResult:
    """Result returned by an agent run."""
    agent_id: str
    task: str
    answer: str
    steps: int
    tools_used: list[str]
    tool_results: list[dict]
    execution_time_ms: float
    success: bool
    error: str | None = None


class ReActAgent:
    """ReAct agent implemented with LangGraph StateGraph.

    Flow: agent_node -> conditional_edge -> [tools_node -> agent_node | END]

    Args:
        llm: A LangChain-compatible chat model instance.
        tools: List of BaseTool instances available to the agent.
        max_steps: Maximum reasoning steps before forcing conclusion.
        loop_threshold: Consecutive identical tool calls before triggering loop detection.
        system_prompt: Optional custom system prompt. If None, a default is used.
    """

    def __init__(
        self,
        llm,
        tools: list[BaseTool],
        max_steps: int = 15,
        loop_threshold: int = 3,
        system_prompt: str | None = None,
    ):
        self.llm = llm
        self.tools = tools
        self.max_steps = max_steps
        self.loop_threshold = loop_threshold
        self.system_prompt = system_prompt
        self._graph: StateGraph | None = None
        self._compiled = None

    # ------------------------------------------------------------------
    # Graph construction
    # ------------------------------------------------------------------

    def build_graph(self) -> StateGraph:
        """Build the LangGraph StateGraph for the ReAct agent.

        Returns:
            A compiled LangGraph runnable.
        """
        if self._compiled is not None:
            return self._compiled

        builder = StateGraph(AgentState)

        # Nodes
        builder.add_node("agent", self._agent_node)
        builder.add_node("tools", ToolNode(self._build_tools_list()))
        builder.add_node("force_conclude", self._force_conclude)

        # Edges
        builder.set_entry_point("agent")

        builder.add_conditional_edges(
            "agent",
            self._should_continue,
            {
                "continue": "tools",
                "end": END,
                "force_end": "force_conclude",
            },
        )

        builder.add_edge("tools", "agent")
        builder.add_edge("force_conclude", END)

        self._compiled = builder.compile()
        return self._compiled

    def _build_tools_list(self) -> list:
        """Build a list of LangChain tool definitions from BaseTool instances.

        Creates simple callable wrappers that LangGraph's ToolNode can use.
        """
        langchain_tools = []
        for tool in self.tools:
            import json

            # We wrap each BaseTool as a LangChain StructuredTool-like object
            def make_tool(t: BaseTool):
                import asyncio
                from langchain_core.tools import tool as lc_tool

                def_name = t.definition.name
                def_desc = t.definition.description
                params = t.definition.parameters

                # Create a synchronous wrapper
                @lc_tool(def_name, description=def_desc)
                def wrapped(**kw):
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            import concurrent.futures
                            future = asyncio.run_coroutine_threadsafe(t.execute(**kw), loop)
                            result = future.result(timeout=t.definition.timeout_seconds)
                        else:
                            result = asyncio.run(t.execute(**kw))
                    except RuntimeError:
                        result = asyncio.run(t.execute(**kw))

                    if result.status.value == "success":
                        return json.dumps(result.data, ensure_ascii=False)
                    else:
                        return f"Error: {result.error}"

                return wrapped

            langchain_tools.append(make_tool(tool))

        return langchain_tools

    # ------------------------------------------------------------------
    # Routing logic
    # ------------------------------------------------------------------

    def _should_continue(self, state: AgentState) -> str:
        """Determine the next step in the graph.

        Returns:
            "continue": Route to tools node.
            "end": Task is complete, route to END.
            "force_end": Loop detected or max steps reached, force conclusion.
        """
        # Check step limit
        if state.get("current_step", 0) >= self.max_steps:
            logger.warning("Max steps (%d) reached, forcing conclusion", self.max_steps)
            return "force_end"

        # Check loop detection
        if self._detect_loop(state.get("tool_call_history", [])):
            logger.warning("Loop detected, forcing conclusion")
            state["loop_detected"] = True
            return "force_end"

        # Check if should stop (explicit flag)
        if state.get("should_stop", False):
            return "end"

        # Check if the last message contains a tool call
        messages = state.get("messages", [])
        if not messages:
            return "end"

        last_message = messages[-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "continue"

        # No tool call means the agent produced a final answer
        return "end"

    # ------------------------------------------------------------------
    # Loop detection
    # ------------------------------------------------------------------

    def _detect_loop(self, history: list[str]) -> bool:
        """Detect if the agent is stuck in a loop.

        Checks for consecutive identical tool calls exceeding the threshold.

        Args:
            history: List of recent tool call names.

        Returns:
            True if a loop is detected.
        """
        if len(history) < self.loop_threshold:
            return False

        # Check last N entries
        recent = history[-self.loop_threshold:]
        if len(set(recent)) == 1:
            # All recent calls are the same tool with the same args
            return True

        # Check for alternating pattern (A, B, A, B)
        if len(history) >= self.loop_threshold * 2:
            pattern = history[-self.loop_threshold * 2:]
            half = self.loop_threshold
            if pattern[:half] == pattern[half:]:
                return True

        return False

    # ------------------------------------------------------------------
    # Node functions
    # ------------------------------------------------------------------

    async def _agent_node(self, state: AgentState) -> dict:
        """Agent reasoning node. Calls the LLM and returns updated state.

        The LLM decides whether to call a tool or produce a final answer.
        """
        messages = self._build_prompt(state)
        step = state.get("current_step", 0) + 1

        # Bind tools to LLM
        from langgraph.prebuilt import ToolNode
        tool_node = ToolNode(self._build_tools_list())

        try:
            response = await self.llm.ainvoke(messages)
        except Exception as e:
            logger.exception("LLM call failed at step %d", step)
            return {
                "messages": messages + [{"role": "assistant", "content": f"Error: {e}"}],
                "current_step": step,
                "should_stop": True,
                "final_answer": f"An error occurred: {e}",
            }

        new_messages = messages + [response]

        # Track tool calls
        tool_calls = []
        if hasattr(response, "tool_calls") and response.tool_calls:
            for tc in response.tool_calls:
                tool_calls.append(tc.get("name", "unknown") if isinstance(tc, dict) else tc.name)

        return {
            "messages": new_messages,
            "current_step": step,
            "tool_call_history": state.get("tool_call_history", []) + tool_calls,
        }

    def _build_prompt(self, state: AgentState) -> list[dict]:
        """Build the message list for the LLM call.

        Includes system prompt, task, and conversation history.
        """
        messages = []

        # System prompt
        if self.system_prompt:
            sys = self.system_prompt
        else:
            tool_descriptions = "\n".join(
                f"- {t.definition.name}: {t.definition.description}"
                for t in self.tools
            )
            sys = (
                "You are a helpful AI assistant with access to tools. "
                "Use tools when needed to gather information or perform actions. "
                "When you have enough information to answer the user's task, "
                "provide a complete and well-structured final answer. "
                "Do not call tools if you already have the answer.\n\n"
                "Available tools:\n"
                f"{tool_descriptions}"
            )

        messages.append({"role": "system", "content": sys})

        # Task
        task = state.get("task", "")
        messages.append({"role": "user", "content": task})

        # History (messages already in state)
        existing = state.get("messages", [])
        if existing:
            # Skip the initial system+user if already present
            messages = existing
        else:
            # Ensure we have at least system + task
            pass

        return messages

    async def _force_conclude(self, state: AgentState) -> dict:
        """Force the agent to produce a conclusion when it's stuck.

        Called when max steps reached or loop detected.
        """
        messages = state.get("messages", [])
        task = state.get("task", "")

        conclusion_prompt = (
            f"You have reached the maximum number of steps or a loop was detected. "
            f"Based on the information gathered so far from tool calls, "
            f"please provide your best final answer to the task: '{task}'. "
            f"Summarize what you found and any conclusions you can draw. "
            f"Do NOT make any more tool calls."
        )

        try:
            # Force a response without tool binding
            force_messages = messages + [{"role": "user", "content": conclusion_prompt}]
            response = await self.llm.ainvoke(force_messages)
            content = response.content if hasattr(response, "content") else str(response)
        except Exception as e:
            content = f"Unable to force conclusion due to error: {e}"

        return {
            **state,
            "final_answer": content,
            "should_stop": True,
        }

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    async def run(self, task: str, **kwargs) -> AgentResult:
        """Execute the ReAct agent on a task.

        Args:
            task: The task description or question.
            **kwargs: Additional context or parameters.

        Returns:
            AgentResult with the answer and execution metadata.
        """
        agent_id = str(uuid.uuid4())[:8]
        start_time = time.perf_counter()

        graph = self.build_graph()

        initial_state: AgentState = {
            "messages": [],
            "task": task,
            "current_step": 0,
            "tool_call_history": [],
            "tool_results": [],
            "final_answer": "",
            "should_stop": False,
            "loop_detected": False,
        }

        tools_used: list[str] = []
        tool_results: list[dict] = []

        try:
            final_state = await graph.ainvoke(initial_state)

            answer = final_state.get("final_answer", "")
            if not answer:
                # Extract from last assistant message
                messages = final_state.get("messages", [])
                for msg in reversed(messages):
                    content = msg.content if hasattr(msg, "content") else msg.get("content", "")
                    if content and not getattr(msg, "tool_calls", None):
                        answer = content
                        break

            # Collect tool usage
            for msg in final_state.get("messages", []):
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    for tc in msg.tool_calls:
                        name = tc.get("name", "unknown") if isinstance(tc, dict) else tc.name
                        if name not in tools_used:
                            tools_used.append(name)

            elapsed = (time.perf_counter() - start_time) * 1000

            return AgentResult(
                agent_id=agent_id,
                task=task,
                answer=answer or "No answer produced.",
                steps=final_state.get("current_step", 0),
                tools_used=tools_used,
                tool_results=tool_results,
                execution_time_ms=elapsed,
                success=True,
            )

        except Exception as e:
            elapsed = (time.perf_counter() - start_time) * 1000
            logger.exception("ReAct agent failed")
            return AgentResult(
                agent_id=agent_id,
                task=task,
                answer="",
                steps=0,
                tools_used=tools_used,
                tool_results=tool_results,
                execution_time_ms=elapsed,
                success=False,
                error=str(e),
            )
