"""
Domain exception hierarchy for the LLM Platform.

Every exception carries an HTTP-like ``status_code`` and a ``detail`` message
suitable for returning in API error responses.  The hierarchy is designed so
that middleware can catch ``LLMPlatformError`` and produce consistent JSON
error bodies.
"""

from __future__ import annotations

from typing import Any


# ============================================================================
# Root
# ============================================================================


class LLMPlatformError(Exception):
    """Base exception for all LLM Platform errors."""

    status_code: int = 500
    detail: str = "Internal server error"

    def __init__(self, detail: str | None = None, status_code: int | None = None) -> None:
        if detail is not None:
            self.detail = detail
        if status_code is not None:
            self.status_code = status_code
        super().__init__(self.detail)


# ============================================================================
# Client errors (4xx)
# ============================================================================


class ValidationError(LLMPlatformError):
    """Request validation failed."""

    status_code = 422
    detail = "Validation error"


class AuthenticationError(LLMPlatformError):
    """Missing or invalid credentials."""

    status_code = 401
    detail = "Authentication failed"


class AuthorizationError(LLMPlatformError):
    """Authenticated but insufficient permissions."""

    status_code = 403
    detail = "Insufficient permissions"


class RateLimitExceeded(LLMPlatformError):
    """Too many requests – rate limit hit."""

    status_code = 429
    detail = "Rate limit exceeded"

    def __init__(
        self,
        detail: str | None = None,
        retry_after: float = 60.0,
    ) -> None:
        super().__init__(detail=detail)
        self.retry_after = retry_after


class QuotaExceeded(LLMPlatformError):
    """The tenant has exceeded a quota (tokens, storage, etc.)."""

    status_code = 429
    detail = "Quota exceeded"

    def __init__(
        self,
        detail: str | None = None,
        quota_type: str = "unknown",
        limit: int | None = None,
        current: int | None = None,
    ) -> None:
        super().__init__(detail=detail)
        self.quota_type = quota_type
        self.limit = limit
        self.current = current


# ============================================================================
# Model / provider errors
# ============================================================================


class ModelNotFoundError(LLMPlatformError):
    """The requested model_id is not in the registry or is disabled."""

    status_code = 404
    detail = "Model not found"

    def __init__(self, model_id: str | None = None, detail: str | None = None) -> None:
        if model_id and not detail:
            detail = f"Model '{model_id}' not found"
        super().__init__(detail=detail)
        self.model_id = model_id


class ProviderError(LLMPlatformError):
    """Base for third-party LLM provider errors."""

    status_code = 502
    detail = "Provider error"

    def __init__(
        self,
        detail: str | None = None,
        provider: str = "unknown",
        status_code: int = 502,
    ) -> None:
        super().__init__(detail=detail, status_code=status_code)
        self.provider = provider


class ProviderTimeoutError(ProviderError):
    """Provider request timed out."""

    status_code = 504
    detail = "Provider request timed out"


class ProviderRateLimitError(ProviderError):
    """The upstream provider rate-limited the request."""

    status_code = 429
    detail = "Provider rate limit exceeded"


class ProviderAuthError(ProviderError):
    """Authentication failed with the upstream provider."""

    status_code = 502
    detail = "Provider authentication failed"


# ============================================================================
# Resilience errors
# ============================================================================


class CircuitBreakerOpenError(LLMPlatformError):
    """The circuit breaker is open – requests are not being forwarded."""

    status_code = 503
    detail = "Circuit breaker is open"

    def __init__(
        self,
        detail: str | None = None,
        provider: str = "unknown",
        recovery_seconds: float = 30.0,
    ) -> None:
        super().__init__(detail=detail)
        self.provider = provider
        self.recovery_seconds = recovery_seconds


class FallbackExhaustedError(LLMPlatformError):
    """All fallback providers have been tried and none succeeded."""

    status_code = 503
    detail = "All fallback providers exhausted"

    def __init__(
        self,
        detail: str | None = None,
        attempts: list[str] | None = None,
    ) -> None:
        super().__init__(detail=detail)
        self.attempts = attempts or []


# ============================================================================
# Token / context errors
# ============================================================================


class TokenBudgetExceeded(LLMPlatformError):
    """The cumulative token usage has exceeded the allowed budget."""

    status_code = 400
    detail = "Token budget exceeded"

    def __init__(
        self,
        detail: str | None = None,
        budget: int = 0,
        used: int = 0,
    ) -> None:
        super().__init__(detail=detail)
        self.budget = budget
        self.used = used


class ContextWindowExceeded(LLMPlatformError):
    """The prompt exceeds the model's context window."""

    status_code = 400
    detail = "Context window exceeded"

    def __init__(
        self,
        detail: str | None = None,
        context_window: int = 0,
        requested: int = 0,
    ) -> None:
        super().__init__(detail=detail)
        self.context_window = context_window
        self.requested = requested


# ============================================================================
# Tool-related errors
# ============================================================================


class ToolNotFoundError(LLMPlatformError):
    """The requested tool is not registered."""

    status_code = 404
    detail = "Tool not found"

    def __init__(self, tool_name: str = "", detail: str | None = None) -> None:
        if tool_name and not detail:
            detail = f"Tool '{tool_name}' not found"
        super().__init__(detail=detail)
        self.tool_name = tool_name


class ToolExecutionError(LLMPlatformError):
    """A tool call failed during execution."""

    status_code = 500
    detail = "Tool execution failed"

    def __init__(
        self,
        tool_name: str = "",
        detail: str | None = None,
        original_error: str | None = None,
    ) -> None:
        super().__init__(detail=detail)
        self.tool_name = tool_name
        self.original_error = original_error


# ============================================================================
# RAG / Agent errors
# ============================================================================


class RAGError(LLMPlatformError):
    """An error occurred during the RAG pipeline."""

    status_code = 500
    detail = "RAG operation failed"

    def __init__(
        self,
        detail: str | None = None,
        stage: str = "unknown",
    ) -> None:
        super().__init__(detail=detail)
        self.stage = stage


class AgentError(LLMPlatformError):
    """An error occurred during agent execution."""

    status_code = 500
    detail = "Agent execution failed"

    def __init__(
        self,
        detail: str | None = None,
        agent_type: str = "unknown",
        step_count: int = 0,
    ) -> None:
        super().__init__(detail=detail)
        self.agent_type = agent_type
        self.step_count = step_count


class LoopDetectedError(AgentError):
    """The agent is stuck in a loop – repeating the same output."""

    status_code = 500
    detail = "Agent loop detected"

    def __init__(
        self,
        detail: str | None = None,
        agent_type: str = "unknown",
        step_count: int = 0,
        similar_steps: list[int] | None = None,
    ) -> None:
        super().__init__(detail=detail, agent_type=agent_type, step_count=step_count)
        self.similar_steps = similar_steps or []


class MaxStepsExceeded(AgentError):
    """The agent reached the maximum allowed number of steps."""

    status_code = 500
    detail = "Maximum agent steps exceeded"

    def __init__(
        self,
        detail: str | None = None,
        agent_type: str = "unknown",
        step_count: int = 0,
        max_steps: int = 50,
    ) -> None:
        super().__init__(detail=detail, agent_type=agent_type, step_count=step_count)
        self.max_steps = max_steps
