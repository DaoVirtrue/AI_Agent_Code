"""
Swarm orchestrator - OpenAI-style stateless handoff pattern.

Agents hand off tasks to each other based on routines and instructions,
without a centralized graph or shared state machine.
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class HandoffTarget(str, Enum):
    """Handoff targets for swarm agents."""
    SELF = "self"  # Continue with current agent

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
class SwarmAgent:
    """A stateless agent in the swarm with routing rules.

    Each agent has:
    - name: Identifier
    - agent: The actual agent instance (with run() method)
    - instructions: System-level instructions describing its role
    - handoffs: Dict mapping agent names to handoff conditions/descriptions
    """
    name: str
    agent: Any
    instructions: str
    handoffs: dict[str, str] = field(default_factory=dict)  # target_name -> description


class SwarmOrchestrator:
    """OpenAI-style stateless handoff orchestration.

    Agents pass tasks between themselves based on explicit handoff
    instructions. Each agent decides whether to respond directly or
    hand off to another agent.

    Args:
        agents: List of SwarmAgent instances.
        max_handoffs: Maximum number of handoffs before forcing a response.
        context_window: Number of previous interactions to include in context.
    """

    def __init__(
        self,
        agents: list[SwarmAgent] | None = None,
        max_handoffs: int = 10,
        context_window: int = 5,
    ):
        self.agents: dict[str, SwarmAgent] = {}
        self.max_handoffs = max_handoffs
        self.context_window = context_window

        if agents:
            for a in agents:
                self.add_agent(a)

    def add_agent(self, swarm_agent: SwarmAgent) -> None:
        """Register a swarm agent."""
        if swarm_agent.name in self.agents:
            raise ValueError(f"Agent '{swarm_agent.name}' already registered.")
        self.agents[swarm_agent.name] = swarm_agent

    def add_handoff(self, from_agent: str, to_agent: str, description: str) -> None:
        """Add a handoff route between agents."""
        if from_agent not in self.agents:
            raise ValueError(f"Source agent '{from_agent}' not found.")
        if to_agent not in self.agents:
            raise ValueError(f"Target agent '{to_agent}' not found.")
        self.agents[from_agent].handoffs[to_agent] = description

    async def run(self, task: str, initial_agent: str | None = None, **kwargs) -> OrchestrationResult:
        """Execute swarm orchestration.

        Args:
            task: The task description.
            initial_agent: Name of the agent to start with (default: first registered).
            **kwargs: Additional context.

        Returns:
            OrchestrationResult with handoff trail and final answer.
        """
        run_id = str(uuid.uuid4())[:8]
        start_time = time.perf_counter()
        all_outputs: list[dict] = []
        total_steps = 0
        messages: list[dict] = [{"role": "user", "content": task}]

        # Select initial agent
        current_agent_name = initial_agent or next(iter(self.agents.keys()))
        if current_agent_name not in self.agents:
            current_agent_name = next(iter(self.agents.keys()))

        handoff_count = 0

        while handoff_count < self.max_handoffs:
            swarm_agent = self.agents[current_agent_name]

            # Build context with handoff instructions
            handoff_list = "\n".join(
                f"- {target}: {desc}"
                for target, desc in swarm_agent.handoffs.items()
            )

            context = (
                f"{swarm_agent.instructions}\n\n"
                "You can hand off to these agents if needed:\n"
                f"{handoff_list if handoff_list else 'No handoffs available.'}\n\n"
                "When you are done and do NOT need to hand off, "
                "respond with your final answer. "
                "If you need to hand off, respond with: HANDOFF: agent_name\n"
                "Then provide context for the next agent."
            )

            full_prompt = f"{context}\n\nTask: {task}"

            try:
                result = await swarm_agent.agent.run(full_prompt)
                answer = result.answer if hasattr(result, "answer") else str(result)
                steps = result.steps if hasattr(result, "steps") else 1
                total_steps += steps
            except Exception as e:
                logger.warning("Agent '%s' failed: %s", current_agent_name, e)
                answer = f"HANDOFF: error - {e}"

            # Check for handoff instruction
            handoff_target = self._parse_handoff(answer)

            output = {
                "agent": current_agent_name,
                "handoff_to": handoff_target,
                "content": answer[:500],
                "steps": steps,
            }
            all_outputs.append(output)

            if handoff_target is None:
                # No handoff - this is the final answer
                break

            if handoff_target not in self.agents:
                logger.warning("Invalid handoff target: %s", handoff_target)
                break

            # Handoff
            current_agent_name = handoff_target
            handoff_count += 1
            messages.append({"role": "assistant", "content": answer})
            messages.append({"role": "system", "content": f"Handed off to: {handoff_target}"})

        # Extract final answer
        final_outputs = [o for o in all_outputs if o.get("handoff_to") is None]
        final_answer = final_outputs[-1]["content"] if final_outputs else (
            all_outputs[-1]["content"] if all_outputs else "No response."
        )

        elapsed = (time.perf_counter() - start_time) * 1000
        return OrchestrationResult(
            run_id=run_id,
            task=task,
            outputs=all_outputs,
            final_answer=final_answer,
            total_steps=total_steps,
            execution_time_ms=elapsed,
            success=handoff_count < self.max_handoffs,
        )

    def _parse_handoff(self, text: str) -> str | None:
        """Parse a handoff directive from agent output.

        Looks for patterns like: HANDOFF: agent_name

        Returns:
            Target agent name or None if no handoff.
        """
        import re

        patterns = [
            r'HANDOFF\s*:\s*(\w+)',
            r'handoff to\s+(\w+)',
            r'transfer to\s+(\w+)',
            r'delegate to\s+(\w+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)

        return None

    def get_agent_names(self) -> list[str]:
        """Return all registered agent names."""
        return list(self.agents.keys())

    def __repr__(self) -> str:
        return (
            f"SwarmOrchestrator(agents={list(self.agents.keys())}, "
            f"max_handoffs={self.max_handoffs})"
        )
