"""
Plan-and-Execute agent pattern with optional replanning.

Workflow:
  plan -> execute -> [replan -> execute ...] -> finalize

The agent first creates a step-by-step plan, then executes each step.
After execution, it may replan based on results before finalizing.
"""

import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from agent_system.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


@dataclass
class PlanExecuteState(TypedDict, total=False):
    """State for the plan-execute agent."""
    task: str
    plan: list[dict]  # [{"step_id": int, "description": str, "tool": str, "args": dict}]
    current_step_index: int
    step_results: list[dict]  # [{"step_id": int, "result": Any, "success": bool}]
    observations: list[str]
    final_answer: str
    should_replan: bool
    replan_count: int
    max_replans: int


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


class PlanExecuteAgent:
    """Plan-and-Execute agent using LangGraph.

    Creates a plan, executes steps sequentially, optionally replans,
    and then finalizes with a comprehensive answer.

    Args:
        llm: A LangChain-compatible chat model.
        tools: List of available tools.
        max_replans: Maximum number of replanning cycles (default 2).
        max_plan_steps: Maximum steps in a plan (default 10).
    """

    def __init__(
        self,
        llm,
        tools: list[BaseTool],
        max_replans: int = 2,
        max_plan_steps: int = 10,
    ):
        self.llm = llm
        self.tools = tools
        self.tools_by_name = {t.definition.name: t for t in tools}
        self.max_replans = max_replans
        self.max_plan_steps = max_plan_steps
        self._compiled = None

    # ------------------------------------------------------------------
    # Graph construction
    # ------------------------------------------------------------------

    def build_graph(self) -> StateGraph:
        """Build the plan-execute LangGraph.

        Nodes: plan, execute, replan, finalize
        Edges: plan -> execute -> conditional -> [replan -> execute | finalize]
        """
        if self._compiled is not None:
            return self._compiled

        builder = StateGraph(PlanExecuteState)

        builder.add_node("plan", self._plan_node)
        builder.add_node("execute", self._execute_node)
        builder.add_node("replan", self._replan_node)
        builder.add_node("finalize", self._finalize_node)

        builder.set_entry_point("plan")
        builder.add_edge("plan", "execute")

        builder.add_conditional_edges(
            "execute",
            self._after_execute,
            {
                "replan": "replan",
                "finalize": "finalize",
                "end": END,
            },
        )

        builder.add_conditional_edges(
            "replan",
            self._after_replan,
            {
                "execute": "execute",
                "finalize": "finalize",
            },
        )

        builder.add_edge("finalize", END)

        self._compiled = builder.compile()
        return self._compiled

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def _after_execute(self, state: PlanExecuteState) -> str:
        """Decide next step after execution."""
        plan = state.get("plan", [])
        current = state.get("current_step_index", 0)

        # If all steps executed, go to finalize
        if current >= len(plan):
            return "finalize"

        # Check if replanning is needed
        if state.get("should_replan", False):
            replan_count = state.get("replan_count", 0)
            if replan_count < state.get("max_replans", self.max_replans):
                return "replan"

        return "finalize"

    def _after_replan(self, state: PlanExecuteState) -> str:
        """Decide next step after replanning."""
        plan = state.get("plan", [])
        if plan:
            return "execute"
        return "finalize"

    # ------------------------------------------------------------------
    # Nodes
    # ------------------------------------------------------------------

    async def _plan_node(self, state: PlanExecuteState) -> dict:
        """Generate a step-by-step plan for the task."""
        task = state.get("task", "")
        tool_descriptions = "\n".join(
            f"- {t.definition.name}: {t.definition.description}"
            for t in self.tools
        )

        prompt = (
            "You are a planning agent. Given a task, create a step-by-step plan "
            "to accomplish it using the available tools. Output your plan as a "
            "numbered list of steps. Each step should specify:\n"
            "1. The tool to use (if any)\n"
            "2. The specific action to take\n"
            "3. What information you expect to obtain\n\n"
            "Available tools:\n"
            f"{tool_descriptions}\n\n"
            f"Task: {task}\n\n"
            "Plan (maximum 10 steps):"
        )

        try:
            response = await self.llm.ainvoke([{"role": "user", "content": prompt}])
            plan_text = response.content if hasattr(response, "content") else str(response)
        except Exception as e:
            logger.exception("Plan generation failed")
            plan_text = f"STEP 1: Report error - {e}"

        # Parse the plan into structured steps
        plan_steps = self._parse_plan(plan_text)

        return {
            "plan": plan_steps,
            "current_step_index": 0,
            "step_results": [],
            "observations": [],
            "replan_count": 0,
            "max_replans": self.max_replans,
            "should_replan": False,
        }

    async def _execute_node(self, state: PlanExecuteState) -> dict:
        """Execute the current step in the plan."""
        plan = state.get("plan", [])
        idx = state.get("current_step_index", 0)
        results = list(state.get("step_results", []))
        observations = list(state.get("observations", []))

        if idx >= len(plan):
            return {"should_replan": False}

        step = plan[idx]
        step_desc = step.get("description", "")
        tool_name = step.get("tool", "")
        args = step.get("args", {})

        step_result = {
            "step_id": step.get("step_id", idx),
            "description": step_desc,
            "success": False,
            "result": None,
            "error": None,
        }

        if tool_name and tool_name in self.tools_by_name:
            try:
                tool = self.tools_by_name[tool_name]
                result: ToolResult = await tool.execute(**args)
                step_result["success"] = result.status.value == "success"
                step_result["result"] = result.data if result.status.value == "success" else None
                step_result["error"] = result.error
                observations.append(
                    f"Step {idx + 1} ({tool_name}): "
                    f"{'SUCCESS' if step_result['success'] else 'FAILED'} - "
                    f"{str(result.data)[:200] if result.data else result.error}"
                )
            except Exception as e:
                step_result["error"] = str(e)
                observations.append(f"Step {idx + 1}: ERROR - {e}")
        else:
            # No tool step - just record it
            observations.append(f"Step {idx + 1}: {step_desc} (no tool)")
            step_result["success"] = True

        results.append(step_result)

        # Check if we should replan based on failures
        recent_failures = sum(
            1 for r in results[-3:] if not r.get("success", False)
        )
        should_replan = recent_failures >= 2

        return {
            "current_step_index": idx + 1,
            "step_results": results,
            "observations": observations,
            "should_replan": should_replan,
        }

    async def _replan_node(self, state: PlanExecuteState) -> dict:
        """Replan based on observations so far."""
        task = state.get("task", "")
        plan = state.get("plan", [])
        idx = state.get("current_step_index", 0)
        observations = state.get("observations", [])
        replan_count = state.get("replan_count", 0) + 1

        remaining_steps = plan[idx:] if idx < len(plan) else []
        remaining_desc = "\n".join(
            f"  {s.get('step_id', i)}. {s.get('description', '')}"
            for i, s in enumerate(remaining_steps)
        )

        prompt = (
            "You are a planning agent. The original plan has been partially executed. "
            "Based on the observations so far, adjust the remaining steps if needed.\n\n"
            f"Original Task: {task}\n\n"
            "Observations so far:\n"
            + "\n".join(f"- {o}" for o in observations[-10:])
            + "\n\n"
            "Remaining steps from original plan:\n"
            f"{remaining_desc}\n\n"
            "Provide an updated list of remaining steps (numbered). "
            "If the original plan is still valid, return it unchanged. "
            "If we have enough information, you can reduce or remove steps."
        )

        try:
            response = await self.llm.ainvoke([{"role": "user", "content": prompt}])
            plan_text = response.content if hasattr(response, "content") else str(response)
        except Exception:
            plan_text = ""

        if plan_text and "unchanged" not in plan_text.lower():
            new_remaining = self._parse_plan(plan_text)
            # Keep completed steps + new remaining steps
            completed = plan[:idx]
            new_plan = completed + new_remaining
            return {
                "plan": new_plan,
                "current_step_index": idx,  # Continue from where we were
                "replan_count": replan_count,
                "should_replan": False,
            }

        return {
            "replan_count": replan_count,
            "should_replan": False,
        }

    async def _finalize_node(self, state: PlanExecuteState) -> dict:
        """Produce the final answer based on all step results."""
        task = state.get("task", "")
        observations = state.get("observations", [])
        step_results = state.get("step_results", [])

        context = "Step results:\n" + "\n".join(
            f"  Step {r.get('step_id', i)}: "
            f"{'OK' if r.get('success') else 'FAIL'} - "
            f"{str(r.get('result', r.get('error', '')))[:300]}"
            for i, r in enumerate(step_results)
        )

        prompt = (
            "You are a final report writer. Based on the execution results below, "
            "provide a comprehensive final answer to the original task.\n\n"
            f"Task: {task}\n\n"
            f"{context}\n\n"
            "Final Answer:"
        )

        try:
            response = await self.llm.ainvoke([{"role": "user", "content": prompt}])
            answer = response.content if hasattr(response, "content") else str(response)
        except Exception as e:
            answer = f"Finalize failed: {e}"

        return {"final_answer": answer}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _parse_plan(self, plan_text: str) -> list[dict]:
        """Parse a numbered plan text into structured steps."""
        steps = []
        import re

        lines = plan_text.strip().split("\n")
        current_step = None

        for line in lines:
            # Match numbered steps: "1.", "Step 1:", "1)", etc.
            match = re.match(r'^(?:STEP\s+)?(\d+)[\.\):\-]?\s*(.+)', line.strip(), re.IGNORECASE)
            if match:
                if current_step:
                    steps.append(current_step)
                step_id = int(match.group(1))
                desc = match.group(2).strip()
                current_step = {"step_id": step_id, "description": desc, "tool": "", "args": {}}

                # Try to detect tool name
                for tool_name in self.tools_by_name:
                    if tool_name in desc.lower():
                        current_step["tool"] = tool_name
                        break

            elif current_step:
                # Continuation of previous step description
                current_step["description"] += " " + line.strip()

        if current_step:
            steps.append(current_step)

        if not steps:
            # Fallback: single step with the whole plan
            steps = [{"step_id": 1, "description": plan_text.strip(), "tool": "", "args": {}}]

        return steps[:self.max_plan_steps]

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    async def run(self, task: str) -> AgentResult:
        """Execute the plan-execute agent on a task.

        Args:
            task: The task description.

        Returns:
            AgentResult with answer and metadata.
        """
        agent_id = str(uuid.uuid4())[:8]
        start_time = time.perf_counter()
        tools_used: list[str] = []

        try:
            graph = self.build_graph()
            initial: PlanExecuteState = {
                "task": task,
                "plan": [],
                "current_step_index": 0,
                "step_results": [],
                "observations": [],
                "final_answer": "",
                "should_replan": False,
                "replan_count": 0,
                "max_replans": self.max_replans,
            }

            final_state = await graph.ainvoke(initial)
            answer = final_state.get("final_answer", "")
            step_results = final_state.get("step_results", [])

            # Collect tools used
            for sr in step_results:
                step = sr.get("description", "")
                for t_name in self.tools_by_name:
                    if t_name.lower() in step.lower() and t_name not in tools_used:
                        tools_used.append(t_name)

            elapsed = (time.perf_counter() - start_time) * 1000

            return AgentResult(
                agent_id=agent_id,
                task=task,
                answer=answer or "No answer produced.",
                steps=len(step_results),
                tools_used=tools_used,
                tool_results=step_results,
                execution_time_ms=elapsed,
                success=True,
            )

        except Exception as e:
            elapsed = (time.perf_counter() - start_time) * 1000
            logger.exception("Plan-Execute agent failed")
            return AgentResult(
                agent_id=agent_id,
                task=task,
                answer="",
                steps=0,
                tools_used=tools_used,
                tool_results=[],
                execution_time_ms=elapsed,
                success=False,
                error=str(e),
            )
