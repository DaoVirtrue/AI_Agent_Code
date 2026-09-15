"""Recursive character text splitter (LangChain-compatible wrapper)."""

import logging
import re
from typing import Optional

from .base import BaseChunker, Chunk

logger = logging.getLogger(__name__)


class RecursiveChunker(BaseChunker):
    """Recursive character text splitter.

    Tries to split on progressively smaller separators until chunks
    fit the desired size. This is the approach used by LangChain's
    RecursiveCharacterTextSplitter.

    Separator priority (tried in order):
    1. Double newline (paragraphs)
    2. Single newline
    3. Period + space (sentences)
    4. Other punctuation + space
    5. Space (words)
    6. Empty string (characters)
    """

    DEFAULT_SEPARATORS = ["\n\n", "\n", ". ", "。 ", "! ", "? ", "； ", "; ", ", ", "， ", " ", ""]

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        separators: Optional[list[str]] = None,
        keep_separator: bool = True,
        strip_whitespace: bool = True,
    ):
        """Initialize recursive chunker.

        Args:
            chunk_size: Target chunk size
            chunk_overlap: Overlap between chunks
            separators: Ordered list of separators to try (most to least specific)
            keep_separator: Include separator in chunk (at the end)
            strip_whitespace: Strip whitespace from chunks
        """
        super().__init__(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        self.separators = separators or self.DEFAULT_SEPARATORS
        self.keep_separator = keep_separator
        self.strip_whitespace = strip_whitespace
        logger.info("RecursiveChunker: size=%d, overlap=%d, separators=%d",
                     chunk_size, chunk_overlap, len(self.separators))

    def chunk_text(self, text: str, metadata: Optional[dict] = None) -> list[Chunk]:
        """Split text recursively using the separator hierarchy."""
        if not text:
            return []

        meta = metadata or {}

        # Do the recursive split
        splits = self._split_text(text, self.separators)

        # Merge splits into chunks with overlap
        chunks = self._merge_splits(splits, meta)

        # Re-index
        for i, chunk in enumerate(chunks):
            chunk.index = i
            chunk.metadata["chunk_strategy"] = "recursive"

        return chunks

    def _split_text(self, text: str, separators: list[str]) -> list[str]:
        """Recursively split text using the separator hierarchy."""
        final_chunks: list[str] = []

        # Get the most appropriate separator
        separator = separators[-1]  # Fallback to empty string (character split)
        next_separators = []

        for i, sep in enumerate(separators):
            if sep == "":
                separator = sep
                break
            if sep in text:
                separator = sep
                next_separators = separators[i + 1:]
                break

        # Split by chosen separator
        if separator == "":
            # Character-level split
            for i in range(0, len(text), self.chunk_size - self.chunk_overlap):
                chunk = text[i:i + self.chunk_size]
                if chunk:
                    final_chunks.append(chunk)
            return final_chunks

        # Split by the found separator
        splits = text.split(separator)

        current_chunk = ""
        for i, split in enumerate(splits):
            piece = split + (separator if self.keep_separator and i < len(splits) - 1 else "")

            if len(current_chunk) + len(piece) <= self.chunk_size:
                current_chunk += piece
            else:
                # Current chunk is full, start new one
                if current_chunk:
                    final_chunks.append(current_chunk)

                # If the piece itself is too large, recurse
                if len(piece) > self.chunk_size:
                    if next_separators:
                        sub_chunks = self._split_text(piece, next_separators)
                        final_chunks.extend(sub_chunks)
                    else:
                        # Last resort: character split
                        for j in range(0, len(piece), self.chunk_size):
                            final_chunks.append(piece[j:j + self.chunk_size])
                else:
                    current_chunk = piece

        if current_chunk:
            final_chunks.append(current_chunk)

        return final_chunks

    def _merge_splits(self, splits: list[str], meta: dict) -> list[Chunk]:
        """Merge splits into final chunks with overlap, tracking character positions."""
        chunks: list[Chunk] = []
        char_pos = 0

        for i, split in enumerate(splits):
            text = split.strip() if self.strip_whitespace else split

            if not text:
                char_pos += len(split)
                continue

            chunk = Chunk(
                text=text,
                index=len(chunks),
                start_char=char_pos,
                end_char=char_pos + len(split),
                metadata={**meta, "chunk_strategy": "recursive"},
                token_count=self.estimate_tokens(text),
            )
            chunks.append(chunk)
            char_pos += len(split)

        return chunks
