"""RAG API schemas for document upload, search, and chat with context."""

from typing import Optional
from pydantic import BaseModel, Field


class SourceDoc(BaseModel):
    """A retrieved source document with metadata."""

    document_id: str = Field(..., description="Unique document identifier")
    chunk_id: str = Field(..., description="Chunk identifier within the document")
    content: str = Field(..., description="Chunk text content")
    score: float = Field(..., description="Relevance score", ge=0.0, le=1.0)
    metadata: dict = Field(default_factory=dict, description="Document metadata")
    source_type: str = Field(
        "unknown",
        description="Source type",
        examples=["pdf", "web", "database", "api"],
    )
    page_number: Optional[int] = Field(None, description="Page number if applicable")
    retrieval_strategy: Optional[str] = Field(
        None,
        description="Strategy that retrieved this chunk",
        examples=["semantic", "keyword", "hybrid"],
    )

    class Config:
        json_schema_extra = {
            "example": {
                "document_id": "doc-abc123",
                "chunk_id": "chunk-1",
                "content": "Paris is the capital of France...",
                "score": 0.95,
                "metadata": {"title": "France Overview", "author": "Wikipedia"},
                "source_type": "web",
                "retrieval_strategy": "hybrid",
            }
        }


class RAGQueryRequest(BaseModel):
    """Request for a RAG query (search or chat with context)."""

    query: str = Field(..., description="User query text", min_length=1, max_length=10000)
    top_k: int = Field(
        default=10,
        description="Number of documents to retrieve",
        ge=1,
        le=100,
    )
    retrieval_strategy: str = Field(
        default="hybrid",
        description="Retrieval strategy",
        examples=["semantic", "keyword", "hybrid", "mmr"],
    )
    filters: Optional[dict] = Field(
        None,
        description="Metadata filters for document retrieval",
        examples=[{"source_type": "pdf", "date_range": {"gte": "2024-01-01"}}],
    )
    include_scores: bool = Field(
        default=True,
        description="Include relevance scores in response",
    )
    rerank: bool = Field(
        default=True,
        description="Apply reranking to retrieved results",
    )
    rerank_model: Optional[str] = Field(
        None,
        description="Reranking model to use",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "query": "What is the capital of France?",
                "top_k": 10,
                "retrieval_strategy": "hybrid",
                "filters": {"source_type": "web"},
                "include_scores": True,
                "rerank": True,
            }
        }


class RAGQueryResponse(BaseModel):
    """Response for a RAG query containing answer and sources."""

    answer: str = Field(..., description="Generated answer text")
    sources: list[SourceDoc] = Field(..., description="Retrieved source documents")
    latency_ms: float = Field(..., description="Total query latency in milliseconds", ge=0)
    cost_usd: float = Field(..., description="Estimated cost in USD", ge=0)
    token_usage: Optional[dict] = Field(None, description="Token usage breakdown")
    cache_hit: bool = Field(False, description="Whether answer was served from cache")
    retrieval_latency_ms: Optional[float] = Field(None, description="Retrieval-only latency")
    generation_latency_ms: Optional[float] = Field(None, description="Generation-only latency")

    class Config:
        json_schema_extra = {
            "example": {
                "answer": "The capital of France is Paris.",
                "sources": [
                    {
                        "document_id": "doc-1",
                        "chunk_id": "chunk-1",
                        "content": "Paris is the capital of France.",
                        "score": 0.95,
                        "metadata": {},
                        "source_type": "web",
                    }
                ],
                "latency_ms": 350.2,
                "cost_usd": 0.0005,
                "cache_hit": False,
            }
        }


class DocumentUploadResponse(BaseModel):
    """Response after uploading a document for indexing."""

    document_id: str = Field(..., description="Unique document identifier assigned by the system")
    chunks_count: int = Field(..., description="Number of chunks the document was split into", ge=0)
    status: str = Field(
        ...,
        description="Processing status",
        examples=["indexing", "completed", "failed"],
    )
    filename: Optional[str] = Field(None, description="Original filename")
    file_size_bytes: Optional[int] = Field(None, description="File size in bytes")
    estimated_tokens: Optional[int] = Field(None, description="Estimated token count")

    class Config:
        json_schema_extra = {
            "example": {
                "document_id": "doc-abc123",
                "chunks_count": 45,
                "status": "completed",
                "filename": "report.pdf",
                "file_size_bytes": 1024000,
                "estimated_tokens": 12000,
            }
        }


class EvalRequest(BaseModel):
    """Request to evaluate RAG pipeline quality."""

    queries: list[str] = Field(..., description="Test queries", min_length=1, max_length=100)
    expected_answers: Optional[list[str]] = Field(None, description="Expected answers for reference")
    metrics: list[str] = Field(
        default=["faithfulness", "relevance", "context_precision", "context_recall"],
        description="Metrics to compute",
    )
    top_k: int = Field(default=10, ge=1, le=50)
    retrieval_strategy: str = Field(default="hybrid")

    class Config:
        json_schema_extra = {
            "example": {
                "queries": ["What is AI?", "Explain RAG"],
                "expected_answers": ["AI is artificial intelligence...", "RAG is retrieval augmented..."],
                "metrics": ["faithfulness", "relevance"],
                "top_k": 10,
            }
        }
