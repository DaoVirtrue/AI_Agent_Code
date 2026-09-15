"""Hybrid context strategy: summarize old turns, keep recent verbatim.

Achieves 5-20x compression ratio by summarizing messages older than N turns
while preserving the most recent M turns in full detail. This gives the LLM
detailed recent context and a compact summary of older history.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class HybridStrategy:
    """Hybrid context management combining summarization and sliding window.

    Strategy:
    1. Split conversation into "old" (summarize) and "recent" (keep verbatim).
    2. Generate a compressed summary of old messages.
    3. Build final context: system prompt with summary + recent messages.

    This provides LLMs with both long-term context (via summary) and
    detailed short-term context (via recent verbatim messages), achieving
    5-20x compression of older history.

    Usage::

        strategy = HybridStrategy(summarizer, token_counter, recent_turns=3)
        optimized = await strategy.process(messages, model="gpt-4o")
    """

    def __init__(
        self,
        summarizer: Any,
        token_counter: Any,
        recent_turns: int = 3,
        summary_trigger_turns: int = 10,
        max_summary_tokens: int = 500,
    ) -> None:
        """Initialize hybrid strategy.

        Args:
            summarizer: HistorySummarizer instance.
            token_counter: TokenCounter instance.
            recent_turns: Number of most recent turns to keep verbatim.
            summary_trigger_turns: Minimum turns before summarization kicks in.
            max_summary_tokens: Max tokens for the summary.
        """
        self.summarizer = summarizer
        self.token_counter = token_counter
        self.recent_turns = recent_turns
        self.summary_trigger_turns = summary_trigger_turns
        self.max_summary_tokens = max_summary_tokens

    async def process(
        self,
        messages: list[dict[str, Any]],
        model: str,
    ) -> list[dict[str, Any]]:
        """Process messages using the hybrid strategy.

        Args:
            messages: Original messages list.
            model: Model identifier for token counting.

        Returns:
            Optimized messages list with summary + recent verbatim.
        """
        if not messages:
            return []

        # Separate system and non-system
        system_msgs = [m for m in messages if m.get("role") == "system"]
        non_system = [m for m in messages if m.get("role") != "system"]

        # Group into turns
        turns = self._group_into_turns(non_system)

        total_turns = len(turns)

        # Not enough turns to warrant summarization
        if total_turns <= self.summary_trigger_turns:
            return messages

        # Split: old (to summarize) vs recent (to keep)
        split_point = max(0, total_turns - self.recent_turns)

        old_turns = turns[:split_point]
        recent_turns = turns[split_point:]

        # Flatten old turns back to messages
        old_messages: list[dict[str, Any]] = []
        for turn in old_turns:
            old_messages.extend(turn)

        # Generate summary of old messages
        if old_messages:
            summary = await self.summarizer.summarize(
                old_messages,
                max_summary_tokens=self.max_summary_tokens,
            )
        else:
            summary = ""

        # Build the optimized message list
        result: list[dict[str, Any]] = []

        # System messages first
        result.extend(system_msgs)

        # Add summary as a system-level context note
        if summary:
            existing_system = " ".join(
                m.get("content", "") for m in system_msgs if isinstance(m.get("content"), str)
            )

            summary_message = (
                f"[CONVERSATION HISTORY SUMMARY ({len(old_turns)} previous turns)]\n"
                f"{summary}\n"
                f"[END OF SUMMARY — {len(recent_turns)} recent turns follow verbatim]\n"
            )

            if result and result[-1].get("role") == "system":
                # Append to the last system message
                result[-1] = {
                    **result[-1],
                    "content": result[-1].get("content", "") + "\n\n" + summary_message,
                }
            else:
                result.insert(0, {"role": "system", "content": summary_message})

        # Add recent turns in full
        for turn in recent_turns:
            result.extend(turn)

        # Log compression stats
        original_tokens = self.token_counter.count_messages(messages, model)
        optimized_tokens = self.token_counter.count_messages(result, model)
        ratio = (
            original_tokens / optimized_tokens
            if optimized_tokens > 0
            else float("inf")
        )

        logger.info(
            "Hybrid strategy: %d turns → %d verbatim + summary. "
            "Tokens: %d → %d (%.1fx compression)",
            total_turns,
            len(recent_turns),
            original_tokens,
            optimized_tokens,
            ratio,
        )

        return result

    async def estimate_summary_tokens(
        self,
        messages: list[dict[str, Any]],
        model: str,
    ) -> dict[str, int]:
        """Estimate token breakdown for hybrid strategy without executing.

        Args:
            messages: Original messages.
            model: Model identifier.

        Returns:
            Dict with estimated token counts per section.
        """
        system_msgs = [m for m in messages if m.get("role") == "system"]
        non_system = [m for m in messages if m.get("role") != "system"]

        turns = self._group_into_turns(non_system)
        split_point = max(0, len(turns) - self.recent_turns)

        old_turns = turns[:split_point]
        recent_turns = turns[split_point:]

        system_tokens = self.token_counter.count_messages(system_msgs, model)

        old_messages: list[dict[str, Any]] = []
        for turn in old_turns:
            old_messages.extend(turn)
        old_tokens = self.token_counter.count_messages(old_messages, model)

        recent_messages: list[dict[str, Any]] = []
        for turn in recent_turns:
            recent_messages.extend(turn)
        recent_tokens = self.token_counter.count_messages(recent_messages, model)

        return {
            "system_tokens": system_tokens,
            "old_turns_tokens": old_tokens,
            "recent_turns_tokens": recent_tokens,
            "estimated_summary_tokens": self.max_summary_tokens,
            "total_estimated": system_tokens + self.max_summary_tokens + recent_tokens,
        }

    def _group_into_turns(
        self,
        messages: list[dict[str, Any]],
    ) -> list[list[dict[str, Any]]]:
        """Group messages into conversation turns (user + assistant pairs).

        Args:
            messages: List of non-system messages.

        Returns:
            List of turns, each turn is a list of messages.
        """
        turns: list[list[dict[str, Any]]] = []
        current_turn: list[dict[str, Any]] = []

        for msg in messages:
            role = msg.get("role", "user")
            if role == "user" and current_turn:
                turns.append(current_turn)
                current_turn = []
            current_turn.append(msg)

        if current_turn:
            turns.append(current_turn)

        return turns
