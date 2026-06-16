"""Gateway API schemas for chat completions and model management."""

from typing import Optional
from pydantic import BaseModel, Field


class MessageDict(BaseModel):
    """A single chat message in the conversation."""

    role: str = Field(..., description="Message role", examples=["system", "user", "assistant", "tool"])
    content: str = Field(..., description="Message content text")
    name: Optional[str] = Field(None, description="Optional name for the participant")
    tool_calls: Optional[list[dict]] = Field(None, description="Tool calls made by the assistant")
    tool_call_id: Optional[str] = Field(None, description="ID of the tool call this message responds to")

    class Config:
        json_schema_extra = {
            "example": {
                "role": "user",
                "content": "What is the capital of France?",
            }
        }


class TokenUsage(BaseModel):
    """Token usage statistics for an LLM call."""

    prompt_tokens: int = Field(0, description="Tokens in the prompt", ge=0)
    completion_tokens: int = Field(0, description="Tokens in the completion", ge=0)
    total_tokens: int = Field(0, description="Total tokens used", ge=0)
    cached_tokens: int = Field(0, description="Tokens served from cache", ge=0)

    class Config:
        json_schema_extra = {
            "example": {
                "prompt_tokens": 150,
                "completion_tokens": 80,
                "total_tokens": 230,
                "cached_tokens": 0,
            }
        }


class ChatRequest(BaseModel):
    """Chat completion request compatible with OpenAI-style API."""

    model: str = Field(
        default="gpt-4o",
        description="Model identifier to use for the completion",
        examples=["gpt-4o", "claude-3-opus", "gemini-2.0-flash"],
    )
    messages: list[MessageDict] = Field(
        ...,
        description="List of messages in the conversation",
        min_length=1,
    )
    temperature: float = Field(
        default=0.7,
        description="Sampling temperature (0-2)",
        ge=0.0,
        le=2.0,
    )
    max_tokens: int = Field(
        default=4096,
        description="Maximum tokens in the completion",
        ge=1,
        le=128000,
    )
    top_p: float = Field(
        default=1.0,
        description="Nucleus sampling parameter",
        ge=0.0,
        le=1.0,
    )
    tools: Optional[list[dict]] = Field(
        None,
        description="Tool definitions for function calling",
    )
    tool_choice: Optional[str] = Field(
        None,
        description="Tool choice mode: 'auto', 'none', 'required', or specific tool",
    )
    stream: bool = Field(
        default=False,
        description="Whether to stream the response as SSE events",
    )
    stop: Optional[list[str]] = Field(
        None,
        description="Stop sequences that end generation early",
    )
    response_format: Optional[dict] = Field(
        None,
        description="Response format specification (e.g., JSON mode)",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "model": "gpt-4o",
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": "Hello!"},
                ],
                "temperature": 0.7,
                "max_tokens": 4096,
                "stream": False,
            }
        }


class ChatResponse(BaseModel):
    """Chat completion response."""

    id: str = Field(..., description="Unique response identifier")
    model: str = Field(..., description="Model used for the completion")
    content: str = Field(..., description="Assistant response content")
    finish_reason: Optional[str] = Field(
        None,
        description="Reason completion finished",
        examples=["stop", "length", "tool_calls", "content_filter"],
    )
    usage: TokenUsage = Field(..., description="Token usage statistics")
    cost_usd: float = Field(..., description="Estimated cost in USD", ge=0)
    latency_ms: float = Field(..., description="Response latency in milliseconds", ge=0)
    tool_calls: Optional[list[dict]] = Field(None, description="Tool calls if requested")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "chatcmpl-abc123",
                "model": "gpt-4o",
                "content": "Hello! How can I help you today?",
                "finish_reason": "stop",
                "usage": {
                    "prompt_tokens": 25,
                    "completion_tokens": 9,
                    "total_tokens": 34,
                    "cached_tokens": 0,
                },
                "cost_usd": 0.00015,
                "latency_ms": 450.5,
            }
        }


class StreamChunk(BaseModel):
    """A single chunk in a streaming chat completion response (SSE format)."""

    id: str = Field(..., description="Chunk identifier matching the response ID")
    model: str = Field(..., description="Model identifier")
    delta_content: str = Field("", description="Content delta for this chunk")
    delta_tool_calls: Optional[list[dict]] = Field(None, description="Tool call deltas")
    finish_reason: Optional[str] = Field(None, description="Reason if this is the final chunk")
    index: int = Field(0, description="Sequence index of this chunk", ge=0)

    class Config:
        json_schema_extra = {
            "example": {
                "id": "chatcmpl-abc123",
                "model": "gpt-4o",
                "delta_content": "Hello",
                "finish_reason": None,
                "index": 0,
            }
        }


class ModelInfo(BaseModel):
    """Information about an available LLM model."""

    id: str = Field(..., description="Unique model identifier")
    provider: str = Field(..., description="Model provider", examples=["openai", "anthropic", "google", "azure"])
    display_name: str = Field(..., description="Human-readable model name")
    context_window: int = Field(..., description="Maximum context window in tokens", ge=1)
    max_output_tokens: int = Field(..., description="Maximum output tokens", ge=1)
    capabilities: list[str] = Field(
        ...,
        description="Model capabilities",
        examples=[["chat", "function_calling", "vision", "json_mode"]],
    )
    pricing: dict = Field(
        ...,
        description="Pricing per 1K tokens for input/output",
        examples=[{"input": 0.0025, "output": 0.01, "cached_input": 0.00125}],
    )
    supports_streaming: bool = Field(True, description="Whether model supports streaming")
    supports_tools: bool = Field(True, description="Whether model supports function/tool calling")
    availability: str = Field(
        "available",
        description="Model availability status",
        examples=["available", "degraded", "unavailable"],
    )

    class Config:
        json_schema_extra = {
            "example": {
                "id": "gpt-4o",
                "provider": "openai",
                "display_name": "GPT-4o",
                "context_window": 128000,
                "max_output_tokens": 16384,
                "capabilities": ["chat", "function_calling", "vision", "json_mode", "streaming"],
                "pricing": {"input": 0.0025, "output": 0.01, "cached_input": 0.00125},
                "supports_streaming": True,
                "supports_tools": True,
                "availability": "available",
            }
        }
