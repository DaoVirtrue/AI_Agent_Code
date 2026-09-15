"""
ReWOO (Reasoning Without Observation) agent pattern.

ReWOO minimizes LLM calls by separating reasoning from execution:
1. Planner: Generates a complete plan with tool calls (1 LLM call)
2. Worker: Executes all tool calls in parallel (0 LLM calls)
3. Solver: Synthesizes results into final answer (1 LLM call)

Total: Only 2-3 LLM calls regardless of task complexity.
"""

import asyncio
import logging
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from src.core.tools import BaseTool, ToolResult

logger = logging.getLogger(__name__)


@dataclass
class ReWOOState(TypedDict, total=False):
    """State for the ReWOO agent."""
    task: str
    plan: str  # Raw plan text with #E1, #E2 placeholders
    plan_steps: list[dict]  # Parsed steps: [{"id": "E1", "tool": "...", "args": {...}}]
    tool_results: dict[str, Any]  # {"E1": result_data, "E2": ...}
    final_answer: str
    errors: list[str]


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


class ReWOOAgent:
    """Reasoning Without Observation agent.

    Separates planning from execution to minimize LLM calls:
    - Plan: Generate all tool calls upfront (1 call)
    - Execute: Run all tools in parallel (0 calls)
    - Solve: Synthesize final answer (1 call)

    Args:
        llm: A LangChain-compatible chat model.
        tools: List of BaseTool instances.
        system_prompt: Optional custom system prompt.
    """

    def __init__(self, llm, tools: list[BaseTool], system_prompt: str | None = None):
        self.llm = llm
        self.tools = tools
        self.tools_by_name = {t.definition.name: t for t in tools}
        self.system_prompt = system_prompt
        self._compiled = None

    # ------------------------------------------------------------------
    # Graph construction
    # ------------------------------------------------------------------

    def build_graph(self) -> StateGraph:
        """Build the ReWOO graph: plan -> execute -> solve."""
        if self._compiled is not None:
            return self._compiled

        builder = StateGraph(ReWOOState)

        builder.add_node("plan", self._plan_node)
        builder.add_node("execute", self._execute_node)
        builder.add_node("solve", self._solve_node)

        builder.set_entry_point("plan")
        builder.add_edge("plan", "execute")
        builder.add_edge("execute", "solve")
        builder.add_edge("solve", END)

        self._compiled = builder.compile()
        return self._compiled

    # ------------------------------------------------------------------
    # Plan node (1 LLM call)
    # ------------------------------------------------------------------

    async def _plan_node(self, state: ReWOOState) -> dict:
        """Generate a plan with explicit tool call placeholders."""
        task = state.get("task", "")

        tool_schemas = []
        for t in self.tools:
            defn = t.definition
            tool_schemas.append(
                f"- Tool: {defn.name}\n"
                f"  Description: {defn.description}\n"
                f"  Parameters: {defn.parameters.get('properties', {})}"
            )

        plan_prompt = (
            "You are a planning agent. Given a task, create a plan that uses "
            "tools to solve it. For each tool call, use a placeholder of the form "
            "'#E{{number}}' where the result will be substituted. "
            "Use the format:\n\n"
            "Plan:\n"
            "1. [Action description]\n"
            "#E1 = tool_name[arg1=value1, arg2=value2]\n"
            "2. [Next action, can reference #E1]\n"
            "#E2 = tool_name[arg1=#E1, ...]\n"
            "...\n\n"
            "Available tools:\n"
            f"{''.join(tool_schemas)}\n\n"
            f"Task: {task}\n\n"
            "Provide your plan:"
        )

        try:
            response = await self.llm.ainvoke([{"role": "user", "content": plan_prompt}])
            plan_text = response.content if hasattr(response, "content") else str(response)
        except Exception as e:
            logger.exception("ReWOO plan generation failed")
            return {"plan": f"Error generating plan: {e}", "plan_steps": [], "errors": [str(e)]}

        plan_steps = self._parse_plan_steps(plan_text)
        return {"plan": plan_text, "plan_steps": plan_steps, "errors": []}

    def _parse_plan_steps(self, plan_text: str) -> list[dict]:
        """Parse plan text to extract tool calls with #E placeholders.

        Looks for patterns like: #E1 = tool_name[arg1=val1, ...]
        """
        steps = []
        pattern = r'#E(\d+)\s*=\s*(\w+)\[(.*?)\]'
        for match in re.finditer(pattern, plan_text):
            step_id = f"E{match.group(1)}"
            tool_name = match.group(2)
            raw_args = match.group(3)

            # Parse key=value arguments
            args = {}
            arg_pattern = r'(\w+)\s*=\s*([^,\]]+)'
            for arg_match in re.finditer(arg_pattern, raw_args):
                key = arg_match.group(1).strip()
                value = arg_match.group(2).strip().strip("\"'")
                # Try to parse as number
                try:
                    if '.' in value:
                        value = float(value)
                    else:
                        value = int(value)
                except ValueError:
                    pass
                args[key] = value

            steps.append({
                "id": step_id,
                "tool": tool_name,
                "args": args,
            })

        return steps

    # ------------------------------------------------------------------
    # Execute node (parallel tool execution)
    # ------------------------------------------------------------------

    async def _execute_node(self, state: ReWOOState) -> dict:
        """Execute all planned tool calls in parallel."""
        plan_steps = state.get("plan_steps", [])
        tool_results: dict[str, Any] = {}
        errors: list[str] = list(state.get("errors", []))

        async def execute_step(step: dict, resolved_args: dict):
            step_id = step["id"]
            tool_name = step["tool"]

            if tool_name not in self.tools_by_name:
                return step_id, None, f"Unknown tool: {tool_name}"

            tool = self.tools_by_name[tool_name]
            try:
                result: ToolResult = await tool.execute(**resolved_args)
                if result.status.value == "success":
                    return step_id, result.data, None
                else:
                    return step_id, None, result.error
            except Exception as e:
                return step_id, None, str(e)

        # Need to resolve placeholders sequentially for dependencies,
        # then run independent calls in parallel
        resolved_results: dict[str, Any] = {}

        # Identify dependency order
        executed = set()
        remaining = list(range(len(plan_steps)))
        max_iterations = len(plan_steps) * 2  # safety valve
        iteration = 0

        while remaining and iteration < max_iterations:
            iteration += 1
            parallel_batch = []

            for idx in remaining[:]:
                step = plan_steps[idx]
                args = dict(step["args"])
                deps_resolved = True

                # Resolve placeholders in args
                for key, value in args.items():
                    if isinstance(value, str):
                        # Replace #E references with actual results
                        placeholder_match = re.match(r'^#E(\d+)$', value)
                        if placeholder_match:
                            ref_id = f"E{placeholder_match.group(1)}"
                            if ref_id in resolved_results:
                                args[key] = resolved_results[ref_id]
                            else:
                                deps_resolved = False

                if deps_resolved:
                    parallel_batch.append((idx, step, args))
                    remaining.remove(idx)

            if not parallel_batch:
                # Circular dependency or unresolved - break
                logger.warning("ReWOO: unresolved dependencies in plan steps")
                break

            # Execute batch in parallel
            tasks = [execute_step(step, args) for _, step, args in parallel_batch]
            batch_results = await asyncio.gather(*tasks)

            for step_id, data, error in batch_results:
                resolved_results[step_id] = data
                tool_results[step_id] = {"data": data, "error": error}
                if error:
                    errors.append(f"{step_id}: {error}")

        return {"tool_results": tool_results, "errors": errors}

    # ------------------------------------------------------------------
    # Solve node (1 LLM call)
    # ------------------------------------------------------------------

    async def _solve_node(self, state: ReWOOState) -> dict:
        """Synthesize final answer from tool results."""
        task = state.get("task", "")
        plan = state.get("plan", "")
        tool_results = state.get("tool_results", {})
        errors = state.get("errors", [])

        # Format tool results for the solver
        results_text = []
        for step_id, result in tool_results.items():
            if result.get("error"):
                results_text.append(f"{step_id}: ERROR - {result['error']}")
            else:
                data_str = str(result.get("data", ""))[:1000]
                results_text.append(f"{step_id}: {data_str}")

        solve_prompt = (
            "You are a final answer synthesizer. Based on the plan and its "
            "execution results, provide a comprehensive answer to the task.\n\n"
            f"Task: {task}\n\n"
            "Execution Results:\n"
            + "\n".join(results_text)
            + "\n\n"
            "Provide your final answer (be thorough, cite specific findings):"
        )

        try:
            response = await self.llm.ainvoke([{"role": "user", "content": solve_prompt}])
            answer = response.content if hasattr(response, "content") else str(response)
        except Exception as e:
            answer = f"Failed to synthesize answer: {e}"

        return {"final_answer": answer}

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    async def run(self, task: str) -> AgentResult:
        """Execute the ReWOO agent on a task.

        Args:
            task: The task description.

        Returns:
            AgentResult with answer and metadata.
        """
        agent_id = str(uuid.uuid4())[:8]
        start_time = time.perf_counter()

        try:
            graph = self.build_graph()
            initial: ReWOOState = {
                "task": task,
                "plan": "",
                "plan_steps": [],
                "tool_results": {},
                "final_answer": "",
                "errors": [],
            }

            final_state = await graph.ainvoke(initial)
            answer = final_state.get("final_answer", "")
            plan_steps = final_state.get("plan_steps", [])
            tool_results = final_state.get("tool_results", {})

            # Collect tools used
            tools_used = list(set(s.get("tool", "") for s in plan_steps if s.get("tool")))

            step_results = [
                {"step_id": s["id"], "tool": s["tool"], "args": s["args"],
                 "result": tool_results.get(s["id"], {})}
                for s in plan_steps
            ]

            elapsed = (time.perf_counter() - start_time) * 1000

            return AgentResult(
                agent_id=agent_id,
                task=task,
                answer=answer or "No answer produced.",
                steps=len(plan_steps),
                tools_used=tools_used,
                tool_results=step_results,
                execution_time_ms=elapsed,
                success=True,
            )

        except Exception as e:
            elapsed = (time.perf_counter() - start_time) * 1000
            logger.exception("ReWOO agent failed")
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
