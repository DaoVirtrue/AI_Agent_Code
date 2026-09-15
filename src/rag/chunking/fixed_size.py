"""Fixed-size chunker with overlap."""

import logging
from typing import Optional

from .base import BaseChunker, Chunk

logger = logging.getLogger(__name__)


class FixedSizeChunker(BaseChunker):
    """Split text into fixed-size chunks with configurable overlap.

    Splits on character boundaries by default, optionally respects
    word boundaries for cleaner chunk breaks.
    """

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        respect_word_boundaries: bool = True,
        length_function: str = "chars",  # "chars" or "tokens"
    ):
        """Initialize fixed-size chunker.

        Args:
            chunk_size: Target size of each chunk
            chunk_overlap: Number of characters/tokens to overlap
            respect_word_boundaries: Try to break at word boundaries
            length_function: "chars" or "tokens" for length measurement
        """
        super().__init__(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        self.respect_word_boundaries = respect_word_boundaries
        self.length_function = length_function
        logger.info("FixedSizeChunker: size=%d, overlap=%d, word_boundaries=%s",
                     chunk_size, chunk_overlap, respect_word_boundaries)

    def chunk_text(self, text: str, metadata: Optional[dict] = None) -> list[Chunk]:
        """Split text into fixed-size overlapping chunks."""
        if not text:
            return []
        
        meta = metadata or {}
        chunks: list[Chunk] = []
        text_length = len(text)
        
        if text_length <= self.chunk_size:
            chunk = Chunk(
                text=text,
                index=0,
                start_char=0,
                end_char=text_length,
                metadata=meta.copy(),
                token_count=self.estimate_tokens(text),
            )
            return [chunk]
        
        start = 0
        while start < text_length:
            end = min(start + self.chunk_size, text_length)
            
            # Try to break at word boundary if enabled
            if self.respect_word_boundaries and end < text_length:
                # Look backwards from end for a space to break at
                for i in range(min(self.chunk_size // 10, 100), 0, -1):
                    if end - i > start and text[end - i] in " \n\t":
                        end = end - i
                        break
            
            chunk_text_slice = text[start:end]
            
            chunk = Chunk(
                text=chunk_text_slice,
                index=len(chunks),
                start_char=start,
                end_char=end,
                metadata={**meta, "chunk_strategy": "fixed_size"},
                token_count=self.estimate_tokens(chunk_text_slice),
            )
            chunks.append(chunk)
            
            # Advance with overlap
            start = end - self.chunk_overlap
            
            # Prevent infinite loop if overlap >= chunk_size (shouldn't happen due to validation)
            if start >= text_length:
                break
        
        return chunks

    def chunk_by_tokens(
        self, text: str, tokenizer=None, metadata: Optional[dict] = None
    ) -> list[Chunk]:
        """Split text by approximate token count (if tokenizer provided)."""
        if not text:
            return []
        
        meta = metadata or {}
        
        if tokenizer:
            tokens = tokenizer.encode(text)
            chunk_size_tokens = self.chunk_size
        else:
            # Approximate: 4 chars per token
            tokens = text
            chunk_size_tokens = self.chunk_size * 4
        
        chunks: list[Chunk] = []
        
        for i in range(0, len(tokens), chunk_size_tokens - self.chunk_overlap):
            token_slice = tokens[i:i + chunk_size_tokens]
            if tokenizer:
                chunk_text = tokenizer.decode(token_slice)
            else:
                chunk_text = token_slice if isinstance(token_slice, str) else str(token_slice)
            
            chunk = Chunk(
                text=chunk_text,
                index=len(chunks),
                start_char=i,
                end_char=min(i + chunk_size_tokens, len(tokens)),
                metadata={**meta, "chunk_strategy": "fixed_tokens"},
                token_count=len(token_slice),
            )
            chunks.append(chunk)
        
        return chunks
