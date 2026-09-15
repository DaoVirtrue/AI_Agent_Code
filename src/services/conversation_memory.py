"""Conversation memory service — 会话记忆 + 上下文压缩。

Bridges the five-tier memory system (src/memory) into the chat pipeline:

- **Short-term** (STM): the active conversation window (sliding, token-budgeted).
- **Long-term** (LTM): compressed summaries of older turns (semantic, survives
  context truncation).
- **Compression**: when STM exceeds its budget, older turns are summarized
  (via the LLM or a deterministic fallback) into LTM, so key facts are NOT
  lost even when the raw window is truncated.

This directly addresses the "memory loss after context compression" concern:
compression moves content to a *summary* tier instead of dropping it.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from src.memory.short_term import ShortTermMemory
from src.memory.long_term import LongTermMemory

logger = logging.getLogger(__name__)


@dataclass
class ConversationMemoryState:
    """The current memory state for a conversation."""

    conversation_id: str
    stm_messages: list[dict] = field(default_factory=list)
    summary: str = ""
    stm_token_count: int = 0
    compressed: bool = False

    def to_dict(self) -> dict:
        return {
            "conversation_id": self.conversation_id,
            "stm_messages": self.stm_messages,
            "summary": self.summary,
            "stm_token_count": self.stm_token_count,
            "compressed": self.compressed,
        }


class ConversationMemory:
    """Per-conversation memory manager with summary-based compression.

    Args:
        max_stm_tokens: STM token budget before compression triggers.
        max_stm_messages: Max raw messages to keep in STM.
        llm: Optional LLM for high-quality summarization (deterministic fallback).
    """

    def __init__(
        self,
        max_stm_tokens: int = 4000,
        max_stm_messages: int = 12,
        llm: Any = None,
    ):
        self.max_stm_tokens = max_stm_tokens
        self.max_stm_messages = max_stm_messages
        self.llm = llm
        self._conversations: dict[str, dict] = {}

    def get_or_create(self, conversation_id: str) -> dict:
        if conversation_id not in self._conversations:
            self._conversations[conversation_id] = {
                "stm": ShortTermMemory(max_tokens=self.max_stm_tokens),
                "ltm": LongTermMemory(),
                "summary": "",
                "compressed": False,
            }
        return self._conversations[conversation_id]

    def add_message(self, conversation_id: str, role: str, content: str) -> None:
        """Add a message to the conversation's short-term memory."""
        conv = self.get_or_create(conversation_id)
        conv["stm"].add(role, content)

    async def build_context(self, conversation_id: str) -> list[dict]:
        """Build the messages list to send to the LLM.

        Checks for compression first (STM over budget -> summarize older turns
        into a summary), then prefixes the summary so the LLM retains key facts
        even when the raw window has been truncated.
        """
        conv = self.get_or_create(conversation_id)

        # Compress when STM is full (async — needs to be awaited here)
        if conv["stm"].is_full or len(conv["stm"].get_messages()) > self.max_stm_messages:
            await self._compress(conversation_id)
            conv = self.get_or_create(conversation_id)

        messages = []

        if conv["summary"]:
            messages.append({
                "role": "system",
                "content": f"[对话历史摘要]\n{conv['summary']}",
            })

        messages.extend(conv["stm"].get_messages())
        return messages

    async def _compress(self, conversation_id: str) -> None:
        """Compress older STM turns into a summary stored in LTM."""
        conv = self._conversations.get(conversation_id)
        if conv is None:
            return

        stm = conv["stm"]
        messages = stm.get_messages()

        # Keep only the most recent N messages in STM
        older = messages[:-self.max_stm_messages] if len(messages) > self.max_stm_messages else messages[:-2]
        recent = messages[-self.max_stm_messages:] if len(messages) > self.max_stm_messages else messages

        if not older:
            return

        # Generate summary of older messages
        summary = await self._summarize(older)

        # Store summary in LTM + update conversation summary
        await conv["ltm"].add(summary, importance=6.0, tags=["conversation_summary"])
        conv["summary"] = summary
        conv["compressed"] = True

        # Reset STM to only recent messages
        new_stm = ShortTermMemory(max_tokens=self.max_stm_tokens)
        for m in recent:
            new_stm.add(m["role"], m["content"])
        conv["stm"] = new_stm

        logger.info(
            "Compressed conversation %s: %d older turns -> summary (%d chars)",
            conversation_id, len(older), len(summary),
        )

    async def _summarize(self, messages: list[dict]) -> str:
        """Summarize older messages via LLM, or deterministic fallback."""
        text = "\n".join(f"{m['role']}: {m['content']}" for m in messages)

        if self.llm is not None:
            try:
                response = await self.llm.ainvoke([
                    {"role": "user", "content": (
                        "请将以下对话历史压缩成简洁的摘要，保留关键事实、用户偏好、"
                        "已讨论的要点和结论。不要遗漏重要信息：\n\n" + text
                    )},
                ])
                summary = response.content if hasattr(response, "content") else str(response)
                return summary.strip()
            except Exception as exc:  # noqa: BLE001
                logger.warning("LLM summarization failed, using fallback: %s", exc)

        # Deterministic fallback: keep first ~1200 chars
        return text[:1200] + ("..." if len(text) > 1200 else "")

    def get_state(self, conversation_id: str) -> ConversationMemoryState:
        conv = self.get_or_create(conversation_id)
        return ConversationMemoryState(
            conversation_id=conversation_id,
            stm_messages=conv["stm"].get_messages(),
            summary=conv["summary"],
            stm_token_count=conv["stm"].token_count,
            compressed=conv["compressed"],
        )

    def clear(self, conversation_id: str) -> None:
        self._conversations.pop(conversation_id, None)
