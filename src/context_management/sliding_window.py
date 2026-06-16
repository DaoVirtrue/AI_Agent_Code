"""Sliding window truncation for context management.

FIFO-based truncation that preserves system messages and drops oldest
messages first when the context budget is exceeded.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class SlidingWindowTruncator:
    """FIFO message truncation for context window compliance.

    Always preserves the system message(s). Drops non-system messages
    from the oldest end until the token budget fits.

    Usage::

        truncator = SlidingWindowTruncator(token_counter)
        truncated = truncator.truncate(
            messages, model="gpt-4o", max_tokens=100000, preserve_system=True
        )
    """

    def __init__(self, token_counter: Any) -> None:
        """Initialize with a token counter.

        Args:
            token_counter: TokenCounter instance for accurate token counting.
        """
        self.token_counter = token_counter

    def truncate(
        self,
        messages: list[dict[str, Any]],
        model: str,
        max_tokens: int | None = None,
        preserve_system: bool = True,
    ) -> list[dict[str, Any]]:
        """Truncate messages to fit within a token budget using FIFO strategy.

        Args:
            messages: Original messages list.
            model: Model identifier for token counting.
            max_tokens: Maximum tokens allowed. If None, uses model's default
                context window size.
            preserve_system: If True, system messages are never dropped.

        Returns:
            Truncated messages list.
        """
        if not messages:
            return []

        if max_tokens is None:
            from src.context_management.window_manager import ContextWindowManager

            wm = ContextWindowManager()
            max_tokens = wm.get_window(model)

        # Separate system and non-system messages
        system_msgs = [m for m in messages if m.get("role") == "system"]
        non_system_msgs = [m for m in messages if m.get("role") != "system"]

        # Count tokens in system messages
        system_tokens = sum(
            self._count_message(msg, model) for msg in system_msgs
        )

        remaining_budget = max_tokens - system_tokens
        if remaining_budget <= 0:
            logger.warning(
                "System messages alone (%d tokens) exceed budget (%d tokens). "
                "Keeping system messages but budget is overshot.",
                system_tokens,
                max_tokens,
            )
            return system_msgs

        # Build result by including messages from the end (most recent first)
        # using a reverse FIFO — keep newest, drop oldest
        kept: list[dict[str, Any]] = []
        tokens_used = 0

        for msg in reversed(non_system_msgs):
            msg_tokens = self._count_message(msg, model)
            if tokens_used + msg_tokens <= remaining_budget:
                kept.append(msg)
                tokens_used += msg_tokens
            else:
                # Try to trim the message content if possible
                trimmed = self._trim_message(msg, model, remaining_budget - tokens_used)
                if trimmed is not None:
                    kept.append(trimmed)
                break

        # Restore correct order: system first, then kept messages in original order
        kept.reverse()

        result = system_msgs if preserve_system else []
        result.extend(kept)

        if len(non_system_msgs) > len(kept):
            dropped = len(non_system_msgs) - len(kept)
            logger.info(
                "Sliding window truncated %d messages (kept %d, dropped %d oldest)",
                len(messages),
                len(result),
                dropped,
            )

        return result

    def fit_to_window(
        self,
        messages: list[dict[str, Any]],
        model: str,
        target_fill_pct: float = 0.80,
    ) -> list[dict[str, Any]]:
        """Truncate to fill a target percentage of the context window.

        Args:
            messages: Original messages list.
            model: Model identifier.
            target_fill_pct: Target fill percentage (0.0 to 1.0).

        Returns:
            Truncated messages list.
        """
        from src.context_management.window_manager import ContextWindowManager

        wm = ContextWindowManager()
        full_window = wm.get_window(model)
        max_tokens = int(full_window * target_fill_pct)

        return self.truncate(messages, model, max_tokens=max_tokens, preserve_system=True)

    def truncate_by_turns(
        self,
        messages: list[dict[str, Any]],
        model: str,
        max_turns: int,
        preserve_system: bool = True,
    ) -> list[dict[str, Any]]:
        """Truncate by conversation turn count instead of token count.

        A "turn" is a user-assistant pair.

        Args:
            messages: Original messages list.
            model: Model identifier.
            max_turns: Maximum number of turns to keep.
            preserve_system: Whether to preserve system messages.

        Returns:
            Truncated messages list.
        """
        if not messages:
            return []

        system_msgs = [m for m in messages if m.get("role") == "system"]
        non_system = [m for m in messages if m.get("role") != "system"]

        # Group into turns (user + assistant pairs)
        turns: list[list[dict[str, Any]]] = []
        current_turn: list[dict[str, Any]] = []

        for msg in non_system:
            role = msg.get("role", "user")
            if role == "user" and current_turn:
                turns.append(current_turn)
                current_turn = []
            current_turn.append(msg)

        if current_turn:
            turns.append(current_turn)

        # Keep only the last max_turns turns
        if len(turns) > max_turns:
            turns = turns[-max_turns:]

        result = system_msgs if preserve_system else []
        for turn in turns:
            result.extend(turn)

        return result

    def _count_message(self, msg: dict[str, Any], model: str) -> int:
        """Count tokens for a single message."""
        content = msg.get("content", "")
        if isinstance(content, str):
            return self.token_counter.count(content, model)
        if isinstance(content, list):
            total = 0
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    total += self.token_counter.count(part.get("text", ""), model)
                elif isinstance(part, str):
                    total += self.token_counter.count(part, model)
            return total if total > 0 else self.token_counter.count(str(content), model)
        return self.token_counter.count(str(content), model)

    def _trim_message(
        self,
        msg: dict[str, Any],
        model: str,
        max_tokens: int,
    ) -> dict[str, Any] | None:
        """Attempt to trim a message to fit within a token budget.

        Returns trimmed message or None if it cannot be trimmed.
        """
        if max_tokens <= 0:
            return None

        content = msg.get("content", "")
        if not isinstance(content, str):
            return None

        # Character-based trimming: approximate tokens → chars
        # Conservative estimate: 1 token ≈ 3 chars
        max_chars = max_tokens * 3
        if len(content) <= max_chars:
            return msg

        trimmed = content[:max_chars] + " ... [truncated]"
        return {**msg, "content": trimmed}
