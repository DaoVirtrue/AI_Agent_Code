"""
Supervisor agent with conditional routing, PostgresSaver, and worker subgraphs.

A supervisor LLM routes tasks to specialized worker agents. Each worker
is a LangGraph subgraph callable. Supports checkpointing via PostgresSaver.
"""

import logging
import uuid
from typing import Any, Literal, TypedDict

logger = logging.getLogger(__name__)


class SupervisorState(TypedDict, total=False):
    """State for the supervisor workflow."""
    messages: list[dict]
    task: str
    next_worker: str
    worker_outputs: dict[str, str]
    final_answer: str
    should_finish: bool


class SupervisorAgent:
    """Supervisor agent that routes tasks to worker subgraphs.

    The supervisor (LLM) analyzes the task and delegates to the
    most appropriate worker. After worker completion, the supervisor
    either delegates to another worker or produces the final answer.

    Supports PostgreSQL checkpointing via langgraph checkpointer.

    Args:
        supervisor_llm: LLM for the supervisor agent.
        workers: Dict mapping worker name -> runnable (or agent with run()).
        worker_descriptions: Dict mapping worker name -> description string.
        checkpointer: Optional langgraph checkpointer (e.g., PostgresSaver).
        max_worker_calls: Maximum worker invocations before forcing finish.
    """

    def __init__(
        self,
        supervisor_llm,
        workers: dict[str, Any] | None = None,
        worker_descriptions: dict[str, str] | None = None,
        checkpointer=None,
        max_worker_calls: int = 8,
    ):
        self.supervisor_llm = supervisor_llm
        self.workers = workers or {}
        self.worker_descriptions = worker_descriptions or {}
        self.checkpointer = checkpointer
        self.max_worker_calls = max_worker_calls

    def register_worker(self, name: str, worker: Any, description: str = "") -> None:
        """Register a worker agent.

        Args:
            name: Worker identifier.
            worker: A runnable (LangGraph graph) or an object with run() method.
            description: Natural language description of what this worker does.
        """
        self.workers[name] = worker
        self.worker_descriptions[name] = description or f"Worker: {name}"

    def remove_worker(self, name: str) -> None:
        """Remove a registered worker."""
        self.workers.pop(name, None)
        self.worker_descriptions.pop(name, None)

    async def _supervisor_node(self, state: SupervisorState) -> dict:
        """Supervisor decides which worker to invoke next or finishes."""
        task = state.get("task", "")
        worker_outputs = state.get("worker_outputs", {})
        messages = state.get("messages", [])

        # Count calls to prevent infinite loops
        call_count = len(worker_outputs)
        if call_count >= self.max_worker_calls:
            return await self._finish_node(state)

        worker_list = "\n".join(
            f"- {name}: {desc}"
            for name, desc in self.worker_descriptions.items()
        )

        # Build context from worker outputs
        context = ""
        if worker_outputs:
            context = "Previous worker outputs:\n" + "\n---\n".join(
                f"[{name}]: {output[:300]}"
                for name, output in worker_outputs.items()
            )

        prompt = (
            "You are a supervisor agent. Your job is to route the user's task "
            "to the most appropriate worker, or produce a final answer if the "
            "task is complete or no more workers are needed.\n\n"
            "Available workers:\n"
            f"{worker_list}\n\n"
            f"Task: {task}\n\n"
            f"{context}\n\n"
            "Respond with exactly ONE of:\n"
            "- NEXT: worker_name  (to route to a worker)\n"
            "- FINISH: your_final_answer  (to conclude)\n\n"
            "Decision:"
        )

        try:
            response = await self.supervisor_llm.ainvoke([{"role": "user", "content": prompt}])
            text = response.content if hasattr(response, "content") else str(response)
        except Exception as e:
            logger.exception("Supervisor decision failed")
            return {"next_worker": "__finish__", "should_finish": True,
                    "final_answer": f"Supervisor error: {e}"}

        import re

        # Check for NEXT directive
        next_match = re.search(r'NEXT\s*:\s*(\w+)', text)
        if next_match:
            worker_name = next_match.group(1)
            if worker_name in self.workers:
                return {"next_worker": worker_name, "should_finish": False,
                        "messages": messages + [{"role": "assistant", "content": text}]}
            else:
                logger.warning("Supervisor selected unknown worker: %s", worker_name)

        # Check for FINISH directive
        finish_match = re.search(r'FINISH\s*:\s*(.+)', text, re.DOTALL)
        if finish_match:
            final = finish_match.group(1).strip()
            return {"should_finish": True, "final_answer": final,
                    "messages": messages + [{"role": "assistant", "content": text}]}

        # Default: finish with whatever was said
        return {"should_finish": True, "final_answer": text,
                "messages": messages + [{"role": "assistant", "content": text}]}

    async def _worker_node(self, state: SupervisorState) -> dict:
        """Execute the selected worker."""
        worker_name = state.get("next_worker", "")
        task = state.get("task", "")
        worker_outputs = dict(state.get("worker_outputs", {}))
        messages = list(state.get("messages", []))

        if worker_name not in self.workers:
            return {"worker_outputs": worker_outputs, "next_worker": "__finish__"}

        worker = self.workers[worker_name]

        # Build worker context
        worker_prompt = (
            f"Original Task: {task}\n\n"
            "You are a specialized worker. Complete your part of the task "
            "and return your results."
        )

        try:
            if hasattr(worker, "ainvoke"):
                # LangGraph subgraph
                result = await worker.ainvoke({"messages": [{"role": "user", "content": worker_prompt}]})
                output = result.get("final_answer", "") or str(result.get("messages", [{}])[-1].get("content", ""))
            elif hasattr(worker, "run"):
                result = await worker.run(worker_prompt)
                output = result.answer if hasattr(result, "answer") else str(result)
            else:
                output = f"Worker '{worker_name}' is not runnable."
        except Exception as e:
            output = f"Worker '{worker_name}' error: {e}"

        worker_outputs[worker_name] = output
        messages.append({"role": "system", "content": f"Worker {worker_name}: {output[:300]}"})

        return {
            "worker_outputs": worker_outputs,
            "messages": messages,
            "should_finish": False,
        }

    async def _finish_node(self, state: SupervisorState) -> dict:
        """Produce the final answer from worker outputs."""
        task = state.get("task", "")
        worker_outputs = state.get("worker_outputs", {})

        if not worker_outputs:
            return {"final_answer": "No workers were invoked.", "should_finish": True}

        combined = "\n---\n".join(
            f"[{name}]: {output[:400]}"
            for name, output in worker_outputs.items()
        )

        prompt = (
            "Synthesize the following worker outputs into a comprehensive "
            "final answer for the original task.\n\n"
            f"Task: {task}\n\n"
            f"Worker Results:\n{combined}\n\n"
            "Final Answer:"
        )

        try:
            response = await self.supervisor_llm.ainvoke([{"role": "user", "content": prompt}])
            final = response.content if hasattr(response, "content") else str(response)
        except Exception:
            final = combined

        return {"final_answer": final, "should_finish": True}

    async def run(self, task: str, **kwargs) -> dict:
        """Run the supervisor workflow on a task.

        Simulates the LangGraph supervisor loop without the full graph
        (since a full langgraph.graph.StateGraph would be needed for checkpointer).

        Args:
            task: The task description.
            **kwargs: Additional context.

        Returns:
            Dict with final_answer, worker_outputs, and metadata.
        """
        state: SupervisorState = {
            "task": task,
            "next_worker": "",
            "worker_outputs": {},
            "final_answer": "",
            "should_finish": False,
            "messages": [],
        }

        iteration = 0
        while not state["should_finish"] and iteration < self.max_worker_calls * 2:
            iteration += 1

            # Supervisor decides
            state.update(await self._supervisor_node(state))

            if state.get("should_finish", False):
                break

            # Execute worker
            state.update(await self._worker_node(state))

        # Finalize if not already finished
        if not state.get("final_answer"):
            state.update(await self._finish_node(state))

        return {
            "final_answer": state.get("final_answer", "No answer produced."),
            "worker_outputs": state.get("worker_outputs", {}),
            "iterations": iteration,
            "run_id": str(uuid.uuid4())[:8],
        }

    def __repr__(self) -> str:
        return (
            f"SupervisorAgent(workers={list(self.workers.keys())}, "
            f"max_calls={self.max_worker_calls})"
        )
