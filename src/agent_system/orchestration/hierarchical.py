"""
Hierarchical orchestrator with supervisor-worker pattern using LangGraph subgraphs.

A supervisor agent delegates subtasks to specialized worker agents and
synthesizes their outputs into a final answer.
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any, TypedDict

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


@dataclass
class WorkerSpec:
    """Specification for a worker agent."""
    name: str
    agent: Any  # Agent instance with run() method
    description: str
    capabilities: list[str]  # Keywords describing what this worker handles


class HierarchicalOrchestrator:
    """Supervisor-worker orchestrator with LangGraph subgraphs.

    The supervisor LLM analyzes the task, decomposes it into subtasks,
    assigns them to specialized workers, and synthesizes their outputs.

    Args:
        supervisor_llm: LLM for the supervisor agent.
        workers: List of WorkerSpec instances.
        max_delegations: Maximum number of worker delegations.
    """

    def __init__(
        self,
        supervisor_llm,
        workers: list[WorkerSpec] | None = None,
        max_delegations: int = 6,
    ):
        self.supervisor_llm = supervisor_llm
        self.workers: dict[str, WorkerSpec] = {}
        self.max_delegations = max_delegations

        if workers:
            for w in workers:
                self.add_worker(w)

    def add_worker(self, spec: WorkerSpec) -> None:
        """Register a worker agent.

        Args:
            spec: WorkerSpec defining the worker.
        """
        if spec.name in self.workers:
            raise ValueError(f"Worker '{spec.name}' already registered.")
        self.workers[spec.name] = spec

    def remove_worker(self, name: str) -> None:
        """Remove a worker by name."""
        self.workers.pop(name, None)

    async def run(self, task: str, **kwargs) -> OrchestrationResult:
        """Execute the hierarchical orchestration.

        1. Supervisor analyzes task and creates subtasks
        2. Delegates to appropriate workers
        3. Synthesizes worker outputs into final answer

        Args:
            task: The overall task description.

        Returns:
            OrchestrationResult with worker outputs and final synthesis.
        """
        run_id = str(uuid.uuid4())[:8]
        start_time = time.perf_counter()
        outputs: list[dict] = []
        total_steps = 0

        try:
            # Step 1: Supervisor decomposes the task
            subtasks = await self._decompose_task(task)

            if not subtasks:
                # Fallback: single worker or supervisor handles directly
                return await self._fallback_direct(task, run_id, start_time)

            # Step 2: Assign and execute subtasks with workers
            for i, subtask in enumerate(subtasks[:self.max_delegations]):
                worker_name = await self._select_worker(subtask, task)

                if worker_name and worker_name in self.workers:
                    worker_spec = self.workers[worker_name]
                    worker_input = (
                        f"Context - Original Task: {task}\n"
                        f"Subtask ({i + 1}/{min(len(subtasks), self.max_delegations)}): "
                        f"{subtask}"
                    )

                    try:
                        worker_result = await worker_spec.agent.run(worker_input)
                    except Exception as e:
                        logger.warning("Worker '%s' failed: %s", worker_name, e)
                        outputs.append({
                            "position": i,
                            "worker": worker_name,
                            "subtask": subtask,
                            "answer": f"Worker error: {e}",
                            "success": False,
                            "error": str(e),
                        })
                        continue

                    output = {
                        "position": i,
                        "worker": worker_name,
                        "subtask": subtask,
                        "answer": worker_result.answer if hasattr(worker_result, "answer") else str(worker_result),
                        "steps": worker_result.steps if hasattr(worker_result, "steps") else 1,
                        "success": getattr(worker_result, "success", True),
                    }
                    outputs.append(output)
                    total_steps += output["steps"]
                else:
                    outputs.append({
                        "position": i,
                        "worker": "unknown",
                        "subtask": subtask,
                        "answer": f"No suitable worker found for: {subtask}",
                        "success": False,
                    })

            # Step 3: Supervisory synthesis
            final_answer = await self._synthesize(task, outputs)

            elapsed = (time.perf_counter() - start_time) * 1000
            return OrchestrationResult(
                run_id=run_id,
                task=task,
                outputs=outputs,
                final_answer=final_answer,
                total_steps=total_steps,
                execution_time_ms=elapsed,
                success=all(o.get("success", False) for o in outputs) if outputs else True,
            )

        except Exception as e:
            elapsed = (time.perf_counter() - start_time) * 1000
            logger.exception("Hierarchical orchestration failed")
            return OrchestrationResult(
                run_id=run_id,
                task=task,
                outputs=outputs,
                final_answer="",
                total_steps=total_steps,
                execution_time_ms=elapsed,
                success=False,
                error=str(e),
            )

    # ------------------------------------------------------------------
    # Supervisor logic
    # ------------------------------------------------------------------

    async def _decompose_task(self, task: str) -> list[str]:
        """Use the supervisor LLM to decompose a task into subtasks.

        Args:
            task: The overall task.

        Returns:
            List of subtask descriptions.
        """
        worker_list = "\n".join(
            f"- {name}: {spec.description} (capabilities: {', '.join(spec.capabilities)})"
            for name, spec in self.workers.items()
        )

        prompt = (
            "You are a supervisor agent. Decompose the following task into "
            "smaller subtasks that can be handled by specialized workers.\n\n"
            "Available workers:\n"
            f"{worker_list}\n\n"
            f"Task: {task}\n\n"
            "Break this down into a numbered list of subtasks. "
            "Each subtask should be a clear, actionable piece that one worker can handle. "
            "Maximum 5 subtasks:"
        )

        try:
            response = await self.supervisor_llm.ainvoke([{"role": "user", "content": prompt}])
            text = response.content if hasattr(response, "content") else str(response)
        except Exception as e:
            logger.warning("Task decomposition failed: %s", e)
            return [task]  # Fallback: single subtask

        # Parse numbered list
        import re
        subtasks = re.findall(r'\d+[\.\)\s-]+(.+)', text)
        if not subtasks:
            return [task]

        return [s.strip() for s in subtasks if s.strip()]

    async def _select_worker(self, subtask: str, context: str) -> str | None:
        """Select the best worker for a subtask.

        Uses keyword matching between the subtask and worker capabilities.

        Args:
            subtask: The subtask description.
            context: The original task for context.

        Returns:
            Worker name or None if no suitable worker found.
        """
        subtask_lower = subtask.lower()

        # Score each worker by capability keyword matches
        scored = []
        for name, spec in self.workers.items():
            score = 0
            for capability in spec.capabilities:
                if capability.lower() in subtask_lower:
                    score += 2
                # Partial match
                for word in capability.lower().split():
                    if word in subtask_lower:
                        score += 1

            # Description match
            if any(word in subtask_lower for word in spec.description.lower().split()):
                score += 1

            if score > 0:
                scored.append((score, name))

        if not scored:
            # Return first worker as default
            return next(iter(self.workers.keys())) if self.workers else None

        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1]

    async def _synthesize(self, task: str, outputs: list[dict]) -> str:
        """Synthesize worker outputs into a final answer.

        Args:
            task: The original task.
            outputs: Worker output dicts.

        Returns:
            Synthesized final answer string.
        """
        worker_results = "\n".join(
            f"Worker {o.get('worker', '?')}: {o.get('answer', '')[:300]}"
            for o in outputs
        )

        prompt = (
            "You are a supervisor agent. Synthesize the following worker outputs "
            "into a comprehensive final answer for the original task.\n\n"
            f"Original Task: {task}\n\n"
            "Worker Results:\n"
            f"{worker_results}\n\n"
            "Provide a well-structured, unified final answer that incorporates "
            "all the worker findings:"
        )

        try:
            response = await self.supervisor_llm.ainvoke([{"role": "user", "content": prompt}])
            return response.content if hasattr(response, "content") else str(response)
        except Exception as e:
            # Fallback: concatenate worker outputs
            return "\n\n".join(
                f"[{o.get('worker', '?')}]: {o.get('answer', '')}"
                for o in outputs
            )

    async def _fallback_direct(self, task: str, run_id: str, start_time: float) -> OrchestrationResult:
        """Fallback: supervisor handles the task directly."""
        try:
            response = await self.supervisor_llm.ainvoke([{"role": "user", "content": task}])
            answer = response.content if hasattr(response, "content") else str(response)
        except Exception as e:
            answer = f"Failed: {e}"

        return OrchestrationResult(
            run_id=run_id,
            task=task,
            outputs=[{"position": 0, "worker": "supervisor_direct", "answer": answer, "success": True}],
            final_answer=answer,
            total_steps=1,
            execution_time_ms=(time.perf_counter() - start_time) * 1000,
            success=True,
        )

    def __repr__(self) -> str:
        return (
            f"HierarchicalOrchestrator(workers={list(self.workers.keys())}, "
            f"max_delegations={self.max_delegations})"
        )
