"""
Short-term memory with sliding window and token budget.

Implements a FIFO buffer that evicts oldest messages when the token
budget is exceeded. Designed to maintain conversation context within
the LLM's context window limits.
"""

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class STMEntry:
    """A single entry in short-term memory."""
    role: str
    content: str
    timestamp: float = field(default_factory=time.time)
    token_count: int = 0
    metadata: dict = field(default_factory=dict)


class ShortTermMemory:
    """Sliding-window memory buffer with token budget management.

    Maintains a FIFO queue of conversation messages, automatically evicting
    the oldest entries when the total estimated token count exceeds the budget.

    Args:
        max_tokens: Maximum number of tokens to retain (default 8000).
        token_counter: Optional callable that counts tokens in text.
                       Should accept (text: str) -> int.
                       If None, uses a simple whitespace-based heuristic.
    """

    def __init__(self, max_tokens: int = 8000, token_counter=None):
        self.max_tokens = max_tokens
        self._token_counter = token_counter or self._default_token_counter
        self._buffer: deque[STMEntry] = deque()
        self._total_tokens = 0
        self._system_message: STMEntry | None = None

    # ------------------------------------------------------------------
    # Adding messages
    # ------------------------------------------------------------------

    def add(self, role: str, content: str, metadata: dict | None = None) -> None:
        """Add a message to short-term memory.

        Args:
            role: Message role (system, user, assistant, tool, etc.).
            content: Message content text.
            metadata: Optional metadata dict.
        """
        token_count = self._token_counter(content)
        entry = STMEntry(
            role=role,
            content=content,
            token_count=token_count,
            metadata=metadata or {},
        )

        # System messages are kept separately and never evicted
        if role == "system":
            self._system_message = entry
            self._total_tokens += token_count
            return

        self._buffer.append(entry)
        self._total_tokens += token_count

        # Evict if over budget
        self._evict_if_needed()

    def add_batch(self, messages: list[dict]) -> None:
        """Add multiple messages at once.

        Args:
            messages: List of dicts with 'role' and 'content' keys.
        """
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            metadata = msg.get("metadata")
            self.add(role, content, metadata)

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get_messages(self) -> list[dict]:
        """Get all messages as a list of dicts for LLM API consumption.

        System message (if any) is always first.

        Returns:
            List of dicts with 'role' and 'content' keys.
        """
        messages = []

        if self._system_message is not None:
            messages.append({
                "role": self._system_message.role,
                "content": self._system_message.content,
            })

        for entry in self._buffer:
            messages.append({
                "role": entry.role,
                "content": entry.content,
            })

        return messages

    def get_recent(self, n: int) -> list[dict]:
        """Get the n most recent messages.

        Args:
            n: Number of recent messages to return.

        Returns:
            List of dicts with 'role' and 'content' keys.
        """
        messages = self.get_messages()
        return messages[-n:] if n < len(messages) else messages

    def get_turn_count(self) -> int:
        """Return the number of conversation turns (user-assistant pairs)."""
        # Count user messages as a proxy for turns
        return sum(1 for e in self._buffer if e.role == "user")

    # ------------------------------------------------------------------
    # Eviction
    # ------------------------------------------------------------------

    def _evict_if_needed(self) -> None:
        """Evict oldest non-system messages until within token budget.

        Uses FIFO eviction: oldest messages are removed first.
        Maintains at least the last 2 turns if possible.
        """
        safety_turns = 4  # Keep at least the last 2 user+assistant pairs

        # Count how many user messages represent recent turns
        user_count = 0
        for entry in reversed(self._buffer):
            if entry.role == "user":
                user_count += 1
                if user_count >= 2:
                    break

        while self._total_tokens > self.max_tokens and len(self._buffer) > safety_turns:
            # Evict the oldest message
            evicted = self._buffer.popleft()
            self._total_tokens -= evicted.token_count
            logger.debug(
                "Evicted STM entry: role=%s tokens=%d (remaining: %d/%d)",
                evicted.role, evicted.token_count, self._total_tokens, self.max_tokens,
            )

        # If still over budget after keeping minimum turns, log warning
        if self._total_tokens > self.max_tokens:
            logger.warning(
                "STM over budget: %d/%d tokens with %d messages retained",
                self._total_tokens, self.max_tokens, len(self._buffer),
            )

    # ------------------------------------------------------------------
    # Management
    # ------------------------------------------------------------------

    def clear(self) -> None:
        """Clear all messages from short-term memory."""
        self._buffer.clear()
        self._total_tokens = 0
        self._system_message = None

    def clear_except_system(self) -> None:
        """Clear all messages except the system message."""
        self._buffer.clear()
        self._total_tokens = (
            self._system_message.token_count if self._system_message else 0
        )

    @property
    def token_count(self) -> int:
        """Current estimated token count."""
        return self._total_tokens

    @property
    def message_count(self) -> int:
        """Number of messages currently stored."""
        count = len(self._buffer)
        if self._system_message:
            count += 1
        return count

    @property
    def is_full(self) -> bool:
        """Whether the memory is at or near capacity."""
        return self._total_tokens >= self.max_tokens * 0.9

    # ------------------------------------------------------------------
    # Token counting
    # ------------------------------------------------------------------

    @staticmethod
    def _default_token_counter(text: str) -> int:
        """Simple token count heuristic: ~4 characters per token.

        This is a rough approximation. For production use, provide a
        real tokenizer (tiktoken, HuggingFace, etc.).

        Args:
            text: The text to count tokens for.

        Returns:
            Estimated token count.
        """
        if not text:
            return 0
        # Rough: 1 token ≈ 4 chars for English text
        # Add 1 to account for whitespace/formatting
        return max(1, len(text) // 4)

    def __len__(self) -> int:
        return self.message_count

    def __repr__(self) -> str:
        return (
            f"ShortTermMemory(messages={self.message_count}, "
            f"tokens={self._total_tokens}/{self.max_tokens})"
        )
