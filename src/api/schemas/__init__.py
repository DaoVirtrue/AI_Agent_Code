"""API Schemas - Pydantic models for request/response validation."""

from src.api.schemas.common import (
    ErrorResponse,
    PaginatedResponse,
    HealthResponse,
)
from src.api.schemas.gateway import (
    ChatRequest,
    ChatResponse,
    ModelInfo,
    TokenUsage,
    MessageDict,
    StreamChunk,
)
from src.api.schemas.rag import (
    RAGQueryRequest,
    RAGQueryResponse,
    DocumentUploadResponse,
    SourceDoc,
    EvalRequest,
)
from src.api.schemas.agent import (
    AgentRunRequest,
    AgentRunResponse,
    AgentStep,
    OrchestrateRequest,
    ApprovalDecision,
)
from src.api.schemas.prompt import (
    RenderRequest,
    RenderResponse,
    TemplateCreate,
    TemplateResponse,
    ExperimentRequest,
)

__all__ = [
    # Common
    "ErrorResponse",
    "PaginatedResponse",
    "HealthResponse",
    # Gateway
    "ChatRequest",
    "ChatResponse",
    "ModelInfo",
    "TokenUsage",
    "MessageDict",
    "StreamChunk",
    # RAG
    "RAGQueryRequest",
    "RAGQueryResponse",
    "DocumentUploadResponse",
    "SourceDoc",
    "EvalRequest",
    # Agent
    "AgentRunRequest",
    "AgentRunResponse",
    "AgentStep",
    "OrchestrateRequest",
    "ApprovalDecision",
    # Prompt
    "RenderRequest",
    "RenderResponse",
    "TemplateCreate",
    "TemplateResponse",
    "ExperimentRequest",
]
