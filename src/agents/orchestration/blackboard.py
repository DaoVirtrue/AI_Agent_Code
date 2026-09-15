"""
Blackboard orchestrator with opportunistic collaboration.

Agents autonomously read from and write to a shared blackboard,
collaborating on a task without central coordination. Each agent
contributes when it has relevant capabilities.
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any

from src.memory.blackboard import SharedBlackboard

logger = logging.getLogger(__name__)


@dataclass
class OrchestrationResult:
    """Result from an orchestration run."""
    run_id: str
    task: str
    outputs: list[dict]
    final_answer: str
    total_steps: int
    execution_time_ms: float
    success: bool
    error: str | None = None


class BlackboardOrchestrator:
    """Orchestrates agents via a shared blackboard for opportunistic collaboration.

    Agents write their findings to the blackboard and read others' contributions.
    A solver agent periodically checks if the task can be completed.

    Args:
        agents: List of agent instances.
        blackboard: SharedBlackboard instance.
        solver_llm: LLM for the solver agent that synthesizes the final answer.
        max_cycles: Maximum number of read-write cycles.
        idle_timeout: Seconds of inactivity before forcing conclusion.
    """

    def __init__(
        self,
        agents: list = None,
        blackboard: SharedBlackboard | None = None,
        solver_llm=None,
        max_cycles: int = 10,
        idle_timeout: float = 60.0,
    ):
        self.agents = agents or []
        self.blackboard = blackboard or SharedBlackboard()
        self.solver_llm = solver_llm
        self.max_cycles = max_cycles
        self.idle_timeout = idle_timeout

    async def run(self, task: str, **kwargs) -> OrchestrationResult:
        """Execute blackboard-based collaboration.

        Args:
            task: The task description.
            **kwargs: Additional context.

        Returns:
            OrchestrationResult with final answer.
        """
        run_id = str(uuid.uuid4())[:8]
        start_time = time.perf_counter()
        all_outputs: list[dict] = []
        total_steps = 0

        try:
            # Seed the blackboard with the task
            await self.blackboard.write("task", "description", task)
            await self.blackboard.write("status", "complete", False)
            await self.blackboard.write("status", "cycle", 0)

            for cycle in range(self.max_cycles):
                # Each agent reads the blackboard and contributes
                contributions_made = 0

                for agent in self.agents:
                    agent_name = type(agent).__name__

                    # Build context from blackboard
                    all_keys = await self._get_relevant_keys()
                    context = await self._build_context(task, all_keys)

                    if context is None:
                        continue

                    try:
                        result = await agent.run(context)
                        answer = result.answer if hasattr(result, "answer") else str(result)
                        steps = result.steps if hasattr(result, "steps") else 1
                    except Exception as e:
                        logger.warning("Agent '%s' failed in cycle %d: %s", agent_name, cycle, e)
                        continue

                    # Write contribution to blackboard
                    contribution_key = f"agent_{agent_name}_{cycle}"
                    await self.blackboard.write("contributions", contribution_key, {
                        "agent": agent_name,
                        "cycle": cycle,
                        "content": answer,
                        "timestamp": time.time(),
                    })
                    contributions_made += 1
                    total_steps += steps

                    all_outputs.append({
                        "cycle": cycle,
                        "agent": agent_name,
                        "answer": answer,
                        "steps": steps,
                    })

                # Check if complete
                await self.blackboard.write("status", "cycle", cycle + 1)

                # Solver checks if we can conclude
                if contributions_made == 0:
                    # Check for idle timeout
                    elapsed = time.perf_counter() - start_time
                    if elapsed > self.idle_timeout or cycle >= self.max_cycles - 1:
                        break

            # Get all contributions and synthesize
            all_contributions = await self.blackboard.read("contributions", list) if False else []

            try:
                contrib_keys = await self.blackboard.list_namespace("contributions")
            except Exception:
                contrib_keys = []

            contributions = []
            for key in contrib_keys:
                try:
                    data, _ = await self.blackboard.read_with_meta("contributions", key)
                    contributions.append(data)
                except Exception:
                    pass

            final_answer = await self._synthesize_with_solver(task, contributions)

            await self.blackboard.write("status", "complete", True)

            elapsed = (time.perf_counter() - start_time) * 1000
            return OrchestrationResult(
                run_id=run_id,
                task=task,
                outputs=all_outputs,
                final_answer=final_answer,
                total_steps=total_steps,
                execution_time_ms=elapsed,
                success=True,
            )

        except Exception as e:
            elapsed = (time.perf_counter() - start_time) * 1000
            logger.exception("Blackboard orchestration failed")
            return OrchestrationResult(
                run_id=run_id,
                task=task,
                outputs=all_outputs,
                final_answer="",
                total_steps=total_steps,
                execution_time_ms=elapsed,
                success=False,
                error=str(e),
            )

    async def _get_relevant_keys(self) -> list[str]:
        """Get all relevant keys from the blackboard namespaces."""
        keys = []
        for ns in ["task", "contributions", "status", "findings"]:
            try:
                ns_keys = await self.blackboard.list_namespace(ns)
                keys.extend(f"{ns}/{k}" for k in ns_keys)
            except Exception:
                pass
        return keys

    async def _build_context(self, task: str, keys: list[str]) -> str | None:
        """Build context for an agent from the blackboard."""
        parts = [f"Task: {task}\n\nBlackboard contents:"]

        for key in keys[:20]:  # Limit context size
            try:
                ns, k = key.split("/", 1)
                value = await self.blackboard.read(ns, k)
                parts.append(f"[{key}]: {str(value)[:300]}")
            except Exception:
                pass

        return "\n".join(parts) if len(parts) > 1 else None

    async def _synthesize_with_solver(self, task: str, contributions: list) -> str:
        """Synthesize contributions into a final answer."""
        if not contributions:
            if self.solver_llm:
                try:
                    response = await self.solver_llm.ainvoke(
                        [{"role": "user", "content": task}]
                    )
                    return response.content if hasattr(response, "content") else str(response)
                except Exception:
                    pass
            return "No contributions were made during the session."

        contributions_text = "\n---\n".join(
            f"{c.get('agent', '?')} (cycle {c.get('cycle', '?')}): {c.get('content', '')[:400]}"
            for c in contributions
        )

        if self.solver_llm:
            prompt = (
                "Synthesize the following agent contributions into a final answer.\n\n"
                f"Task: {task}\n\n"
                f"Contributions:\n{contributions_text}\n\n"
                "Final synthesis:"
            )
            try:
                response = await self.solver_llm.ainvoke([{"role": "user", "content": prompt}])
                return response.content if hasattr(response, "content") else str(response)
            except Exception:
                pass

        # Fallback
        return f"Synthesis of {len(contributions)} contributions:\n\n" + contributions_text

    def __repr__(self) -> str:
        return f"BlackboardOrchestrator(agents={len(self.agents)}, cycles={self.max_cycles})"
