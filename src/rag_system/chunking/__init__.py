"""RAG System - Text Chunking Strategies.

Provides multiple chunking strategies for splitting documents into
manageable pieces for retrieval-augmented generation.

Exports:
    BaseChunker - Abstract base class for all chunkers
    FixedSizeChunker - Fixed-size character/token chunks with overlap
    SemanticChunker - Paragraph/section boundary-aware chunking
    RecursiveChunker - Recursive character text splitting
    MarkdownChunker - Markdown header hierarchy-preserving chunking
    Chunk - Dataclass representing a single text chunk
"""

from .base import BaseChunker, Chunk
from .fixed_size import FixedSizeChunker
from .recursive import RecursiveChunker
from .semantic import SemanticChunker
from .markdown_aware import MarkdownChunker

__all__ = [
    "BaseChunker",
    "Chunk",
    "FixedSizeChunker",
    "RecursiveChunker",
    "SemanticChunker",
    "MarkdownChunker",
]
