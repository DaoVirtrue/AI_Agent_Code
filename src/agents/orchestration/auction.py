"""
Auction orchestrator - task bidding between agents.

Agents bid on subtasks based on their capabilities and confidence.
The highest-bidding agent is assigned each subtask.
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


@dataclass
class Bid:
    """A bid from an agent for a subtask."""
    agent_name: str
    subtask_index: int
    confidence: float  # 0-1
    estimated_time: float  # seconds
    rationale: str
    agent: Any


class AuctionOrchestrator:
    """Task-bidding orchestrator where agents compete for subtasks.

    An auctioneer decomposes the task, agents bid on subtasks, and the
    auctioneer assigns each subtask to the highest bidder.

    Args:
        agents: List of agent instances.
        auctioneer_llm: LLM for the auctioneer (decomposing and synthesis).
        bid_strategy: "confidence" (highest confidence wins) or "speed" (fastest wins).
        max_bid_rounds: Maximum auction rounds.
    """

    def __init__(
        self,
        agents: list = None,
        auctioneer_llm=None,
        bid_strategy: str = "confidence",
        max_bid_rounds: int = 3,
    ):
        self.agents = agents or []
        self.auctioneer_llm = auctioneer_llm
        self.bid_strategy = bid_strategy
        self.max_bid_rounds = max_bid_rounds

    async def run(self, task: str, **kwargs) -> OrchestrationResult:
        """Execute the auction process.

        Args:
            task: The task description.
            **kwargs: Additional context.

        Returns:
            OrchestrationResult with bids and final answer.
        """
        run_id = str(uuid.uuid4())[:8]
        start_time = time.perf_counter()
        all_outputs: list[dict] = []
        total_steps = 0

        try:
            # Step 1: Auctioneer decomposes task into subtasks
            subtasks = await self._decompose_task(task)

            if not subtasks:
                subtasks = [task]

            # Step 2: Bidding rounds
            all_bids: list[Bid] = []

            for round_num in range(self.max_bid_rounds):
                round_bids = await self._collect_bids(subtasks, task, round_num)
                all_bids.extend(round_bids)

                if round_num >= self.max_bid_rounds - 1:
                    break

            # Step 3: Auctioneer selects winning bids
            assignments = self._select_winners(subtasks, all_bids)

            # Step 4: Execute assigned subtasks
            subtask_results = []
            for subtask_idx, bid in assignments.items():
                subtask = subtasks[subtask_idx] if subtask_idx < len(subtasks) else "Unknown subtask"

                try:
                    result = await bid.agent.run(subtask)
                    answer = result.answer if hasattr(result, "answer") else str(result)
                    steps = result.steps if hasattr(result, "steps") else 1
                    total_steps += steps

                    subtask_results.append({
                        "subtask_index": subtask_idx,
                        "agent": bid.agent_name,
                        "confidence": bid.confidence,
                        "subtask": subtask,
                        "answer": answer,
                        "steps": steps,
                        "success": getattr(result, "success", True),
                    })
                except Exception as e:
                    logger.warning("Bid execution failed for agent '%s': %s", bid.agent_name, e)
                    subtask_results.append({
                        "subtask_index": subtask_idx,
                        "agent": bid.agent_name,
                        "subtask": subtask,
                        "answer": f"Error: {e}",
                        "success": False,
                    })

            all_outputs = [
                {"type": "bid", "agent": b.agent_name, "subtask": b.subtask_index,
                 "confidence": b.confidence, "rationale": b.rationale}
                for b in all_bids
            ] + [
                {"type": "result", **r} for r in subtask_results
            ]

            # Step 5: Synthesize final answer
            final_answer = await self._synthesize(task, subtask_results)

            elapsed = (time.perf_counter() - start_time) * 1000
            return OrchestrationResult(
                run_id=run_id,
                task=task,
                outputs=all_outputs,
                final_answer=final_answer,
                total_steps=total_steps,
                execution_time_ms=elapsed,
                success=all(r.get("success", False) for r in subtask_results),
            )

        except Exception as e:
            elapsed = (time.perf_counter() - start_time) * 1000
            logger.exception("Auction orchestration failed")
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

    async def _decompose_task(self, task: str) -> list[str]:
        """Decompose a task into subtasks for bidding."""
        if not self.auctioneer_llm:
            return [task]

        prompt = (
            "Decompose the following task into smaller independent subtasks "
            "that can be auctioned to different agents. Return a numbered list.\n\n"
            f"Task: {task}\n\n"
            "Subtask breakdown (numbered, max 6):"
        )

        try:
            response = await self.auctioneer_llm.ainvoke([{"role": "user", "content": prompt}])
            text = response.content if hasattr(response, "content") else str(response)
        except Exception:
            return [task]

        import re
        subtasks = re.findall(r'\d+[\.\)\s-]+(.+)', text)
        return subtasks[:6] if subtasks else [task]

    async def _collect_bids(self, subtasks: list[str], task: str, round_num: int) -> list[Bid]:
        """Collect bids from all agents for all unassigned subtasks."""
        bids = []

        for agent in self.agents:
            agent_name = type(agent).__name__

            for i, subtask in enumerate(subtasks):
                bid_prompt = (
                    "You are an agent in a task auction. Review the subtask below "
                    "and submit a bid. Include your confidence (0-100), estimated "
                    "time in seconds, and rationale.\n\n"
                    f"Original Task: {task}\n"
                    f"Subtask {i + 1}: {subtask}\n\n"
                    "Bid: Confidence=X%, Time=Ys, Rationale: ..."
                )

                try:
                    result = await agent.run(bid_prompt)
                    answer = result.answer if hasattr(result, "answer") else str(result)
                except Exception:
                    continue

                # Parse bid
                import re

                conf_match = re.search(r'Confidence\s*[=:]\s*(\d+)', answer, re.IGNORECASE)
                time_match = re.search(r'Time\s*[=:]\s*(\d+(?:\.\d+)?)', answer, re.IGNORECASE)
                rationale_match = re.search(r'Rationale\s*[=:]\s*(.+)', answer, re.IGNORECASE)

                confidence = min(1.0, int(conf_match.group(1)) / 100) if conf_match else 0.5
                estimated_time = float(time_match.group(1)) if time_match else 30.0
                rationale = rationale_match.group(1).strip() if rationale_match else "No rationale"

                if confidence > 0.1:  # Only consider meaningful bids
                    bids.append(Bid(
                        agent_name=agent_name,
                        subtask_index=i,
                        confidence=confidence,
                        estimated_time=estimated_time,
                        rationale=rationale,
                        agent=agent,
                    ))

        return bids

    def _select_winners(self, subtasks: list[str], all_bids: list[Bid]) -> dict[int, Bid]:
        """Select winning bids for each subtask.

        Returns:
            Dict mapping subtask_index -> winning Bid.
        """
        assignments: dict[int, Bid] = {}

        # Group bids by subtask
        bids_by_subtask: dict[int, list[Bid]] = {}
        for bid in all_bids:
            bids_by_subtask.setdefault(bid.subtask_index, []).append(bid)

        for subtask_idx in range(len(subtasks)):
            candidates = bids_by_subtask.get(subtask_idx, [])
            if not candidates:
                continue

            # Score and select
            if self.bid_strategy == "confidence":
                candidates.sort(key=lambda b: b.confidence, reverse=True)
            elif self.bid_strategy == "speed":
                candidates.sort(key=lambda b: b.estimated_time)
            else:
                # Composite score: confidence / time
                candidates.sort(
                    key=lambda b: b.confidence / max(b.estimated_time, 1),
                    reverse=True,
                )

            # Assign, but avoid giving one agent too many subtasks
            assigned_agents = {b.agent_name for b in assignments.values()}
            for candidate in candidates:
                if candidate.agent_name not in assigned_agents or len(bids_by_subtask.get(subtask_idx, [])) == 1:
                    assignments[subtask_idx] = candidate
                    break
            else:
                assignments[subtask_idx] = candidates[0]

        return assignments

    async def _synthesize(self, task: str, results: list[dict]) -> str:
        """Synthesize subtask results into a final answer."""
        if not results:
            return "No results from the auction."

        results_text = "\n---\n".join(
            f"Subtask {r['subtask_index']} ({r.get('agent', '?')}): {r.get('answer', '')[:300]}"
            for r in results
        )

        if self.auctioneer_llm:
            prompt = (
                f"Task: {task}\n\nSubtask results:\n{results_text}\n\n"
                "Synthesize into a comprehensive final answer:"
            )
            try:
                response = await self.auctioneer_llm.ainvoke([{"role": "user", "content": prompt}])
                return response.content if hasattr(response, "content") else str(response)
            except Exception:
                pass

        return "Auction Results:\n\n" + results_text

    def __repr__(self) -> str:
        return f"AuctionOrchestrator(agents={len(self.agents)}, strategy={self.bid_strategy})"
