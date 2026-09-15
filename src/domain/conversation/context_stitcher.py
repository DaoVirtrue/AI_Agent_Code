"""Context stitching: merge fragmented conversation turns into coherent context.

Provides ConversationHistory for managing multi-turn dialog state and
ContextStitcher for building coherent query context from fragmented turns.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConversationTurn:
    """A single turn in a conversation."""
    turn_id: int
    role: str  # "user" | "assistant" | "system"
    content: str
    timestamp: float = field(default_factory=time.time)
    entities: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)


class ConversationHistory:
    """Manages the full conversation history with turn tracking.

    Maintains an ordered list of turns with automatic deduplication
    of entities and support for context windowing.
    """

    def __init__(self, max_turns: int = 50) -> None:
        self._turns: list[ConversationTurn] = []
        self._turn_counter: int = 0
        self.max_turns = max_turns
        self._entity_index: dict[str, int] = {}  # entity -> first turn_id
        self._topic_index: dict[str, int] = {}    # topic -> first turn_id

    def add_turn(self, role: str, content: str, entities: list[str] | None = None,
                 topics: list[str] | None = None) -> ConversationTurn:
        """Add a new turn to the conversation history.

        Args:
            role: "user", "assistant", or "system"
            content: The text content of the turn
            entities: Optional pre-extracted entities
            topics: Optional pre-extracted topics

        Returns:
            The newly created ConversationTurn
        """
        self._turn_counter += 1
        turn = ConversationTurn(
            turn_id=self._turn_counter,
            role=role,
            content=content,
            entities=entities or [],
            topics=topics or [],
        )
        self._turns.append(turn)

        # Index entities
        for entity in turn.entities:
            if entity not in self._entity_index:
                self._entity_index[entity] = turn.turn_id
        for topic in turn.topics:
            if topic not in self._topic_index:
                self._topic_index[topic] = turn.turn_id

        # Enforce max_turns
        if len(self._turns) > self.max_turns:
            removed = self._turns.pop(0)
            # Clean up indices for removed turn
            for entity in removed.entities:
                if self._entity_index.get(entity) == removed.turn_id:
                    del self._entity_index[entity]
            for topic in removed.topics:
                if self._topic_index.get(topic) == removed.turn_id:
                    del self._topic_index[topic]

        return turn

    def get_recent_turns(self, n: int = 5) -> list[ConversationTurn]:
        """Get the n most recent conversation turns."""
        return self._turns[-n:] if n < len(self._turns) else list(self._turns)

    def get_last_user_query(self) -> str | None:
        """Get the content of the most recent user turn."""
        for turn in reversed(self._turns):
            if turn.role == "user":
                return turn.content
        return None

    def get_last_assistant_response(self) -> str | None:
        """Get the content of the most recent assistant turn."""
        for turn in reversed(self._turns):
            if turn.role == "assistant":
                return turn.content
        return None

    def get_all_entities(self) -> list[str]:
        """Get unique entities across all turns in chronological order of first mention."""
        sorted_entities = sorted(self._entity_index.items(), key=lambda x: x[1])
        return [e for e, _ in sorted_entities]

    def to_context_string(self) -> str:
        """Format the full conversation history as a single context string.

        Returns:
            A formatted string suitable for inclusion in an LLM prompt.
        """
        lines: list[str] = []
        for turn in self._turns:
            role_label = {
                "user": "User",
                "assistant": "Assistant",
                "system": "System",
            }.get(turn.role, turn.role.capitalize())
            lines.append(f"{role_label}: {turn.content}")
        return "\n".join(lines)

    def get_turn_count(self) -> int:
        """Return the total number of turns."""
        return len(self._turns)

    def clear(self) -> None:
        """Reset the conversation history."""
        self._turns.clear()
        self._turn_counter = 0
        self._entity_index.clear()
        self._topic_index.clear()

    def __len__(self) -> int:
        return len(self._turns)

    def __iter__(self):
        return iter(self._turns)

    def __getitem__(self, index: int) -> ConversationTurn:
        return self._turns[index]


class ContextStitcher:
    """Merge fragmented context across turns into a coherent paragraph.

    Uses an LLM client to synthesize scattered information from multiple
    conversation turns into a single, coherent context paragraph that
    can be used to augment the current query.
    """

    def __init__(self, llm_client: Any) -> None:
        """Initialize with an LLM client for text generation.

        Args:
            llm_client: An async LLM client with a `generate` method
                        that accepts a prompt string and returns generated text.
        """
        self._llm = llm_client

    async def build_query_context(self, query: str, history: ConversationHistory) -> str:
        """Build a coherent context paragraph for augmenting the current query.

        This stitches together relevant information from previous turns
        to provide the LLM with full context for answering the query.

        Args:
            query: The current user query.
            history: The conversation history.

        Returns:
            A context string that can be prepended to the query.
        """
        turns = history.get_recent_turns(n=10)
        if len(turns) <= 1:
            # Only the current query or empty history - nothing to stitch
            return ""

        stitched = await self.stitch(turns)
        return stitched

    async def stitch(self, turns: list[ConversationTurn]) -> str:
        """Stitch multiple conversation turns into a single coherent paragraph.

        Args:
            turns: List of conversation turns to stitch together.

        Returns:
            A coherent paragraph summarizing the conversation context.
        """
        if not turns:
            return ""

        # Format the turns for the LLM
        dialog_text = "\n".join(
            f"{'User' if t.role == 'user' else 'Assistant'}: {t.content}"
            for t in turns
        )

        # Collect all entities and topics for reference
        all_entities: list[str] = []
        all_topics: list[str] = []
        seen_entities: set[str] = set()
        seen_topics: set[str] = set()
        for t in turns:
            for e in t.entities:
                if e not in seen_entities:
                    all_entities.append(e)
                    seen_entities.add(e)
            for tp in t.topics:
                if tp not in seen_topics:
                    all_topics.append(tp)
                    seen_topics.add(tp)

        entity_str = ", ".join(all_entities) if all_entities else "none"
        topic_str = ", ".join(all_topics) if all_topics else "none"

        prompt = (
            "You are a context stitcher. Given the following conversation turns, "
            "produce a single coherent paragraph that summarizes the key context, "
            "entities discussed, and topics covered. This paragraph will be used "
            "to augment the next user query so the LLM has full context.\n\n"
            f"Key entities: {entity_str}\n"
            f"Key topics: {topic_str}\n\n"
            "=== Conversation ===\n"
            f"{dialog_text}\n"
            "=== End Conversation ===\n\n"
            "Coherent context paragraph:"
        )

        try:
            result = await self._llm.generate(prompt)
            return result.strip() if result else ""
        except Exception:
            # Fallback: simple concatenation of key points
            return self._fallback_stitch(turns)

    def _fallback_stitch(self, turns: list[ConversationTurn]) -> str:
        """Fallback stitching without LLM - concatenate recent context."""
        if not turns:
            return ""

        parts: list[str] = []
        for turn in turns[-5:]:
            # Truncate long turns
            content = turn.content
            if len(content) > 200:
                content = content[:200] + "..."
            parts.append(content)

        return " | ".join(parts)
