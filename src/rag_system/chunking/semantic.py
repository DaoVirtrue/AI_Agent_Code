"""Semantic chunker that splits on paragraph/section boundaries."""

import logging
import re
import numpy as np
from typing import Optional

from .base import BaseChunker, Chunk
from .fixed_size import FixedSizeChunker

logger = logging.getLogger(__name__)


class SemanticChunker(BaseChunker):
    """Split text at semantic boundaries (paragraphs, sections).

    This chunker detects natural text boundaries (double newlines,
    section headers, topic transitions) to create more meaningful
    chunks. Uses a breakpoint percentile approach: identifies candidate
    breakpoints, scores them, and keeps those above a percentile threshold.
    """

    # Section/heading detection patterns
    SECTION_PATTERNS = [
        re.compile(r'^#{1,6}\s+', re.MULTILINE),          # Markdown headers
        re.compile(r'^(?:Chapter|Section|Part)\s+\d+', re.IGNORECASE | re.MULTILINE),
        re.compile(r'^(?:第[一二三四五六七八九十]+[章节部分篇])', re.MULTILINE),  # Chinese
        re.compile(r'^\d+[\.\)]\s+[A-Z]', re.MULTILINE),  # Numbered sections
        re.compile(r'^(?:Abstract|Introduction|Conclusion|References?|Appendix)',
                   re.IGNORECASE | re.MULTILINE),
    ]

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        breakpoint_percentile: float = 0.5,
        min_section_length: int = 50,
    ):
        """Initialize semantic chunker.

        Args:
            chunk_size: Target chunk size
            chunk_overlap: Overlap between chunks
            breakpoint_percentile: Threshold percentile for breakpoint selection
                Lower = more breakpoints (smaller sub-chunks)
                Higher = fewer breakpoints (closer to paragraphs)
            min_section_length: Minimum characters for a standalone section
        """
        super().__init__(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        self.breakpoint_percentile = breakpoint_percentile
        self.min_section_length = min_section_length
        logger.info(
            "SemanticChunker: size=%d, overlap=%d, breakpoint_pct=%.2f",
            chunk_size, chunk_overlap, breakpoint_percentile
        )

    def chunk_text(self, text: str, metadata: Optional[dict] = None) -> list[Chunk]:
        """Split text at semantic boundaries."""
        if not text:
            return []

        meta = metadata or {}

        # Step 1: Split by double newlines (paragraph boundaries)
        paragraphs = re.split(r'\n\s*\n', text)
        paragraphs = [p.strip() for p in paragraphs if p.strip()]

        if not paragraphs:
            return []

        # Step 2: Merge small paragraphs into larger sections
        sections = self._merge_small_sections(paragraphs)

        # Step 3: Create chunks from sections, splitting oversized ones
        chunks = self._create_chunks_from_sections(sections, meta)

        # Step 4: Add overlap metadata
        for i, chunk in enumerate(chunks):
            chunk.metadata["chunk_strategy"] = "semantic"
            chunk.metadata["section_boundary"] = i == 0 or self._is_section_boundary(
                chunks[i-1].text, chunk.text
            )

        return chunks

    def _merge_small_sections(self, paragraphs: list[str]) -> list[str]:
        """Merge paragraphs that are too short into coherent sections."""
        sections = []
        buffer = ""

        for para in paragraphs:
            if len(para) < self.min_section_length:
                buffer = (buffer + "\n\n" + para).strip() if buffer else para
            else:
                if buffer:
                    if len(buffer) < self.min_section_length:
                        combined = (buffer + "\n\n" + para).strip()
                        sections.append(combined)
                    else:
                        sections.append(buffer)
                        sections.append(para)
                    buffer = ""
                else:
                    sections.append(para)

        if buffer:
            if sections and len(buffer) < self.min_section_length:
                sections[-1] = sections[-1] + "\n\n" + buffer
            else:
                sections.append(buffer)

        return sections

    def _create_chunks_from_sections(
        self, sections: list[str], meta: dict
    ) -> list[Chunk]:
        """Create chunks from sections, splitting oversized ones."""
        chunks: list[Chunk] = []
        char_pos = 0

        for section in sections:
            if len(section) <= self.chunk_size:
                chunks.append(Chunk(
                    text=section,
                    index=len(chunks),
                    start_char=char_pos,
                    end_char=char_pos + len(section),
                    metadata={**meta, "chunk_strategy": "semantic"},
                    token_count=self.estimate_tokens(section),
                ))
                char_pos += len(section)
            else:
                # Split oversized section at its internal breakpoints
                sub_chunks = self._split_oversized_section(section, char_pos, meta)
                chunks.extend(sub_chunks)
                char_pos += len(section)

        # Re-index
        for i, chunk in enumerate(chunks):
            chunk.index = i

        return chunks

    def _split_oversized_section(
        self, text: str, base_pos: int, meta: dict
    ) -> list[Chunk]:
        """Split a section that exceeds chunk_size at semantic sub-breakpoints."""
        # Find candidate breakpoints
        sentences = self._get_sentence_breakpoints(text)

        if len(sentences) <= 1:
            # Can't split meaningfully, do fixed-size
            fixed = FixedSizeChunker(
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap,
                respect_word_boundaries=True,
            )
            raw_chunks = fixed.chunk_text(text, meta)
            for c in raw_chunks:
                c.start_char += base_pos
                c.end_char += base_pos
            return raw_chunks

        # Greedy chunking: pack sentences until approaching chunk_size
        chunks: list[Chunk] = []
        current_text = ""
        current_start = 0

        for sent_start, sent_end in sentences:
            sentence = text[sent_start:sent_end]

            if len(current_text) + len(sentence) > self.chunk_size and current_text:
                # Finalize current chunk
                chunks.append(Chunk(
                    text=current_text.strip(),
                    index=len(chunks),
                    start_char=base_pos + current_start,
                    end_char=base_pos + sent_start,
                    metadata={**meta, "chunk_strategy": "semantic"},
                    token_count=self.estimate_tokens(current_text),
                ))
                # Start new chunk with overlap
                overlap_start = max(0, len(current_text) - self.chunk_overlap)
                if overlap_start > 0:
                    overlap_text = current_text[overlap_start:]
                    current_text = overlap_text + sentence
                    current_start = current_start + overlap_start
                else:
                    current_text = sentence
                    current_start = sent_start
            else:
                if not current_text:
                    current_start = sent_start
                current_text += sentence

        if current_text.strip():
            chunks.append(Chunk(
                text=current_text.strip(),
                index=len(chunks),
                start_char=base_pos + current_start,
                end_char=base_pos + len(text),
                metadata={**meta, "chunk_strategy": "semantic"},
                token_count=self.estimate_tokens(current_text),
            ))

        return chunks

    def _get_sentence_breakpoints(self, text: str) -> list[tuple[int, int]]:
        """Split text into sentence-level segments with their positions."""
        # Simple sentence splitting by punctuation
        pattern = re.compile(r'(?<=[.!?。！？\n])\s+')
        segments = []
        pos = 0

        for part in pattern.split(text):
            if part.strip():
                start = text.index(part, pos) if part in text[pos:] else pos
                start = max(start, pos)
                end = start + len(part)
                segments.append((start, end))
                pos = end

        if not segments and text.strip():
            segments.append((0, len(text)))

        return segments

    def _is_section_boundary(self, prev_text: str, current_text: str) -> bool:
        """Check if there's a semantic boundary between two chunks."""
        # Check for section headings at the start of current_text
        for pattern in self.SECTION_PATTERNS:
            if pattern.match(current_text.strip()):
                return True

        # Check for topic shift (simple approach)
        prev_words = set(prev_text.lower().split())
        curr_words = set(current_text.lower().split())

        if prev_words and curr_words:
            overlap = len(prev_words & curr_words) / min(len(prev_words), len(curr_words))
            # Low word overlap suggests topic shift
            if overlap < 0.1:
                return True

        return False
