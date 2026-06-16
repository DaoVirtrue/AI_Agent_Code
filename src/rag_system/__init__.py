"""RAG System - Retrieval-Augmented Generation pipeline.

A comprehensive RAG system with:
- Multi-format document ingestion (PDF, DOCX, HTML, Markdown, CSV, JSON)
- OCR, table extraction, and text cleaning
- Multiple chunking strategies (fixed, recursive, semantic, markdown-aware)
- Embedding model registry with batch processing
- Vector stores (Milvus, Chroma, FAISS)
- Dense, sparse, and hybrid retrieval with RRF fusion
- Query processing (rewriting, expansion, decomposition, HyDE, routing)
- Multi-level caching (exact, semantic, summary, precomputed)
- RAGAS evaluation and quality metrics
- Advanced RAG strategies (CRAG, Self-RAG, Adaptive, GraphRAG, AgenticRAG)
- Quality assurance (fact verification, source attribution, hallucination detection, answer voting)
- Incremental indexing
- Full LangGraph pipeline orchestration
"""

# ---- Pipeline (core orchestration) ----
from .pipeline import (
    RAGPipeline,
    build_rag_graph,
    RAGState,
    RAGQueryRequest,
    RAGQueryResponse,
    RAGChatResponse,
)

# ---- Ingestion ----
from .ingestion import (
    DocumentParser,
    OCREngine,
    TableExtractor,
    TextCleaner,
    ParsedDocument,
)

# ---- Chunking ----
from .chunking import (
    BaseChunker,
    FixedSizeChunker,
    SemanticChunker,
    RecursiveChunker,
    MarkdownChunker,
    Chunk,
)

# ---- Embedding ----
from .embedding import EmbeddingRegistry, BatchEmbedder

# ---- Vector Stores (indexing) ----
from .indexing import (
    BaseVectorStore,
    MilvusStore,
    ChromaStore,
    FAISSStore,
)

# ---- Retrieval ----
from .retrieval import (
    DenseRetriever,
    SparseRetriever,
    HybridRetriever,
    Reranker,
    RRFFusion,
)

# ---- Query Processing ----
from .query_processing import (  # type: ignore
    QueryRewriter,
    QueryExpander,
    QueryDecomposer,
    HyDEGenerator,
    QueryRouter,
    BaseQueryProcessor,
    ProcessedQuery,
)

# ---- Caching ----
from .caching import (
    ExactCache,
    SemanticCache,
    SummaryCache,
    PrecomputedCache,
    CacheOrchestrator,
    BaseCache,
    CacheEntry,
    CacheLookupResult,
)

# ---- Evaluation ----
from .evaluation import RAGASWrapper, RAGMetrics

# ---- Advanced RAG Strategies ----
from .advanced import (
    CRAGProcessor,
    SelfRAGProcessor,
    AdaptiveRAGRouter,
    GraphRAGProcessor,
    AgenticRAGProcessor,
)

# ---- Quality Assurance ----
from .quality import (
    FactVerifier,
    SourceAttribution,
    HallucinationDetector,
    AnswerVoting,
    VerificationResult,
    AttributionResult,
    HallucinationReport,
    VoteResult,
)

# ---- Incremental Indexing ----
from .incremental import IncrementalIndexer

# ---- Search Results ----
from .retrieval import SearchResult, RetrievalResult

__all__ = [
    # Pipeline
    "RAGPipeline",
    "build_rag_graph",
    "RAGState",
    "RAGQueryRequest",
    "RAGQueryResponse",
    "RAGChatResponse",
    # Ingestion
    "DocumentParser",
    "OCREngine",
    "TableExtractor",
    "TextCleaner",
    "ParsedDocument",
    # Chunking
    "BaseChunker",
    "FixedSizeChunker",
    "SemanticChunker",
    "RecursiveChunker",
    "MarkdownChunker",
    "Chunk",
    # Embedding
    "EmbeddingRegistry",
    "BatchEmbedder",
    # Vector Stores
    "BaseVectorStore",
    "MilvusStore",
    "ChromaStore",
    "FAISSStore",
    # Retrieval
    "DenseRetriever",
    "SparseRetriever",
    "HybridRetriever",
    "Reranker",
    "RRFFusion",
    "SearchResult",
    "RetrievalResult",
    # Query Processing
    "QueryRewriter",
    "QueryExpander",
    "QueryDecomposer",
    "HyDEGenerator",
    "QueryRouter",
    "BaseQueryProcessor",
    "ProcessedQuery",
    # Caching
    "ExactCache",
    "SemanticCache",
    "SummaryCache",
    "PrecomputedCache",
    "CacheOrchestrator",
    "BaseCache",
    "CacheEntry",
    "CacheLookupResult",
    # Evaluation
    "RAGASWrapper",
    "RAGMetrics",
    # Advanced RAG
    "CRAGProcessor",
    "SelfRAGProcessor",
    "AdaptiveRAGRouter",
    "GraphRAGProcessor",
    "AgenticRAGProcessor",
    # Quality
    "FactVerifier",
    "SourceAttribution",
    "HallucinationDetector",
    "AnswerVoting",
    "VerificationResult",
    "AttributionResult",
    "HallucinationReport",
    "VoteResult",
    # Indexing
    "IncrementalIndexer",
]
