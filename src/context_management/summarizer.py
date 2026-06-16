"""Conversation history summarization via LLM.

Generates concise summaries of conversation history to compress context,
enabling longer conversations without exceeding token limits.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class LLMClient(Protocol):
    """Protocol for LLM clients used by HistorySummarizer."""

    async def generate(self, prompt: str, max_tokens: int) -> str: ...


class HistorySummarizer:
    """Summarize conversation history using an LLM.

    Converts verbose conversation history into a compact summary string
    that preserves key facts, decisions, and context while dramatically
    reducing token usage (typically 10-20x compression).

    Usage::

        summarizer = HistorySummarizer(llm_client)
        summary = await summarizer.summarize(messages, max_summary_tokens=500)
    """

    DEFAULT_SUMMARY_PROMPT: str = (
        "Summarize the following conversation history concisely. "
        "Focus on:\n"
        "1. Key decisions made by the user and assistant\n"
        "2. Facts and information exchanged\n"
        "3. Actions taken or pending\n"
        "4. Important context that a new participant would need\n"
        "5. Any constraints, preferences, or requirements mentioned\n\n"
        "Format as a compact narrative. Use bullet points only when appropriate. "
        "Exclude pleasantries, fillers, and redundant back-and-forth.\n\n"
        "Conversation:\n{conversation}\n\n"
        "Summary:"
    )

    TURN_SUMMARY_PROMPT: str = (
        "Summarize the following conversation turn in a single sentence. "
        "Capture the user's request/intent and the assistant's response/action:\n\n"
        "{turn}\n\n"
        "One-sentence summary:"
    )

    def __init__(self, llm_client: Any) -> None:
        """Initialize with an LLM client.

        Args:
            llm_client: An object with an async `generate(prompt, max_tokens)` method.
                Compatible with LangChain, OpenAI, and Anthropic clients.
        """
        self.llm_client = llm_client

    async def summarize(
        self,
        messages: list[dict[str, Any]],
        max_summary_tokens: int = 500,
    ) -> str:
        """Generate a single summary for the entire conversation history.

        Args:
            messages: List of message dicts to summarize.
            max_summary_tokens: Maximum tokens for the summary output.

        Returns:
            Compressed summary string.
        """
        if not messages:
            return ""

        conversation_text = self._format_messages(messages)
        prompt = self._build_summary_prompt(conversation_text)

        try:
            summary = await self.llm_client.generate(prompt, max_summary_tokens)
            return summary.strip()
        except Exception as exc:
            logger.error("Summary generation failed: %s, falling back to extraction", exc)
            return self._extract_fallback(messages)

    async def summarize_turns(self, turns: list[dict[str, Any]]) -> list[str]:
        """Generate per-turn summaries (one sentence each).

        Args:
            turns: List of conversation turns. Each turn is a list of
                one or more messages (user + assistant).

        Returns:
            List of one-sentence summaries, one per turn.
        """
        summaries: list[str] = []

        for turn in turns:
            if not turn:
                continue

            if isinstance(turn, dict):
                turn_content = self._format_single_message(turn)
            elif isinstance(turn, list):
                turn_content = self._format_messages(turn)
            else:
                continue

            prompt = self.TURN_SUMMARY_PROMPT.format(turn=turn_content)

            try:
                result = await self.llm_client.generate(prompt, 80)
                summaries.append(result.strip())
            except Exception as exc:
                logger.warning("Per-turn summary failed: %s", exc)
                summaries.append(self._extract_fallback_line(turn_content))

        return summaries

    async def progressive_summary(
        self,
        messages: list[dict[str, Any]],
        compress_ratio: float = 0.2,
    ) -> str:
        """Progressively compress a summary: expensive but high-quality.

        Splits messages into chunks, summarizes each, then summarizes
        the summaries.

        Args:
            messages: Messages to summarize.
            compress_ratio: Target compression ratio (0.0 to 1.0).

        Returns:
            Final compressed summary.
        """
        if not messages:
            return ""

        conversation_text = self._format_messages(messages)

        # If the text is short enough, summarize directly
        if len(conversation_text) < 4000:
            target_tokens = max(100, int(len(conversation_text) // 4 * compress_ratio))
            return await self.summarize(messages, target_tokens)

        # Chunk into ~2000 char pieces and summarize each
        chunk_size = 2000
        chunks = [
            conversation_text[i : i + chunk_size]
            for i in range(0, len(conversation_text), chunk_size)
        ]

        chunk_summaries: list[str] = []
        for chunk in chunks:
            chunk_msgs = [{"role": "user", "content": chunk}]
            summary = await self.summarize(chunk_msgs, 200)
            chunk_summaries.append(summary)

        # Combine chunk summaries and do a final pass
        combined = " ".join(chunk_summaries)
        combined_msgs = [{"role": "user", "content": combined}]
        final_summary = await self.summarize(
            combined_msgs,
            max(100, int(len(combined) // 4 * compress_ratio)),
        )
        return final_summary.strip()

    def _build_summary_prompt(self, conversation: str) -> str:
        """Build the summary prompt from conversation text.

        Args:
            conversation: Formatted conversation text.

        Returns:
            Complete prompt string.
        """
        return self.DEFAULT_SUMMARY_PROMPT.format(conversation=conversation)

    def _format_messages(self, messages: list[dict[str, Any]]) -> str:
        """Format a list of messages into a readable text block.

        Args:
            messages: List of message dicts.

        Returns:
            Formatted text string.
        """
        lines: list[str] = []
        for msg in messages:
            lines.append(self._format_single_message(msg))
        return "\n".join(lines)

    @staticmethod
    def _format_single_message(msg: dict[str, Any]) -> str:
        """Format a single message dict to text.

        Args:
            msg: Message dict with 'role' and 'content'.

        Returns:
            Formatted string like "User: Hello".
        """
        role = msg.get("role", "unknown").capitalize()
        content = msg.get("content", "")

        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, dict):
                    if part.get("type") == "text":
                        parts.append(part.get("text", ""))
                    elif part.get("type") == "image_url":
                        parts.append("[image]")
                    else:
                        parts.append(str(part))
                elif isinstance(part, str):
                    parts.append(part)
            text = " ".join(parts)
        else:
            text = str(content)

        # Truncate very long individual messages for summarization
        if len(text) > 3000:
            text = text[:3000] + " ... [message truncated for summary]"

        return f"{role}: {text}"

    def _extract_key_points(self, summary: str) -> list[str]:
        """Extract key bullet points from a summary string.

        Args:
            summary: Summary text that may contain bullet points.

        Returns:
            List of key point strings.
        """
        # Match lines starting with common bullet markers
        bullet_pattern = re.compile(
            r"^\s*(?:[-*•]|\d+[.)]\s+)(.+)$",
            re.MULTILINE,
        )
        matches = bullet_pattern.findall(summary)

        if matches:
            return [m.strip() for m in matches]

        # If no bullet points found, split on sentences as fallback
        sentences = re.split(r"(?<=[.!?])\s+", summary)
        return [s.strip() for s in sentences if len(s.strip()) > 20]

    @staticmethod
    def _extract_fallback(messages: list[dict[str, Any]]) -> str:
        """Fallback extraction when LLM summarization fails.

        Picks the first and last meaningful messages as a crude summary.

        Args:
            messages: List of message dicts.

        Returns:
            Fallback summary string.
        """
        if not messages:
            return "No conversation history."

        meaningful = [
            m for m in messages
            if m.get("content") and m.get("role") not in ("system",)
        ]

        if len(meaningful) <= 2:
            return "Short conversation: " + (
                meaningful[0].get("content", "")[:200] if meaningful else ""
            )

        first_content = meaningful[0].get("content", "")
        last_content = meaningful[-1].get("content", "")

        return (
            f"Conversation started with: {first_content[:150]}... "
            f"Ended with: {last_content[:150]}..."
        )

    @staticmethod
    def _extract_fallback_line(text: str) -> str:
        """Extract a one-line fallback from text."""
        clean = text.strip()
        if len(clean) <= 120:
            return clean
        return clean[:117] + "..."
