"""
Multi-agent debate orchestrator with voting and rebuttal rounds.

Multiple agents debate a topic, each providing arguments, rebuttals,
and voting. A moderator synthesizes the final conclusion.
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any

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


class DebateOrchestrator:
    """Multi-agent debate with structured rounds.

    Agents take positions on a topic, argue their cases, provide rebuttals,
    and vote on the best answer. A moderator synthesizes the final result.

    Args:
        agents: List of agent instances (each must have `run` method).
        moderator_llm: LLM for the moderator (synthesis and question framing).
        max_rounds: Maximum number of debate rounds (default 3).
        voting_threshold: Consensus threshold for early termination (0.5-1.0).
    """

    def __init__(
        self,
        agents: list = None,
        moderator_llm=None,
        max_rounds: int = 3,
        voting_threshold: float = 0.6,
    ):
        self.agents = agents or []
        self.moderator_llm = moderator_llm
        self.max_rounds = max_rounds
        self.voting_threshold = voting_threshold

    async def run(self, task: str, **kwargs) -> OrchestrationResult:
        """Execute the debate orchestration.

        Rounds:
        1. Opening statements (each agent gives initial response)
        2. Rebuttal rounds (each agent critiques others' positions)
        3. Voting (agents rank answers)
        4. Moderator synthesis

        Args:
            task: The debate topic or question.
            **kwargs: Additional context.

        Returns:
            OrchestrationResult with final synthesized answer.
        """
        run_id = str(uuid.uuid4())[:8]
        start_time = time.perf_counter()
        all_outputs: list[dict] = []
        total_steps = 0

        if len(self.agents) < 2:
            return OrchestrationResult(
                run_id=run_id, task=task, outputs=[],
                final_answer="Debate requires at least 2 agents.",
                total_steps=0, execution_time_ms=0, success=False,
                error="Insufficient agents",
            )

        try:
            # Round 1: Opening statements
            openings = await asyncio.gather(*[
                self._get_agent_response(agent, task, role="opening")
                for agent in self.agents
            ])

            for i, (agent, answer) in enumerate(zip(self.agents, openings)):
                all_outputs.append({
                    "round": 1,
                    "type": "opening",
                    "agent": type(agent).__name__,
                    "agent_index": i,
                    "answer": answer,
                })
            total_steps += len(self.agents)

            # Rounds 2+: Rebuttals
            for round_num in range(2, self.max_rounds + 1):
                previous_answers = [
                    o["answer"] for o in all_outputs
                    if o["round"] == round_num - 1
                ]

                rebuttal_tasks = []
                for i, agent in enumerate(self.agents):
                    other_answers = [a for j, a in enumerate(previous_answers) if j != i]
                    rebuttal_prompt = (
                        f"Original Task: {task}\n\n"
                        "Other agents' answers from the previous round:\n"
                        + "\n---\n".join(
                            f"Agent {j}: {a[:500]}"
                            for j, a in enumerate(other_answers)
                        )
                        + "\n\nProvide your rebuttal or refined answer. "
                        "Address weaknesses in others' arguments and strengthen your own position:"
                    )
                    rebuttal_tasks.append(self._get_agent_response(agent, rebuttal_prompt, role=f"rebuttal_{round_num}"))

                rebuttals = await asyncio.gather(*rebuttal_tasks)

                for i, (agent, answer) in enumerate(zip(self.agents, rebuttals)):
                    all_outputs.append({
                        "round": round_num,
                        "type": "rebuttal",
                        "agent": type(agent).__name__,
                        "agent_index": i,
                        "answer": answer,
                    })
                total_steps += len(self.agents)

                # Check for early consensus (skip voting in intermediate rounds)
                if round_num < self.max_rounds:
                    continue

            # Voting round
            votes = await self._conduct_voting(task, all_outputs)
            total_steps += 1

            # Moderator synthesis
            final_answer = await self._synthesize(task, all_outputs, votes)

            elapsed = (time.perf_counter() - start_time) * 1000
            return OrchestrationResult(
                run_id=run_id,
                task=task,
                outputs=all_outputs + [{"type": "votes", "votes": votes}],
                final_answer=final_answer,
                total_steps=total_steps,
                execution_time_ms=elapsed,
                success=True,
            )

        except Exception as e:
            elapsed = (time.perf_counter() - start_time) * 1000
            logger.exception("Debate orchestration failed")
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

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _get_agent_response(self, agent, prompt: str, role: str = "respondent") -> str:
        """Get a response from an agent."""
        try:
            result = await agent.run(prompt)
            return result.answer if hasattr(result, "answer") else str(result)
        except Exception as e:
            logger.warning("Agent failed (%s): %s", role, e)
            return f"Agent error: {e}"

    async def _conduct_voting(self, task: str, outputs: list[dict]) -> dict:
        """Have agents vote on the best answer.

        Returns:
            Dict mapping agent_index -> list of scores.
        """
        # Collect final answers from last round
        last_round = max(o["round"] for o in outputs if "round" in o)
        final_answers = {
            o["agent_index"]: o["answer"]
            for o in outputs
            if o.get("round") == last_round
        }

        if not final_answers:
            return {}

        votes = {}
        for i, agent in enumerate(self.agents):
            voting_prompt = (
                "You are a debate judge. Review the following answers to the task "
                "and rank them from best (1) to worst by agent index.\n\n"
                f"Task: {task}\n\n"
                "Answers:\n"
                + "\n---\n".join(
                    f"Agent {idx}: {ans[:400]}"
                    for idx, ans in final_answers.items()
                )
                + "\n\nReturn your ranking as: Agent X=rank, Agent Y=rank, ..."
            )

            try:
                result = await agent.run(voting_prompt)
                answer = result.answer if hasattr(result, "answer") else str(result)
            except Exception:
                answer = ""

            # Parse rankings
            import re
            rankings = {}
            for match in re.finditer(r'Agent\s+(\d+)\s*[=:]\s*(\d+)', answer):
                rankings[int(match.group(1))] = int(match.group(2))

            votes[i] = rankings

        return votes

    async def _synthesize(self, task: str, outputs: list[dict], votes: dict) -> str:
        """Moderator synthesizes the final conclusion.

        Args:
            task: The original debate topic.
            outputs: All agent outputs.
            votes: Voting results.

        Returns:
            Synthesized final answer.
        """
        if not self.moderator_llm:
            # Fallback: return best-voted answer
            return self._fallback_synthesize(outputs, votes)

        # Build debate summary
        debate_summary = []
        for o in outputs:
            debate_summary.append(
                f"[{o.get('type', '?')}, Round {o.get('round', '?')}, "
                f"Agent {o.get('agent_index', '?')}]: {o.get('answer', '')[:300]}"
            )

        prompt = (
            "You are a debate moderator. Synthesize the following multi-agent "
            "debate into a comprehensive final conclusion. Consider all arguments, "
            "rebuttals, and votes. Provide a balanced, well-reasoned final answer.\n\n"
            f"Topic: {task}\n\n"
            "Debate Discussion:\n"
            + "\n\n".join(debate_summary[:15])
            + "\n\nFinal Synthesis:"
        )

        try:
            response = await self.moderator_llm.ainvoke([{"role": "user", "content": prompt}])
            return response.content if hasattr(response, "content") else str(response)
        except Exception as e:
            return self._fallback_synthesize(outputs, votes)

    def _fallback_synthesize(self, outputs: list[dict], votes: dict) -> str:
        """Fallback synthesis without moderator LLM."""
        # Get the answer that received the most #1 rankings
        best_agent = None
        best_score = float("inf")

        for voter_idx, rankings in votes.items():
            for agent_idx, rank in rankings.items():
                if rank < best_score:
                    best_score = rank
                    best_agent = agent_idx

        if best_agent is not None:
            for o in outputs:
                if o.get("agent_index") == best_agent and o.get("type") in ("rebuttal", "opening"):
                    return o["answer"]

        # Last resort: return last answer
        return outputs[-1]["answer"] if outputs else "No consensus reached."

    def __repr__(self) -> str:
        agent_names = [type(a).__name__ for a in self.agents]
        return f"DebateOrchestrator(agents={agent_names}, rounds={self.max_rounds})"
