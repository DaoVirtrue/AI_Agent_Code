"""Markdown header-aware chunking strategy."""

import logging
import re
from typing import Optional

from .base import BaseChunker, Chunk

logger = logging.getLogger(__name__)


class MarkdownChunker(BaseChunker):
    """Split Markdown documents preserving header hierarchy.

    Respects the document structure defined by Markdown headers (# ## ### etc.)
    and splits content at section boundaries whenever possible. Falls back
    to recursive splitting for oversized sections.

    Each chunk retains the header path (breadcrumb) for context.
    """

    HEADER_PATTERN = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)
    CODE_BLOCK_PATTERN = re.compile(r'```.*?```', re.DOTALL)

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        max_heading_level: int = 3,
        include_header_context: bool = True,
    ):
        """Initialize Markdown header-aware chunker.

        Args:
            chunk_size: Target chunk size in characters
            chunk_overlap: Overlap between chunks
            max_heading_level: Maximum header level to use as split points
            include_header_context: Prepend header breadcrumb to each chunk
        """
        super().__init__(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        self.max_heading_level = max_heading_level
        self.include_header_context = include_header_context
        logger.info(
            "MarkdownChunker: size=%d, overlap=%d, max_heading=%d",
            chunk_size, chunk_overlap, max_heading_level
        )

    def chunk_text(self, text: str, metadata: Optional[dict] = None) -> list[Chunk]:
        """Split markdown text, preserving header hierarchy."""
        if not text:
            return []

        meta = metadata or {}

        # Parse document structure
        sections = self._parse_sections(text)

        if not sections:
            return []

        # Create chunks from sections
        chunks: list[Chunk] = []

        for section in sections:
            header_path = section["header_path"]
            content = section["content"]
            level = section["level"]
            start = section["start"]
            end = section["end"]

            if self.include_header_context and header_path:
                contextualized = f"{header_path}\n\n{content}"
            else:
                contextualized = content

            if len(contextualized) <= self.chunk_size:
                chunks.append(Chunk(
                    text=contextualized,
                    index=len(chunks),
                    start_char=start,
                    end_char=end,
                    metadata={
                        **meta,
                        "chunk_strategy": "markdown",
                        "header_level": level,
                        "header_path": header_path,
                    },
                    token_count=self.estimate_tokens(contextualized),
                ))
            else:
                # Oversized section - split recursively
                sub_chunks = self._split_oversized_section(
                    contextualized, start, end, meta, header_path, level
                )
                chunks.extend(sub_chunks)

        # Re-index
        for i, chunk in enumerate(chunks):
            chunk.index = i

        return chunks

    def _parse_sections(self, text: str) -> list[dict]:
        """Parse markdown text into a hierarchy of sections.

        Returns list of {level, title, header_path, content, start, end}.
        """
        # Protect code blocks from being parsed as headers
        code_blocks = []
        def _protect(match):
            code_blocks.append(match.group(0))
            return f"{{CODE_BLOCK_{len(code_blocks)-1}}}"

        protected_text = self.CODE_BLOCK_PATTERN.sub(_protect, text)

        # Find all headers
        headers = list(self.HEADER_PATTERN.finditer(protected_text))

        if not headers:
            return [{
                "level": 0,
                "title": "",
                "header_path": "",
                "content": text,
                "start": 0,
                "end": len(text),
            }]

        sections = []

        for i, match in enumerate(headers):
            hashes = match.group(1)
            title = match.group(2).strip()
            level = len(hashes)
            start = match.start()

            # Find end (start of next section or end of text)
            if i + 1 < len(headers):
                end = headers[i + 1].start()
            else:
                end = len(protected_text)

            # Build header path (breadcrumb)
            header_path = self._build_header_path(headers[:i+1])

            # Extract content for this section
            content_start = match.end()
            content_text = protected_text[content_start:end].strip()

            # Restore code blocks
            for j, block in enumerate(code_blocks):
                content_text = content_text.replace(f"{{CODE_BLOCK_{j}}}", block)

            sections.append({
                "level": level,
                "title": title,
                "header_path": header_path,
                "content": content_text,
                "start": content_start,
                "end": end,
            })

        # Restore code blocks in section contents
        for section in sections:
            for j, block in enumerate(code_blocks):
                section["content"] = section["content"].replace(f"{{CODE_BLOCK_{j}}}", block)

        return sections

    def _build_header_path(self, headers: list) -> str:
        """Build a breadcrumb path from headers."""
        parts = []
        for match in headers:
            level = len(match.group(1))
            title = match.group(2).strip()
            if level <= self.max_heading_level:
                parts.append(title)
        return " > ".join(parts) if parts else ""

    def _split_oversized_section(
        self, text: str, start: int, end: int, meta: dict, header_path: str, level: int
    ) -> list[Chunk]:
        """Split a section that exceeds chunk_size."""
        # Try splitting by paragraphs first
        paragraphs = text.split("\n\n")

        chunks: list[Chunk] = []
        current = ""
        sub_start = start

        for para in paragraphs:
            if len(current) + len(para) + 2 > self.chunk_size and current:
                chunks.append(Chunk(
                    text=current.strip(),
                    index=len(chunks),
                    start_char=sub_start,
                    end_char=sub_start + len(current),
                    metadata={
                        **meta,
                        "chunk_strategy": "markdown",
                        "header_level": level,
                        "header_path": header_path,
                    },
                    token_count=self.estimate_tokens(current),
                ))
                sub_start = sub_start + len(current)
                current = para
            else:
                current = current + "\n\n" + para if current else para

        if current.strip():
            chunks.append(Chunk(
                text=current.strip(),
                index=len(chunks),
                start_char=sub_start,
                end_char=sub_start + len(current),
                metadata={
                    **meta,
                    "chunk_strategy": "markdown",
                    "header_level": level,
                    "header_path": header_path,
                },
                token_count=self.estimate_tokens(current),
            ))

        return chunks
