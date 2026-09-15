"""Unified AgentExecutor bridging the 4 agent patterns to a single API.

The existing ReAct / PlanExecute / ReWOO / Reflection patterns each expose
`run(task) -> AgentResult` with slightly different result shapes. The API
layer (`src/api/routes/agent_routes.py`) expects a single `execute(...)`
entry point returning `final_output / status / steps / loop_detected /
cost_usd`. This module provides that unified contract and adapts the
per-pattern results into a consistent trace.

Design notes:
- The LLM is injected (a LangChain-compatible object exposing `ainvoke`).
  It is deliberately optional so that M0 can wire the executor without a
  live model; the real DeepSeek/gateway-backed LLM is attached in M3.
- Tool selection resolves string names against a `ToolRegistry` when one is
  supplied, falling back to an empty tool list (no tools) otherwise.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from src.agent_system.tools.registry import ToolRegistry
from src.agent_system.tools.base import BaseTool
from src.agent_system.patterns.react import ReActAgent
from src.agent_system.patterns.plan_execute import PlanExecuteAgent
from src.agent_system.patterns.rewoo import ReWOOAgent
from src.agent_system.patterns.reflection import ReflectionAgent

logger = logging.getLogger(__name__)

# Agent types supported by the executor, mapped to their pattern classes.
AGENT_TYPE_MAP = {
    "react": ReActAgent,
    "plan_execute": PlanExecuteAgent,
    "rewoo": ReWOOAgent,
    "reflection": ReflectionAgent,
}

# Agent types that do not use tools (reflection is self-critique only).
TOOLLESS_AGENT_TYPES = {"reflection"}


@dataclass
class AgentExecutionResult:
    """Unified result returned by AgentExecutor.execute()."""

    final_output: str
    status: str  # completed | max_steps_reached | error | cancelled
    steps: list[dict] = field(default_factory=list)
    loop_detected: bool = False
    cost_usd: float = 0.0
    agent_id: str = ""
    tools_used: list[str] = field(default_factory=list)
    elapsed_ms: float = 0.0


class AgentExecutor:
    """Uniform execution interface over the four agent patterns.

    Args:
        tool_registry: Optional ToolRegistry used to resolve tool names.
        default_model: Model id used when the caller does not specify one.
        max_steps: Default maximum reasoning steps for the agent loop.
    """

    def __init__(
        self,
        tool_registry: ToolRegistry | None = None,
        default_model: str = "deepseek-chat",
        max_steps: int = 15,
    ):
        self.tool_registry = tool_registry or ToolRegistry()
        self.default_model = default_model
        self.max_steps = max_steps

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def execute(
        self,
        task: str,
        agent_type: str = "react",
        tools: list[str] | None = None,
        max_steps: int | None = None,
        model: str | None = None,
        temperature: float = 0.0,
        system_prompt: str | None = None,
        verbose: bool = False,
        tenant_id: str | None = None,
        llm: Any = None,
    ) -> AgentExecutionResult:
        """Run an agent of the given type against a task.

        Args:
            task: The task description.
            agent_type: One of react / plan_execute / rewoo / reflection.
            tools: Optional list of tool names to expose to the agent.
            max_steps: Maximum steps (falls back to executor default).
            model: Model id (informational at this stage; the LLM is injected).
            temperature: Sampling temperature (accepted for API parity).
            system_prompt: Optional custom system prompt.
            verbose: Whether to log detailed trace (accepted for API parity).
            tenant_id: Tenant identifier (accepted for API parity).
            llm: LangChain-compatible LLM. Required for real execution;
                 tests inject a mock.

        Returns:
            AgentExecutionResult with the final output and execution trace.
        """
        start = time.perf_counter()

        if agent_type not in AGENT_TYPE_MAP:
            return self._error_result(
                task,
                f"Unknown agent_type '{agent_type}'. "
                f"Supported: {sorted(AGENT_TYPE_MAP)}",
                start,
            )

        resolved_tools = self._resolve_tools(tools, agent_type)
        steps_limit = max_steps or self.max_steps

        try:
            agent = self._build_agent(
                agent_type=agent_type,
                llm=llm,
                tools=resolved_tools,
                max_steps=steps_limit,
                system_prompt=system_prompt,
            )
        except Exception as exc:  # noqa: BLE001 - missing LLM etc.
            return self._error_result(
                task, f"Failed to build agent '{agent_type}': {exc}", start
            )

        try:
            result = await agent.run(task)
        except Exception as exc:  # noqa: BLE001 - surface as a clean result
            logger.exception("Agent execution failed for type=%s", agent_type)
            return self._error_result(task, f"Agent execution failed: {exc}", start)

        return self._adapt_result(agent_type, task, result, start, steps_limit)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _resolve_tools(
        self, tool_names: list[str] | None, agent_type: str
    ) -> list[BaseTool]:
        """Resolve tool-name strings into BaseTool instances."""
        if agent_type in TOOLLESS_AGENT_TYPES:
            return []
        if not tool_names:
            return []

        resolved: list[BaseTool] = []
        for name in tool_names:
            try:
                resolved.append(self.tool_registry.get_tool(name))
            except KeyError:
                logger.warning("Unknown tool '%s' requested; skipped", name)
        return resolved

    def _build_agent(
        self,
        agent_type: str,
        llm: Any,
        tools: list[BaseTool],
        max_steps: int,
        system_prompt: str | None,
    ):
        """Instantiate the pattern class for the requested agent type."""
        if llm is None:
            raise ValueError(
                "An LLM is required to run agents. Pass `llm=` to execute() "
                "or configure one during wiring."
            )

        cls = AGENT_TYPE_MAP[agent_type]
        if agent_type == "react":
            return cls(llm=llm, tools=tools, max_steps=max_steps, system_prompt=system_prompt)
        if agent_type == "plan_execute":
            return cls(llm=llm, tools=tools)
        if agent_type == "rewoo":
            return cls(llm=llm, tools=tools, system_prompt=system_prompt)
        if agent_type == "reflection":
            return cls(llm=llm)
        raise ValueError(f"Unsupported agent_type: {agent_type}")

    def _adapt_result(
        self,
        agent_type: str,
        task: str,
        result: Any,
        start: float,
        steps_limit: int,
    ) -> AgentExecutionResult:
        """Adapt a per-pattern AgentResult into the unified shape."""
        answer = getattr(result, "answer", "") or ""
        success = getattr(result, "success", False)
        error = getattr(result, "error", None)
        tools_used = list(getattr(result, "tools_used", []) or [])
        tool_results = list(getattr(result, "tool_results", []) or [])
        elapsed_ms = (time.perf_counter() - start) * 1000

        steps = self._build_steps(answer, tool_results, agent_type, success, error)

        if error or not success:
            status = "error"
        elif self._looks_truncated(answer):
            status = "max_steps_reached"
        else:
            status = "completed"

        return AgentExecutionResult(
            final_output=answer or error or "No answer produced.",
            status=status,
            steps=steps,
            loop_detected=getattr(result, "loop_detected", False),
            cost_usd=round(getattr(result, "cost_usd", 0.0) or 0.0, 6),
            agent_id=getattr(result, "agent_id", ""),
            tools_used=tools_used,
            elapsed_ms=round(elapsed_ms, 2),
        )

    def _build_steps(
        self,
        answer: str,
        tool_results: list[dict],
        agent_type: str,
        success: bool,
        error: str | None,
    ) -> list[dict]:
        """Build a consistent step trace from whatever the pattern returned.

        Patterns differ in how much trace they expose: plan_execute/rewoo
        return per-tool `tool_results`, while react/reflection only return a
        final answer. We normalize into a list of step dicts that the API
        layer can render (Thought -> Action -> Observation).
        """
        steps: list[dict] = []

        if tool_results:
            for i, tr in enumerate(tool_results):
                if isinstance(tr, dict):
                    steps.append({
                        "step_number": i,
                        "action": tr.get("tool") or tr.get("action") or "",
                        "thought": tr.get("thought") or "",
                        "observation": str(tr.get("result") or tr.get("output") or ""),
                        "tool_name": tr.get("tool") or tr.get("tool_name") or "",
                        "tool_input": tr.get("args") or tr.get("tool_input") or {},
                        "tool_output": str(tr.get("result") or tr.get("tool_output") or ""),
                        "elapsed_ms": tr.get("elapsed_ms", 0.0),
                        "tokens_used": tr.get("tokens_used", 0),
                    })

        # Always append a final synthesis step so the trace ends on an answer.
        steps.append({
            "step_number": len(steps),
            "action": "final_answer",
            "thought": "",
            "observation": answer,
            "tool_name": "",
            "tool_input": {},
            "tool_output": answer,
            "elapsed_ms": 0.0,
            "tokens_used": 0,
        })

        if error:
            steps.append({
                "step_number": len(steps),
                "action": "error",
                "thought": "",
                "observation": error,
                "tool_name": "",
                "tool_input": {},
                "tool_output": error,
                "elapsed_ms": 0.0,
                "tokens_used": 0,
            })

        return steps

    @staticmethod
    def _looks_truncated(answer: str) -> bool:
        """Heuristic: did the agent produce a forced/truncated conclusion?"""
        if not answer:
            return False
        markers = ("reached the maximum number of steps", "loop was detected",
                   "unable to force conclusion", "maximum steps")
        lowered = answer.lower()
        return any(m in lowered for m in markers)

    def _error_result(
        self, task: str, message: str, start: float
    ) -> AgentExecutionResult:
        """Build a clean error result."""
        elapsed_ms = (time.perf_counter() - start) * 1000
        return AgentExecutionResult(
            final_output=message,
            status="error",
            steps=[{
                "step_number": 0,
                "action": "error",
                "thought": "",
                "observation": message,
                "tool_name": "",
                "tool_input": {},
                "tool_output": message,
                "elapsed_ms": 0.0,
                "tokens_used": 0,
            }],
            loop_detected=False,
            cost_usd=0.0,
            elapsed_ms=round(elapsed_ms, 2),
        )


__all__ = ["AgentExecutor", "AgentExecutionResult", "AGENT_TYPE_MAP"]
