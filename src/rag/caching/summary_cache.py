"""L3 Cache: Conversation summary cache.

Caches compressed summaries of conversation threads for faster
context retrieval in multi-turn dialogues.
"""

import time
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class SummaryCache:
    """L3 cache - conversation summary caching.

    For multi-turn conversations, caches compressed summaries
    rather than full conversation history. When a new message
    arrives, the cached summary + recent messages provides
    a compact context window.

    Properties:
    - Session-based (keyed by conversation_id)
    - Sliding window of recent messages
    - Auto-summarization trigger on length threshold
    - TTL for stale conversations
    """

    def __init__(
        self,
        max_conversations: int = 1000,
        max_message_window: int = 20,
        summary_trigger_length: int = 15,
        ttl_seconds: int = 86400,  # 24 hours
    ):
        """Initialize summary cache.

        Args:
            max_conversations: Max active conversations
            max_message_window: Recent messages to keep in full
            summary_trigger_length: Messages before triggering summarization
            ttl_seconds: Expire inactive conversations
        """
        self.max_conversations = max_conversations
        self.max_message_window = max_message_window
        self.summary_trigger_length = summary_trigger_length
        self.ttl_seconds = ttl_seconds

        self._conversations: dict[str, dict] = {}
        logger.info("SummaryCache: max_convs=%d, window=%d", max_conversations, max_message_window)

    def get_context(self, conversation_id: str) -> dict:
        """Get cached context for a conversation.

        Returns {summary, recent_messages, metadata}.
        """
        if conversation_id not in self._conversations:
            return {"summary": "", "recent_messages": [], "metadata": {}}

        conv = self._conversations[conversation_id]

        # Check TTL
        if time.time() - conv.get("last_access", 0) > self.ttl_seconds:
            self._conversations.pop(conversation_id, None)
            return {"summary": "", "recent_messages": [], "metadata": {}}

        conv["last_access"] = time.time()

        return {
            "summary": conv.get("summary", ""),
            "recent_messages": conv.get("messages", [])[-self.max_message_window:],
            "metadata": conv.get("metadata", {}),
            "message_count": len(conv.get("messages", [])),
        }

    def add_message(
        self, conversation_id: str, role: str, content: str, metadata: Optional[dict] = None
    ) -> None:
        """Add a message to a conversation's cache.

        Auto-triggers summarization if the message count exceeds threshold.
        """
        if conversation_id not in self._conversations:
            if len(self._conversations) >= self.max_conversations:
                self._evict_oldest()
            self._conversations[conversation_id] = {
                "messages": [],
                "summary": "",
                "metadata": {},
                "last_access": time.time(),
            }

        conv = self._conversations[conversation_id]
        conv["messages"].append({
            "role": role,
            "content": content,
            "timestamp": time.time(),
            "metadata": metadata or {},
        })
        conv["last_access"] = time.time()

        # Trigger summarization if threshold exceeded
        if len(conv["messages"]) > self.summary_trigger_length:
            self._trigger_summarization(conversation_id)

    def update_summary(self, conversation_id: str, summary: str) -> None:
        """Manually update the cached summary for a conversation."""
        if conversation_id in self._conversations:
            self._conversations[conversation_id]["summary"] = summary
            self._conversations[conversation_id]["last_access"] = time.time()

    def _trigger_summarization(self, conversation_id: str) -> None:
        """Auto-generate a basic summary from recent messages."""
        conv = self._conversations.get(conversation_id)
        if not conv:
            return

        messages = conv["messages"]

        # Keep last N messages in full, summarize the rest
        split_point = max(0, len(messages) - self.max_message_window)
        to_summarize = messages[:split_point]

        if not to_summarize:
            return

        # Simple summary: concatenate user queries
        user_messages = [m["content"][:200] for m in to_summarize if m["role"] == "user"]
        summary = "Previous conversation summary:\n" + "\n".join(
            f"- {msg}" for msg in user_messages[-10:]
        )

        conv["summary"] = summary

        # Trim old messages to save memory
        if len(messages) > self.max_message_window * 2:
            conv["messages"] = messages[-self.max_message_window:]

        logger.debug("Summarized conversation %s: %d messages condensed",
                     conversation_id[:8], len(to_summarize))

    def delete_conversation(self, conversation_id: str) -> bool:
        """Delete a conversation from cache."""
        if conversation_id in self._conversations:
            del self._conversations[conversation_id]
            return True
        return False

    def _evict_oldest(self) -> None:
        """Evict the least recently accessed conversation."""
        if not self._conversations:
            return
        oldest_id = min(
            self._conversations,
            key=lambda cid: self._conversations[cid].get("last_access", 0)
        )
        del self._conversations[oldest_id]

    def clear(self) -> None:
        """Clear all conversations."""
        self._conversations.clear()
        logger.info("SummaryCache cleared")

    def stats(self) -> dict:
        active = sum(1 for c in self._conversations.values()
                    if time.time() - c.get("last_access", 0) < self.ttl_seconds)
        return {
            "total_conversations": len(self._conversations),
            "active_conversations": active,
            "max_conversations": self.max_conversations,
            "ttl_seconds": self.ttl_seconds,
        }
