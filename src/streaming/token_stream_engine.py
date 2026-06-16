"""Token-by-token streaming engine for simulating LLM output.

Provides configurable-delay streaming with support for interruption
via asyncio.Event signals, useful for demos, testing, and as a
stand-in before a real LLM backend is integrated.
"""

from __future__ import annotations

import asyncio
import re
from typing import AsyncIterator


class TokenStreamEngine:
    """Simulate token-by-token LLM output for demo and testing.

    Splits text into token-like chunks using whitespace and punctuation
    boundaries, then yields them one at a time with a configurable delay.
    Supports interruption via asyncio.Event.

    Usage:
        engine = TokenStreamEngine(delay_ms=30)
        async for token in engine.stream_text("Hello, world!"):
            print(token, end="", flush=True)
    """

    _TOKEN_SPLIT_PATTERN = re.compile(
        r'(\s+)|'
        r'([。，！？；：、""''（）【】《》\n])|'
        r'([.!?;,:()\[\]{}"\'\n])|'
        r'(\S+)'
    )

    def __init__(self, delay_ms: int = 50) -> None:
        """Initialize the token stream engine.

        Args:
            delay_ms: Delay in milliseconds between yielding tokens.
                      Use 0 for no delay (instant streaming).
        """
        self._delay_ms = max(0, delay_ms)
        self._delay_seconds = self._delay_ms / 1000.0

    async def stream_text(self, text: str) -> AsyncIterator[str]:
        """Stream text token by token with configurable delay.

        Args:
            text: The full text to stream token-by-token.

        Yields:
            Individual token strings at the configured interval.
        """
        tokens = self._tokenize(text)
        for token in tokens:
            if self._delay_seconds > 0:
                await asyncio.sleep(self._delay_seconds)
            yield token

    async def stream_with_interrupt(
        self, text: str, interrupt_signal: asyncio.Event
    ) -> AsyncIterator[str]:
        """Stream text token by token, checking an interrupt signal.

        If the interrupt signal is set between tokens, streaming
        stops immediately and no further tokens are yielded.

        Args:
            text: The full text to stream.
            interrupt_signal: An asyncio.Event; if set, streaming halts.

        Yields:
            Individual token strings, unless interrupted.
        """
        tokens = self._tokenize(text)
        for token in tokens:
            if interrupt_signal.is_set():
                break
            if self._delay_seconds > 0:
                # Use wait_for on the event instead of sleep to be
                # responsive to interrupts during the delay
                try:
                    await asyncio.wait_for(
                        interrupt_signal.wait(),
                        timeout=self._delay_seconds,
                    )
                    # If we get here, the signal was set during the delay
                    break
                except asyncio.TimeoutError:
                    # Timeout means delay elapsed without interruption
                    pass
            yield token

    def _tokenize(self, text: str) -> list[str]:
        """Split text into token-like chunks for streaming simulation.

        Breaks on whitespace, punctuation, and natural boundaries
        while preserving all characters.

        Args:
            text: Input text to tokenize.

        Returns:
            List of token strings.
        """
        if not text:
            return []

        tokens: list[str] = []
        for match in self._TOKEN_SPLIT_PATTERN.finditer(text):
            token = match.group(0)
            if token:
                tokens.append(token)

        # If no tokens were extracted (e.g., single character), return as-is
        if not tokens:
            tokens = list(text)

        return tokens

    async def stream_chunks(self, text: str, chunk_size: int = 3) -> AsyncIterator[str]:
        """Stream text in multi-token chunks.

        Args:
            text: The full text to stream.
            chunk_size: Number of tokens per chunk.

        Yields:
            Chunk strings at the configured interval.
        """
        tokens = self._tokenize(text)
        for i in range(0, len(tokens), chunk_size):
            if self._delay_seconds > 0:
                await asyncio.sleep(self._delay_seconds)
            yield "".join(tokens[i:i + chunk_size])

    @property
    def delay_ms(self) -> int:
        """Current delay in milliseconds."""
        return self._delay_ms

    @delay_ms.setter
    def delay_ms(self, value: int) -> None:
        """Set the delay in milliseconds."""
        self._delay_ms = max(0, value)
        self._delay_seconds = self._delay_ms / 1000.0
