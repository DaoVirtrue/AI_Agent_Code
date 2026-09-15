"""Core layer: lowest-level cross-cutting contracts shared by all other layers.

This layer MUST NOT depend on any other layer. It provides:

- ``exceptions`` — the domain exception hierarchy (``LLMPlatformError`` + subclasses)
- ``tools`` — the tool contract (``BaseTool`` / ``ToolDefinition`` / ``ToolResult`` / ``ToolStatus``)
- ``types`` — shared TypedDict contracts (messages, token usage, agent steps)
- ``id_generator`` — ULID / id generation utilities
"""

from src.core.exceptions import (
    LLMPlatformError,
    ValidationError,
    AuthenticationError,
    AuthorizationError,
    RateLimitExceeded,
    QuotaExceeded,
    ModelNotFoundError,
    ProviderError,
    ProviderTimeoutError,
    ProviderRateLimitError,
    ProviderAuthError,
    CircuitBreakerOpenError,
    FallbackExhaustedError,
    TokenBudgetExceeded,
    ContextWindowExceeded,
    ToolNotFoundError,
    ToolExecutionError,
    RAGError,
    AgentError,
    LoopDetectedError,
    MaxStepsExceeded,
)
from src.core.tools import BaseTool, ToolDefinition, ToolResult, ToolStatus
from src.core.types import (
    JSONDict,
    JSONList,
    JSONValue,
    MessageDict,
    TokenUsage,
    RetrievalResult,
    StreamChunk,
    AgentStep,
    AgentRunResult,
)

__all__ = [
    # exceptions
    "LLMPlatformError",
    "ValidationError",
    "AuthenticationError",
    "AuthorizationError",
    "RateLimitExceeded",
    "QuotaExceeded",
    "ModelNotFoundError",
    "ProviderError",
    "ProviderTimeoutError",
    "ProviderRateLimitError",
    "ProviderAuthError",
    "CircuitBreakerOpenError",
    "FallbackExhaustedError",
    "TokenBudgetExceeded",
    "ContextWindowExceeded",
    "ToolNotFoundError",
    "ToolExecutionError",
    "RAGError",
    "AgentError",
    "LoopDetectedError",
    "MaxStepsExceeded",
    # tools
    "BaseTool",
    "ToolDefinition",
    "ToolResult",
    "ToolStatus",
    # types
    "JSONDict",
    "JSONList",
    "JSONValue",
    "MessageDict",
    "TokenUsage",
    "RetrievalResult",
    "StreamChunk",
    "AgentStep",
    "AgentRunResult",
]
