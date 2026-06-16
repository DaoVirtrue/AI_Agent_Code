"""
Reflection agent pattern - self-critique and iterative improvement.

The agent generates an initial response, then self-critiques it,
and iteratively improves the answer based on its own feedback.

Workflow: generate -> reflect -> [generate -> reflect -> ...] -> finalize
"""

import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

logger = logging.getLogger(__name__)


@dataclass
class ReflectionState(TypedDict, total=False):
    """State for the reflection agent."""
    task: str
    current_answer: str
    critique: str
    reflection_count: int
    max_reflections: int
    history: list[dict]  # [{"answer": ..., "critique": ..., "iteration": ...}]
    final_answer: str
    should_continue: bool


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


class ReflectionAgent:
    """Self-critique and iterative improvement agent.

    Uses LangGraph to orchestrate generate -> reflect -> improve cycles.
    The agent critiques its own output and refines it over multiple rounds.

    Args:
        llm: A LangChain-compatible chat model.
        max_reflections: Maximum number of reflection-improvement cycles (default 3).
        improvement_threshold: Stop early if no significant improvement is found.
    """

    def __init__(self, llm, max_reflections: int = 3, improvement_threshold: float = 0.1):
        self.llm = llm
        self.max_reflections = max_reflections
        self.improvement_threshold = improvement_threshold
        self._compiled = None

    # ------------------------------------------------------------------
    # Graph construction
    # ------------------------------------------------------------------

    def build_graph(self) -> StateGraph:
        """Build the reflection graph.

        Nodes: generate, reflect, improve, finalize
        Flow: generate -> reflect -> [improve -> generate -> reflect -> ... -> finalize]
        """
        if self._compiled is not None:
            return self._compiled

        builder = StateGraph(ReflectionState)

        builder.add_node("generate", self._generate_node)
        builder.add_node("reflect", self._reflect_node)
        builder.add_node("improve", self._improve_node)
        builder.add_node("finalize", self._finalize_node)

        builder.set_entry_point("generate")
        builder.add_edge("generate", "reflect")

        builder.add_conditional_edges(
            "reflect",
            self._after_reflect,
            {
                "improve": "improve",
                "finalize": "finalize",
            },
        )

        builder.add_edge("improve", "generate")
        builder.add_edge("finalize", END)

        self._compiled = builder.compile()
        return self._compiled

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def _after_reflect(self, state: ReflectionState) -> str:
        """Decide whether to improve or finalize."""
        if state.get("should_continue", True):
            count = state.get("reflection_count", 0)
            max_r = state.get("max_reflections", self.max_reflections)
            if count < max_r:
                return "improve"
        return "finalize"

    # ------------------------------------------------------------------
    # Nodes
    # ------------------------------------------------------------------

    async def _generate_node(self, state: ReflectionState) -> dict:
        """Generate an answer to the task.

        On first call, generates from scratch. On subsequent calls,
        generates improved version based on critique.
        """
        task = state.get("task", "")
        history = state.get("history", [])
        reflection_count = state.get("reflection_count", 0)

        if not history:
            # First generation
            prompt = (
                "You are a helpful AI assistant. Provide a thorough, well-reasoned "
                "answer to the following task. Think step by step and be comprehensive.\n\n"
                f"Task: {task}\n\n"
                "Answer:"
            )
        else:
            # Revision based on critique
            last_entry = history[-1]
            previous_answer = last_entry.get("answer", "")
            critique = last_entry.get("critique", "")

            prompt = (
                "You are a helpful AI assistant. Your previous answer had some "
                "shortcomings. Review the critique below and provide an improved, "
                "revised answer that addresses all the feedback.\n\n"
                f"Task: {task}\n\n"
                f"Previous Answer:\n{previous_answer}\n\n"
                f"Critique:\n{critique}\n\n"
                "Improved Answer (address every point in the critique):"
            )

        try:
            response = await self.llm.ainvoke([{"role": "user", "content": prompt}])
            answer = response.content if hasattr(response, "content") else str(response)
        except Exception as e:
            logger.exception("Generation failed in reflection agent")
            answer = f"Error generating answer: {e}"

        return {
            "current_answer": answer,
            "reflection_count": reflection_count,
        }

    async def _reflect_node(self, state: ReflectionState) -> dict:
        """Critique the current answer and identify areas for improvement."""
        task = state.get("task", "")
        answer = state.get("current_answer", "")
        history = list(state.get("history", []))

        prompt = (
            "You are a critical reviewer. Analyze the following answer to the task "
            "and identify specific weaknesses, missing information, logical flaws, "
            "or areas where the answer could be improved. Be specific and actionable.\n\n"
            f"Task: {task}\n\n"
            f"Answer to review:\n{answer}\n\n"
            "Critique (be specific about what to improve and how):"
        )

        try:
            response = await self.llm.ainvoke([{"role": "user", "content": prompt}])
            critique = response.content if hasattr(response, "content") else str(response)
        except Exception as e:
            critique = f"Error generating critique: {e}"

        reflection_count = state.get("reflection_count", 0) + 1

        # Add to history
        history.append({
            "answer": answer,
            "critique": critique,
            "iteration": reflection_count,
        })

        # Determine if we should continue
        should_continue = self._should_continue_reflecting(critique, history)

        return {
            "critique": critique,
            "reflection_count": reflection_count,
            "history": history,
            "should_continue": should_continue,
        }

    def _should_continue_reflecting(self, critique: str, history: list[dict]) -> bool:
        """Heuristic to decide if more reflection rounds are beneficial.

        Stops early if the critique indicates the answer is already good,
        or if improvements are diminishing.
        """
        positive_signals = [
            "no major issues", "well done", "comprehensive",
            "thorough", "well-reasoned", "excellent",
            "no significant", "minor", "adequate",
            "sufficiently addresses", "correctly",
        ]

        negative_signals = [
            "missing", "incorrect", "wrong", "incomplete",
            "needs more", "should include", "overlooked",
            "contradiction", "inconsistent", "error",
            "fails to", "does not",
        ]

        critique_lower = critique.lower()

        # If critique is mostly positive, stop
        positive_count = sum(1 for s in positive_signals if s in critique_lower)
        negative_count = sum(1 for s in negative_signals if s in critique_lower)

        if negative_count == 0 or (positive_count > 0 and negative_count <= 1):
            return False

        # Check for diminishing returns (similar critiques in a row)
        if len(history) >= 2:
            last_two = history[-2:]
            if len(set(e.get("critique", "")[:200] for e in last_two)) == 1:
                return False

        return True

    async def _improve_node(self, state: ReflectionState) -> dict:
        """Transition node - the actual improvement happens in generate_node
        on the next iteration. This node prepares the state."""
        return {
            "reflection_count": state.get("reflection_count", 0),
        }

    async def _finalize_node(self, state: ReflectionState) -> dict:
        """Produce the final answer from the history."""
        history = state.get("history", [])
        if history:
            final_answer = history[-1].get("answer", state.get("current_answer", ""))
        else:
            final_answer = state.get("current_answer", "")

        return {"final_answer": final_answer}

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    async def run(self, task: str) -> AgentResult:
        """Execute the reflection agent on a task.

        Args:
            task: The task description.

        Returns:
            AgentResult with the final answer and metadata.
        """
        agent_id = str(uuid.uuid4())[:8]
        start_time = time.perf_counter()

        try:
            graph = self.build_graph()
            initial: ReflectionState = {
                "task": task,
                "current_answer": "",
                "critique": "",
                "reflection_count": 0,
                "max_reflections": self.max_reflections,
                "history": [],
                "final_answer": "",
                "should_continue": True,
            }

            final_state = await graph.ainvoke(initial)
            answer = final_state.get("final_answer", "")
            history = final_state.get("history", [])

            elapsed = (time.perf_counter() - start_time) * 1000

            return AgentResult(
                agent_id=agent_id,
                task=task,
                answer=answer or "No answer produced.",
                steps=len(history),
                tools_used=[],  # Reflection agent doesn't use tools in this implementation
                tool_results=[
                    {"iteration": h["iteration"], "critique_length": len(h["critique"])}
                    for h in history
                ],
                execution_time_ms=elapsed,
                success=True,
            )

        except Exception as e:
            elapsed = (time.perf_counter() - start_time) * 1000
            logger.exception("Reflection agent failed")
            return AgentResult(
                agent_id=agent_id,
                task=task,
                answer="",
                steps=0,
                tools_used=[],
                tool_results=[],
                execution_time_ms=elapsed,
                success=False,
                error=str(e),
            )
