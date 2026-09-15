"""
Shared type aliases and TypedDict definitions used across the platform.

These provide lightweight contracts for function signatures, message passing,
and data interchange without depending on full ORM objects or Pydantic models.
"""

from __future__ import annotations

from typing import Any, Literal, Optional, TypedDict


# ============================================================================
# JSON-compatible primitives
# ============================================================================

#: A JSON object – keys are strings, values are JSON-serialisable.
JSONDict = dict[str, Any]

#: A JSON array of arbitrary JSON-serialisable values.
JSONList = list[Any]

#: A JSON-serialisable value (used for cache values, payloads, etc.).
JSONValue = str | int | float | bool | None | JSONDict | JSONList


# ============================================================================
# Message types (Chat-completion protocol)
# ============================================================================


class ToolCallFunction(TypedDict):
    """The function call details within a tool_call block."""

    name: str
    arguments: str  # JSON-encoded string


class ToolCall(TypedDict):
    """A single tool-call request from an assistant message."""

    id: str
    type: Literal["function"]
    function: ToolCallFunction


class MessageDict(TypedDict, total=False):
    """Represents a single message in a chat-completion conversation.

    Mirrors the OpenAI / Anthropic message shape but is provider-agnostic.

    Fields:
        role: One of ``system``, ``user``, ``assistant``, ``tool``.
        content: The message body (text or structured content).
        tool_calls: Tool-call blocks emitted by an assistant message.
        tool_call_id: ID linking a tool-result message to its call.
        name: Optional name for the participant (user/function).
    """

    role: Literal["system", "user", "assistant", "tool"]
    content: str | list[dict[str, Any]] | None
    tool_calls: Optional[list[ToolCall]]
    tool_call_id: Optional[str]
    name: Optional[str]


# ============================================================================
# Token usage
# ============================================================================


class TokenUsage(TypedDict, total=False):
    """Token counts for a single LLM request.

    Fields:
        input_tokens: Number of tokens in the prompt.
        output_tokens: Number of tokens in the completion.
        cached_tokens: Number of input tokens read from cache (Anthropic / OpenAI).
    """

    input_tokens: int
    output_tokens: int
    cached_tokens: int


# ============================================================================
# Retrieval (RAG) results
# ============================================================================


class RetrievalResult(TypedDict):
    """A single chunk returned by the RAG retrieval pipeline.

    Fields:
        chunk_id: Unique ID of the chunk within the vector store.
        content: The text content of the retrieved chunk.
        score: Relevance / similarity score (higher = more relevant).
        document_id: ID of the parent document.
        metadata: Arbitrary metadata attached to the chunk (page, section, etc.).
    """

    chunk_id: str
    content: str
    score: float
    document_id: str
    metadata: dict[str, Any]


# ============================================================================
# Streaming
# ============================================================================


class StreamChunk(TypedDict, total=False):
    """A single chunk in a streaming response."""

    type: Literal["text", "tool_call", "tool_result", "error", "done"]
    content: str
    tool_call: Optional[ToolCall]
    index: int
    finish_reason: Optional[str]


# ============================================================================
# Agent step
# ============================================================================


class AgentStep(TypedDict, total=False):
    """Records a single step in an agent execution loop."""

    step_number: int
    thought: str
    action: Optional[dict[str, Any]]  # tool call
    observation: Optional[str]        # tool result
    token_usage: TokenUsage
    latency_ms: float


class AgentRunResult(TypedDict, total=False):
    """Final result of an agent execution."""

    success: bool
    final_answer: Optional[str]
    steps: list[AgentStep]
    total_tokens: int
    total_cost_usd: float
    total_latency_ms: float
    error: Optional[str]
    agent_type: str
    request_id: str
