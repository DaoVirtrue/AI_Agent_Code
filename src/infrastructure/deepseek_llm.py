"""LangChain-compatible DeepSeek LLM adapter.

Provides a minimal ``ainvoke(messages) -> response`` interface used by the RAG
pipeline and the agent patterns. Built directly on ``openai.AsyncOpenAI`` with
``base_url`` pointing at DeepSeek, so no LangChain dependency is required for
the core call path.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class DeepSeekLLM:
    """A minimal LangChain-compatible chat model for DeepSeek.

    Args:
        api_key: DeepSeek API key (falls back to DEEPSEEK_API_KEY env var).
        model: Model id (default ``deepseek-chat``).
        base_url: DeepSeek API base URL.
        temperature: Sampling temperature.
        max_tokens: Max completion tokens.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "deepseek-chat",
        base_url: str = "https://api.deepseek.com",
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ):
        import os

        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

        key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        if not key:
            logger.warning("DeepSeekLLM created without API key; calls will fail")

        try:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(api_key=key, base_url=base_url)
        except ImportError:
            logger.error("openai package not installed; DeepSeekLLM unavailable")
            self._client = None

    async def ainvoke(self, messages: list[dict]) -> Any:
        """Call the DeepSeek chat completions API.

        Args:
            messages: List of ``{"role", "content"}`` dicts.

        Returns:
            An object with a ``.content`` attribute (LangChain-like message).
        """
        if self._client is None:
            raise RuntimeError("DeepSeek client not initialized")

        response = await self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

        return _Message(response.choices[0].message.content)


class _Message:
    """A minimal LangChain-compatible message wrapper."""

    def __init__(self, content: str):
        self.content = content
