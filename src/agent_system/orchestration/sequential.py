"""
Sequential orchestrator - runs agents in a pipeline.

Each agent processes the output of the previous agent, forming a
processing chain. Useful for multi-step workflows where each step
depends on the previous one.
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class OrchestrationResult:
    """Result from an orchestration run."""
    run_id: str
    task: str
    outputs: list[dict]  # Per-agent outputs
    final_answer: str
    total_steps: int
    execution_time_ms: float
    success: bool
    error: str | None = None


class SequentialOrchestrator:
    """Pipeline orchestrator that runs agents in sequence.

    Each agent in the pipeline receives the output of the previous agent
    plus the original task context. Suitable for data processing pipelines,
    review chains, and step-by-step reasoning with specialized agents.

    Args:
        agents: Ordered list of agent instances (each must have a `run` method).
        pass_full_context: If True, pass all previous outputs to each agent.
                          If False, pass only the immediate previous output.
        max_timeout: Maximum total execution time in seconds.
    """

    def __init__(
        self,
        agents: list = None,
        pass_full_context: bool = False,
        max_timeout: float = 300.0,
    ):
        self.agents = agents or []
        self.pass_full_context = pass_full_context
        self.max_timeout = max_timeout

    def add_agent(self, agent, position: int | None = None) -> None:
        """Add an agent to the pipeline.

        Args:
            agent: The agent instance to add.
            position: Position to insert at (None = append to end).
        """
        if position is not None:
            self.agents.insert(position, agent)
        else:
            self.agents.append(agent)

    def remove_agent(self, index: int) -> None:
        """Remove an agent from the pipeline by index."""
        self.agents.pop(index)

    async def run(self, task: str, **kwargs) -> OrchestrationResult:
        """Execute the sequential pipeline.

        Args:
            task: The initial task description.
            **kwargs: Additional context.

        Returns:
            OrchestrationResult with all agent outputs and final answer.
        """
        run_id = str(uuid.uuid4())[:8]
        start_time = time.perf_counter()
        all_outputs: list[dict] = []
        total_steps = 0
        current_input = task

        try:
            for i, agent in enumerate(self.agents):
                agent_name = getattr(agent, "__class__", type(agent)).__name__

                if self.pass_full_context and i > 0:
                    # Build context from all previous outputs
                    context = (
                        f"Original Task: {task}\n\n"
                        "Previous steps:\n"
                    )
                    for prev in all_outputs:
                        context += f"- Agent {prev['position']}: {prev.get('answer', '')[:300]}\n"
                    context += f"\nCurrent task (for step {i + 1}): {current_input}"
                    agent_input = context
                else:
                    agent_input = current_input

                try:
                    result = await asyncio.wait_for(
                        agent.run(agent_input),
                        timeout=self.max_timeout / max(len(self.agents), 1),
                    )
                except asyncio.TimeoutError:
                    logger.warning("Agent %d (%s) timed out", i, agent_name)
                    all_outputs.append({
                        "position": i,
                        "agent": agent_name,
                        "answer": f"Agent timed out at step {i}.",
                        "steps": 0,
                        "error": "Timeout",
                    })
                    return OrchestrationResult(
                        run_id=run_id, task=task, outputs=all_outputs,
                        final_answer="Pipeline incomplete: agent timeout.",
                        total_steps=total_steps,
                        execution_time_ms=(time.perf_counter() - start_time) * 1000,
                        success=False, error="Agent timeout",
                    )

                output = {
                    "position": i,
                    "agent": agent_name,
                    "answer": result.answer if hasattr(result, "answer") else str(result),
                    "steps": result.steps if hasattr(result, "steps") else 1,
                    "tools_used": result.tools_used if hasattr(result, "tools_used") else [],
                    "success": getattr(result, "success", True),
                    "error": getattr(result, "error", None),
                }
                all_outputs.append(output)
                total_steps += output["steps"]

                # Pass output to next agent
                current_input = output["answer"]

                if not output.get("success"):
                    logger.warning("Agent %d (%s) failed: %s", i, agent_name, output.get("error"))
                    break

            # Final answer from the last agent
            final_answer = all_outputs[-1]["answer"] if all_outputs else task

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
            logger.exception("Sequential orchestration failed")
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

    def __len__(self) -> int:
        return len(self.agents)

    def __repr__(self) -> str:
        names = [type(a).__name__ for a in self.agents]
        return f"SequentialOrchestrator({' -> '.join(names)})"
