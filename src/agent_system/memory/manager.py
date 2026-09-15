"""
Unified memory orchestrator that coordinates short-term, long-term,
and episodic memory stores.

Provides a single interface for retrieving context, consolidating
memories, and updating after task completion.
"""

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from src.agent_system.memory.consolidation import MemoryConsolidationEngine
from src.agent_system.memory.episodic import Episode, EpisodicMemory
from src.agent_system.memory.forgetting_curve import ForgettingCurve
from src.agent_system.memory.long_term import LongTermMemory
from src.agent_system.memory.short_term import ShortTermMemory

logger = logging.getLogger(__name__)


@dataclass
class MemoryContext:
    """Aggregated context from all memory stores."""
    short_term_context: list[dict]  # Recent conversation messages
    long_term_relevant: list[dict]  # Relevant long-term memories
    similar_episodes: list[dict]    # Similar past task episodes
    lessons: list[str]              # Aggregated lessons learned
    timestamp: float = field(default_factory=time.time)


class MemoryManager:
    """Unified memory orchestrator.

    Coordinates three memory tiers:
    - ShortTermMemory: Conversation context (immediate)
    - LongTermMemory: Persistent knowledge (semantic)
    - EpisodicMemory: Task history and lessons (experiential)

    Provides:
    - Context retrieval across all stores
    - Periodic STM -> LTM consolidation
    - Post-task memory updates
    """

    def __init__(
        self,
        short_term: ShortTermMemory | None = None,
        long_term: LongTermMemory | None = None,
        episodic: EpisodicMemory | None = None,
        consolidation_engine: MemoryConsolidationEngine | None = None,
    ):
        self.short_term = short_term or ShortTermMemory()
        self.long_term = long_term or LongTermMemory()
        self.episodic = episodic or EpisodicMemory()
        self.consolidation_engine = consolidation_engine or MemoryConsolidationEngine()
        self.forgetting_curve = ForgettingCurve()

    # ------------------------------------------------------------------
    # Context retrieval
    # ------------------------------------------------------------------

    async def retrieve_context(self, query: str) -> MemoryContext:
        """Retrieve relevant context from all memory stores for a query.

        Args:
            query: The task or question to retrieve context for.

        Returns:
            MemoryContext with data from all three memory stores.
        """
        # Short-term: get recent conversation
        stm_context = self.short_term.get_messages()

        # Long-term: search for relevant persistent memories
        ltm_context = await self.long_term.search(query, k=5)

        # Episodic: find similar past episodes
        similar_episodes = await self.episodic.find_similar(query, k=3)
        lessons = await self.episodic.get_lessons(query, max_lessons=5)

        context = MemoryContext(
            short_term_context=stm_context,
            long_term_relevant=ltm_context,
            similar_episodes=[ep.to_dict() for ep in similar_episodes],
            lessons=lessons,
        )

        logger.debug(
            "Retrieved context: STM=%d msgs, LTM=%d memories, Episodes=%d, Lessons=%d",
            len(stm_context), len(ltm_context), len(similar_episodes), len(lessons),
        )

        return context

    def get_conversation_context(self) -> list[dict]:
        """Get immediate conversation context from short-term memory.

        Returns:
            List of message dicts with role and content.
        """
        return self.short_term.get_messages()

    async def enrich_prompt(
        self,
        system_prompt: str,
        task: str,
    ) -> str:
        """Enrich a system prompt with retrieved context.

        Args:
            system_prompt: The base system prompt.
            task: The current task.

        Returns:
            Enriched system prompt with context from memory.
        """
        context = await self.retrieve_context(task)

        parts = [system_prompt]

        # Add relevant long-term memories
        if context.long_term_relevant:
            memories_text = "\n".join(
                f"- {m.get('content', '')[:200]}"
                for m in context.long_term_relevant[:3]
            )
            parts.append(f"\nRelevant Knowledge:\n{memories_text}")

        # Add lessons from similar episodes
        if context.lessons:
            lessons_text = "\n".join(f"- {l}" for l in context.lessons[:5])
            parts.append(f"\nLessons from past tasks:\n{lessons_text}")

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Consolidation
    # ------------------------------------------------------------------

    async def consolidate(self) -> int:
        """Consolidate short-term memories into long-term storage.

        Summarizes recent conversations and stores them as LTM entries.

        Returns:
            Number of memories consolidated.
        """
        consolidated = await self.consolidation_engine.consolidate(
            self.short_term, self.long_term, self.episodic,
        )

        if consolidated:
            logger.info("Consolidated %d memories from STM to LTM", consolidated)

        return consolidated

    async def consolidate_if_needed(self) -> int:
        """Consolidate only if STM usage exceeds threshold.

        Returns:
            Number of memories consolidated, or 0 if not needed.
        """
        if self.short_term.is_full:
            return await self.consolidate()
        return 0

    # ------------------------------------------------------------------
    # Post-task updates
    # ------------------------------------------------------------------

    async def update_after_task(
        self,
        task: str,
        result: str,
        trajectory: list[dict],
        agent_type: str = "react",
        tools_used: list[str] | None = None,
        execution_time_ms: float = 0.0,
    ) -> None:
        """Update all memory stores after task completion.

        Args:
            task: The task description.
            result: The task outcome.
            trajectory: List of step dicts from execution.
            agent_type: The type of agent used.
            tools_used: List of tool names that were used.
            execution_time_ms: Total execution time in milliseconds.
        """
        # Determine outcome
        outcome = self._classify_outcome(trajectory)

        # Extract lessons
        lessons = self._extract_lessons(trajectory)

        # Store as episode
        episode = Episode(
            task=task,
            outcome=outcome,
            lessons=lessons,
            timestamp=time.time(),
            agent_type=agent_type,
            steps=len(trajectory),
            tools_used=tools_used or [],
            execution_time_ms=execution_time_ms,
        )
        await self.episodic.add(episode)

        # Store a summary in long-term memory
        summary = (
            f"Task: {task}\n"
            f"Outcome: {outcome}\n"
            f"Agent: {agent_type}\n"
            f"Steps: {len(trajectory)}\n"
            f"Tools: {', '.join(tools_used or [])}\n"
            f"Lessons: {'; '.join(lessons) if lessons else 'None'}"
        )

        importance = 7.0 if outcome == "SUCCESS" else 5.0 if outcome == "PARTIAL" else 3.0
        await self.long_term.add(
            content=summary,
            importance=importance,
            metadata={
                "type": "task_summary",
                "agent_type": agent_type,
                "outcome": outcome,
            },
            tags=["task", agent_type, outcome.lower()],
        )

        logger.info(
            "Updated memory after task: '%s' -> %s (%d steps)",
            task[:50], outcome, len(trajectory),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_outcome(trajectory: list[dict]) -> str:
        """Classify task outcome from trajectory."""
        if not trajectory:
            return "UNKNOWN"

        successes = sum(1 for step in trajectory if step.get("success", True))
        total = len(trajectory)

        if successes == total and total > 0:
            return "SUCCESS"
        elif successes > total / 2:
            return "PARTIAL"
        else:
            return "FAILURE"

    @staticmethod
    def _extract_lessons(trajectory: list[dict]) -> list[str]:
        """Extract lessons from task execution trajectory."""
        lessons = []

        for step in trajectory:
            error = step.get("error")
            if error:
                lessons.append(f"Encountered error: {error}")

            result = step.get("result")
            if isinstance(result, dict) and result.get("truncated"):
                lessons.append(f"Result truncated at step {step.get('step_id', '?')}")

        if not lessons and trajectory:
            lessons.append("Task completed without errors.")

        return lessons

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    async def apply_forgetting(self) -> int:
        """Apply the forgetting curve to evict stale long-term memories.

        Returns:
            Number of memories evicted.
        """
        current_time = time.time()
        evicted = 0

        for memory_id in list(self.long_term._memories.keys()):
            memory = self.long_term._memories.get(memory_id)
            if not memory:
                continue

            entry = {
                "created_at": memory.created_at,
                "last_accessed": memory.last_accessed,
                "importance": memory.importance,
            }

            if self.forgetting_curve.should_evict(entry, current_time):
                await self.long_term.delete(memory_id)
                evicted += 1

        if evicted:
            logger.info("Forgetting curve evicted %d memories", evicted)
        return evicted

    def clear_all(self) -> None:
        """Clear all memory stores. Use with caution."""
        self.short_term.clear()
        # LTM and episodic clear must be done carefully
        self.short_term.clear()

    def get_stats(self) -> dict:
        """Return statistics from all memory stores."""
        return {
            "short_term": {
                "messages": self.short_term.message_count,
                "tokens": self.short_term.token_count,
                "max_tokens": self.short_term.max_tokens,
            },
            "long_term": {
                "memories": self.long_term.count,
                "tags": len(self.long_term.get_all_tags()),
            },
            "episodic": self.episodic.get_stats(),
        }

    def __repr__(self) -> str:
        return (
            f"MemoryManager(STM={self.short_term.message_count}msgs, "
            f"LTM={self.long_term.count}, EP={len(self.episodic)})"
        )
