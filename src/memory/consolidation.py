"""
Memory consolidation engine that migrates short-term memories
into long-term storage.

Implements the STM -> LTM consolidation process:
1. Summarize recent conversation turns from STM
2. Extract key facts, decisions, and knowledge
3. Store as structured LTM entries with appropriate importance
4. Optionally create episodic records
"""

import asyncio
import logging
import time
from collections import deque
from typing import Any

logger = logging.getLogger(__name__)


class MemoryConsolidationEngine:
    """Engine for consolidating short-term memories into long-term storage.

    Periodically processes STM contents, summarizes them, and stores
    key information as LTM entries. Also manages the consolidation
    schedule and importance assignment.

    Args:
        consolidation_interval: Minimum seconds between consolidations (default 300s).
        max_memories_per_batch: Maximum LTM entries created per consolidation.
        summarizer: Optional callable/LLM for generating memory summaries.
                    Should accept (messages: list[dict]) -> str.
    """

    def __init__(
        self,
        consolidation_interval: float = 300.0,
        max_memories_per_batch: int = 10,
        summarizer=None,
    ):
        self.consolidation_interval = consolidation_interval
        self.max_memories_per_batch = max_memories_per_batch
        self.summarizer = summarizer
        self._last_consolidation = 0.0
        self._total_consolidated = 0

    # ------------------------------------------------------------------
    # Main consolidation
    # ------------------------------------------------------------------

    async def consolidate(
        self,
        short_term,
        long_term,
        episodic=None,
    ) -> int:
        """Consolidate STM content into LTM.

        Args:
            short_term: ShortTermMemory instance.
            long_term: LongTermMemory instance.
            episodic: Optional EpisodicMemory instance.

        Returns:
            Number of memories consolidated.
        """
        # Check if enough time has passed
        now = time.time()
        if now - self._last_consolidation < self.consolidation_interval:
            logger.debug("Skipping consolidation: too soon (%.1fs ago)", now - self._last_consolidation)
            return 0

        self._last_consolidation = now

        # Get messages from STM
        messages = short_term.get_messages()
        if len(messages) < 3:
            logger.debug("Skipping consolidation: only %d messages in STM", len(messages))
            return 0

        # Extract user-assistant turns
        turns = self._extract_turns(messages)
        if not turns:
            return 0

        # Generate memory entries
        memories = await self._generate_memories(turns)
        if not memories:
            return 0

        # Store in LTM
        consolidated = 0
        for memory in memories[:self.max_memories_per_batch]:
            try:
                await long_term.add(
                    content=memory["content"],
                    importance=memory.get("importance", 5.0),
                    metadata={
                        "type": "consolidated",
                        "source": "stm",
                        "timestamp": now,
                        **memory.get("metadata", {}),
                    },
                    tags=memory.get("tags", ["consolidated"]),
                )
                consolidated += 1
            except Exception as e:
                logger.warning("Failed to consolidate memory: %s", e)

        self._total_consolidated += consolidated

        if consolidated:
            logger.info(
                "Consolidated %d memories from STM (%d messages) to LTM",
                consolidated, len(messages),
            )

        return consolidated

    # ------------------------------------------------------------------
    # Turn extraction
    # ------------------------------------------------------------------

    def _extract_turns(self, messages: list[dict]) -> list[dict]:
        """Extract user-assistant conversation turns from messages.

        Returns:
            List of {"user": str, "assistant": str, "tools": list} dicts.
        """
        turns = []
        current_turn: dict | None = None

        for msg in messages:
            role = msg.get("role", "")

            if role == "user":
                if current_turn:
                    turns.append(current_turn)
                current_turn = {"user": msg.get("content", ""), "assistant": "", "tools": []}

            elif role == "assistant" and current_turn is not None:
                current_turn["assistant"] += msg.get("content", "")

            elif role in ("tool", "function") and current_turn is not None:
                content = msg.get("content", "")
                name = msg.get("name", "unknown")
                current_turn["tools"].append({"name": name, "result": str(content)[:200]})

        if current_turn and (current_turn["user"] or current_turn["assistant"]):
            turns.append(current_turn)

        return turns

    # ------------------------------------------------------------------
    # Memory generation
    # ------------------------------------------------------------------

    async def _generate_memories(self, turns: list[dict]) -> list[dict]:
        """Generate LTM memory entries from conversation turns.

        Returns:
            List of dicts with content, importance, metadata, tags.
        """
        memories = []

        for i, turn in enumerate(turns):
            user_msg = turn["user"]
            assistant_msg = turn["assistant"]

            if not user_msg:
                continue

            # Generate a simple summary
            if self.summarizer:
                try:
                    summary = await self._summarize_turn(turn)
                except Exception as e:
                    summary = self._default_summarize(turn)
            else:
                summary = self._default_summarize(turn)

            if summary:
                # Estimate importance based on turn characteristics
                importance = self._estimate_importance(turn)

                memories.append({
                    "content": summary,
                    "importance": importance,
                    "metadata": {
                        "turn_index": i,
                        "user_length": len(user_msg),
                        "has_tools": len(turn.get("tools", [])) > 0,
                    },
                    "tags": ["conversation", f"turn_{i}"],
                })

        return memories

    async def _summarize_turn(self, turn: dict) -> str:
        """Summarize a conversation turn using the configured summarizer."""
        if callable(self.summarizer):
            result = self.summarizer(
                f"User: {turn['user']}\nAssistant: {turn['assistant']}"
            )
            if asyncio.iscoroutine(result):
                return await result
            return str(result)

        return self._default_summarize(turn)

    @staticmethod
    def _default_summarize(turn: dict) -> str:
        """Default summarization without an LLM."""
        user = turn["user"]
        assistant = turn["assistant"]
        tools = turn.get("tools", [])

        summary = f"User asked: {user[:100]}"

        if tools:
            tool_names = [t.get("name", "unknown") for t in tools]
            summary += f" | Tools used: {', '.join(tool_names[:3])}"

        if assistant:
            summary += f" | Response: {assistant[:150]}"

        return summary[:500]

    @staticmethod
    def _estimate_importance(turn: dict) -> float:
        """Estimate the importance of a conversation turn.

        Factors:
        - Turn length (longer = potentially more important)
        - Tool usage (using tools = more important)
        - Key question words (what, how, why = more important)
        """
        importance = 5.0  # baseline

        user = turn.get("user", "")
        assistant = turn.get("assistant", "")

        # Longer turns are potentially more substantive
        total_len = len(user) + len(assistant)
        if total_len > 500:
            importance += 1.0
        if total_len > 1000:
            importance += 0.5

        # Tool usage suggests actionable content
        if turn.get("tools"):
            importance += 1.5

        # Key question words
        user_lower = user.lower()
        question_words = ["what", "how", "why", "explain", "analyze", "compare"]
        for w in question_words:
            if w in user_lower:
                importance += 0.3
                break

        return min(10.0, max(1.0, importance))

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    @property
    def stats(self) -> dict:
        """Return consolidation statistics."""
        return {
            "total_consolidated": self._total_consolidated,
            "last_consolidation": self._last_consolidation,
            "interval": self.consolidation_interval,
            "seconds_since_last": time.time() - self._last_consolidation,
        }

    def __repr__(self) -> str:
        return (
            f"MemoryConsolidationEngine(consolidated={self._total_consolidated}, "
            f"interval={self.consolidation_interval}s)"
        )
