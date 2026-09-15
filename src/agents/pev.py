"""Plan-Execute-Verify (PEV) state machine.

The production-grade agent orchestration pattern from the architecture doc
(section 2.3). An explicit state machine that:

1. **Plan** — decompose the task into a step-by-step plan.
2. **Execute** — run each step (tool call or LLM reasoning), tracking cost/tokens.
3. **Verify** — independently validate the output (NOT LLM self-assessment).

The whole loop is wrapped in a ``Harness`` that enforces hard limits
(max steps, cost budget, token budget, loop detection, tool approval).

States:
    PLANNING -> EXECUTING -> VERIFYING -> DONE
                    ^              |
                    |  (replan)    |  (fail -> replan or abort)
                    +--------------+
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from src.harness.guard import Harness, HarnessConfig, HarnessViolation
from src.harness.verify import Verifier, VerificationResult

logger = logging.getLogger(__name__)


class PEVState(str, Enum):
    PLANNING = "planning"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    DONE = "done"
    FAILED = "failed"


@dataclass
class PEVStep:
    """A single step in the plan."""

    step_id: int
    description: str
    tool: str = ""
    args: dict = field(default_factory=dict)
    result: Any = None
    success: bool = False
    error: str = ""


@dataclass
class PEVResult:
    """Result of a PEV run."""

    final_output: str
    status: str  # completed | max_steps_reached | error | failed_verification
    steps: list[dict] = field(default_factory=list)
    loop_detected: bool = False
    cost_usd: float = 0.0
    elapsed_ms: float = 0.0
    verification: Optional[dict] = None


class PEVAgent:
    """Plan-Execute-Verify agent with Harness enforcement.

    Args:
        llm: LangChain-compatible LLM (used by planner + executor reasoning).
        tools: Mapping of tool name -> callable(**kwargs) (or BaseTool).
        verifier: An independent Verifier instance.
        harness: A configured Harness (built from HarnessConfig if None).
        max_replans: Maximum replan cycles before abort.
    """

    def __init__(
        self,
        llm: Any = None,
        tools: dict[str, Any] | None = None,
        verifier: Verifier | None = None,
        harness: Harness | None = None,
        max_replans: int = 2,
    ):
        self.llm = llm
        self.tools = tools or {}
        self.verifier = verifier
        self.harness = harness or Harness(HarnessConfig())
        self.max_replans = max_replans

    # ------------------------------------------------------------------
    # Main entry
    # ------------------------------------------------------------------

    async def run(self, task: str) -> PEVResult:
        """Run the PEV state machine on a task."""
        start = time.perf_counter()
        state = PEVState.PLANNING
        plan: list[PEVStep] = []
        replans = 0
        steps_trace: list[dict] = []

        try:
            # ---- PLAN ----
            plan = await self._plan(task)
            steps_trace.append(self._trace("plan", f"Generated {len(plan)} step plan", plan=[s.description for s in plan]))

            # ---- EXECUTE + VERIFY loop ----
            while state in (PEVState.EXECUTING, PEVState.VERIFYING, PEVState.PLANNING):
                self.harness.check_step(len(steps_trace))
                state = PEVState.EXECUTING

                # Execute each step
                for step in plan:
                    self.harness.check_step(len(steps_trace))
                    if step.tool and step.tool in self.tools:
                        self.harness.check_tool(step.tool)
                        step.result, step.error = await self._call_tool(step.tool, step.args)
                        step.success = step.error == ""
                    else:
                        # No tool: pure reasoning step via LLM (if present)
                        if self.llm is not None:
                            step.result, step.error = await self._reason(step.description)
                            step.success = step.error == ""
                        else:
                            step.success = True

                    steps_trace.append(self._trace(
                        "execute",
                        f"Step {step.step_id}: {step.description}",
                        tool_name=step.tool,
                        tool_output=str(step.result)[:500] if step.result else "",
                        success=step.success,
                    ))

                # ---- VERIFY ----
                state = PEVState.VERIFYING
                final_output = self._synthesize(plan, task)
                verification = self._verify(final_output, task)

                if verification.passed:
                    state = PEVState.DONE
                    break
                else:
                    steps_trace.append(self._trace("verify", verification.reason, passed=False))
                    if replans < self.max_replans:
                        replans += 1
                        plan = await self._replan(task, plan, verification.reason)
                        steps_trace.append(self._trace("replan", f"Replanned (attempt {replans})"))
                        state = PEVState.PLANNING
                    else:
                        state = PEVState.FAILED
                        break

            if state == PEVState.DONE:
                return PEVResult(
                    final_output=final_output,
                    status="completed",
                    steps=steps_trace,
                    cost_usd=round(self.harness.cumulative_cost, 6),
                    elapsed_ms=(time.perf_counter() - start) * 1000,
                    verification={"passed": True, "reason": verification.reason},
                )
            else:
                return PEVResult(
                    final_output=final_output,
                    status="failed_verification",
                    steps=steps_trace,
                    cost_usd=round(self.harness.cumulative_cost, 6),
                    elapsed_ms=(time.perf_counter() - start) * 1000,
                    verification={"passed": False, "reason": verification.reason},
                )

        except HarnessViolation as exc:
            return PEVResult(
                final_output=f"Harness violation: {exc.reason}",
                status="max_steps_reached" if "step" in exc.reason.lower() else "error",
                steps=steps_trace,
                cost_usd=round(self.harness.cumulative_cost, 6),
                elapsed_ms=(time.perf_counter() - start) * 1000,
            )
        except Exception as exc:  # noqa: BLE001 - surface as clean result
            logger.exception("PEV execution failed")
            return PEVResult(
                final_output=f"PEV execution error: {exc}",
                status="error",
                steps=steps_trace,
                cost_usd=round(self.harness.cumulative_cost, 6),
                elapsed_ms=(time.perf_counter() - start) * 1000,
            )

    # ------------------------------------------------------------------
    # Phase helpers
    # ------------------------------------------------------------------

    async def _plan(self, task: str) -> list[PEVStep]:
        """Decompose the task into steps (LLM if available, else heuristic)."""
        if self.llm is not None:
            prompt = (
                "You are a planning agent. Break the task into a numbered list "
                "of concrete, executable steps. Each step should be self-contained.\n\n"
                f"Task: {task}\n\nSteps:"
            )
            try:
                response = await self.llm.ainvoke([{"role": "user", "content": prompt}])
                text = response.content if hasattr(response, "content") else str(response)
                steps = self._parse_plan(text)
                if steps:
                    return steps
            except Exception as exc:  # noqa: BLE001
                logger.warning("LLM planning failed (%s), using heuristic", exc)

        return self._heuristic_plan(task)

    async def _replan(self, task: str, plan: list[PEVStep], reason: str) -> list[PEVStep]:
        """Replan based on verification failure."""
        if self.llm is not None:
            prompt = (
                "The previous plan failed verification. Adjust the steps to "
                f"address this issue: {reason}\n\n"
                f"Task: {task}\n\nNew steps:"
            )
            try:
                response = await self.llm.ainvoke([{"role": "user", "content": prompt}])
                text = response.content if hasattr(response, "content") else str(response)
                steps = self._parse_plan(text)
                if steps:
                    return steps
            except Exception:  # noqa: BLE001
                pass
        return plan  # keep original plan on replan failure

    async def _reason(self, description: str) -> tuple[Any, str]:
        """Perform a pure-reasoning step via LLM."""
        try:
            response = await self.llm.ainvoke([{"role": "user", "content": description}])
            return (response.content if hasattr(response, "content") else str(response)), ""
        except Exception as exc:  # noqa: BLE001
            return None, str(exc)

    async def _call_tool(self, tool_name: str, args: dict) -> tuple[Any, str]:
        """Call a tool (BaseTool or plain callable)."""
        try:
            tool = self.tools[tool_name]
            if hasattr(tool, "execute"):
                result = await tool.execute(**args)
                if hasattr(result, "data"):
                    return result.data, (result.error or "")
                return result, ""
            # plain callable
            result = tool(**args)
            if hasattr(result, "__await__"):
                result = await result
            return result, ""
        except Exception as exc:  # noqa: BLE001
            return None, str(exc)

    def _verify(self, output: str, task: str) -> VerificationResult:
        """Run the independent verifier."""
        if self.verifier is None:
            return VerificationResult(True, "no verifier configured")
        return self.verifier.verify(output, {"task": task})

    def _synthesize(self, plan: list[PEVStep], task: str) -> str:
        """Synthesize the final output from step results."""
        parts = [f"Task: {task}", ""]
        for step in plan:
            status = "OK" if step.success else "FAIL"
            parts.append(f"Step {step.step_id} ({status}): {step.description}")
            if step.result:
                parts.append(f"  -> {str(step.result)[:300]}")
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _heuristic_plan(task: str) -> list[PEVStep]:
        """Deterministic plan: a single synthesis step."""
        return [PEVStep(step_id=1, description=task)]

    @staticmethod
    def _parse_plan(text: str) -> list[PEVStep]:
        """Parse a numbered plan text into steps."""
        import re
        steps = []
        for match in re.finditer(r"^\s*(?:\d+[\.\)]|Step\s*\d+[:\.])\s*(.+)", text, re.MULTILINE):
            desc = match.group(1).strip()
            if desc:
                steps.append(PEVStep(step_id=len(steps) + 1, description=desc))
        return steps

    @staticmethod
    def _trace(action: str, content: str, **extra) -> dict:
        return {"action": action, "observation": content, **extra}
