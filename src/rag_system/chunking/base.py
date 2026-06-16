"""Abstract base class for all chunking strategies."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Chunk:
    """A single text chunk with metadata."""
    text: str
    index: int
    start_char: int
    end_char: int
    metadata: dict[str, Any] = field(default_factory=dict)
    token_count: int = 0

    def __len__(self) -> int:
        return len(self.text)

    def __repr__(self) -> str:
        return f"Chunk(idx={self.index}, chars={len(self.text)}, tokens={self.token_count})"


class BaseChunker(ABC):
    """Abstract base class for text chunking strategies.

    All chunkers must implement chunk_text() which takes a text string
    and returns a list of Chunk objects.
    """

    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200):
        """Initialize chunker with size and overlap parameters."""
        if chunk_overlap >= chunk_size:
            raise ValueError(
                f"chunk_overlap ({chunk_overlap}) must be less than chunk_size ({chunk_size})"
            )
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    @abstractmethod
    def chunk_text(self, text: str, metadata: Optional[dict] = None) -> list[Chunk]:
        """Split text into chunks. Subclasses must implement."""
        ...

    def estimate_tokens(self, text: str) -> int:
        """Rough token count estimate (~4 chars per token for English)."""
        return len(text) // 4

    def merge_small_chunks(
        self, chunks: list[Chunk], min_chunk_size: int = 100
    ) -> list[Chunk]:
        """Merge chunks smaller than min_chunk_size with neighbors."""
        if not chunks:
            return []
        
        merged = []
        buffer = None
        
        for chunk in chunks:
            if len(chunk.text) < min_chunk_size:
                if buffer is None:
                    buffer = chunk
                else:
                    # Merge into buffer
                    buffer.text = buffer.text + "\n\n" + chunk.text
                    buffer.end_char = chunk.end_char
                    buffer.token_count = self.estimate_tokens(buffer.text)
            else:
                if buffer is not None:
                    # Try to merge small buffer with current chunk
                    if len(buffer.text) < min_chunk_size:
                        buffer.text = buffer.text + "\n\n" + chunk.text
                        buffer.end_char = chunk.end_char
                        buffer.token_count = self.estimate_tokens(buffer.text)
                        merged.append(buffer)
                        buffer = None
                        continue
                    else:
                        merged.append(buffer)
                        buffer = None
                merged.append(chunk)
        
        if buffer is not None:
            merged.append(buffer)
        
        # Re-index
        for i, chunk in enumerate(merged):
            chunk.index = i
        
        return merged

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(chunk_size={self.chunk_size}, overlap={self.chunk_overlap})"
