"""
Base classes and data models for LLM providers.

Defines the common request/response schema and the abstract provider
interface that all provider implementations must satisfy.
"""

from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional, Union


@dataclass
class ToolCall:
    """Represents a tool call requested by the model."""

    id: str
    name: str
    arguments: str  # JSON string

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": "function",
            "function": {
                "name": self.name,
                "arguments": self.arguments,
            },
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolCall":
        func = data.get("function", {})
        return cls(
            id=data.get("id", ""),
            name=func.get("name", ""),
            arguments=func.get("arguments", ""),
        )


@dataclass
class Message:
    """A single message in a conversation."""

    role: str  # "system", "user", "assistant", "tool"
    content: Union[str, List[Dict[str, Any]]]
    name: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None
    tool_call_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {"role": self.role, "content": self.content}
        if self.name:
            result["name"] = self.name
        if self.tool_calls:
            result["tool_calls"] = [tc.to_dict() for tc in self.tool_calls]
        if self.tool_call_id:
            result["tool_call_id"] = self.tool_call_id
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        tool_calls = None
        if "tool_calls" in data and data["tool_calls"]:
            tool_calls = [ToolCall.from_dict(tc) for tc in data["tool_calls"]]

        return cls(
            role=data.get("role", "user"),
            content=data.get("content", ""),
            name=data.get("name"),
            tool_calls=tool_calls,
            tool_call_id=data.get("tool_call_id"),
        )


@dataclass
class LLMRequest:
    """
    Unified request object for all LLM providers.

    Attributes:
        model: The model identifier string (e.g., "gpt-4o", "claude-sonnet-4").
        messages: List of conversation messages.
        temperature: Sampling temperature (0.0 to 2.0).
        max_tokens: Maximum tokens in the response.
        tools: Optional list of tool/function definitions.
        tool_choice: Tool selection mode ("auto", "none", "required", or a specific tool name).
        stream: Whether to stream the response.
        metadata: Arbitrary key-value pairs for tracking and analytics.
    """

    model: str
    messages: List[Message]
    temperature: float = 0.7
    max_tokens: int = 4096
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None
    stream: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "model": self.model,
            "messages": [m.to_dict() for m in self.messages],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": self.stream,
        }
        if self.tools:
            result["tools"] = self.tools
        if self.tool_choice:
            result["tool_choice"] = self.tool_choice
        return result


@dataclass
class TokenUsage:
    """Token usage statistics for a single request."""

    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def to_dict(self) -> Dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cached_tokens": self.cached_tokens,
        }


@dataclass
class LLMResponse:
    """
    Unified response object from all LLM providers.

    Attributes:
        id: Unique response identifier.
        model: The model that produced this response.
        content: The text content of the response (None if only tool calls).
        tool_calls: Tool calls requested by the model, if any.
        finish_reason: Why the model stopped ("stop", "length", "tool_calls", etc.).
        usage: Token usage breakdown.
        latency_ms: End-to-end latency in milliseconds.
        metadata: Additional provider-specific metadata.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    model: str = ""
    content: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None
    finish_reason: str = "stop"
    usage: TokenUsage = field(default_factory=TokenUsage)
    latency_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "id": self.id,
            "model": self.model,
            "content": self.content,
            "finish_reason": self.finish_reason,
            "usage": self.usage.to_dict(),
            "latency_ms": self.latency_ms,
        }
        if self.tool_calls:
            result["tool_calls"] = [tc.to_dict() for tc in self.tool_calls]
        if self.metadata:
            result["metadata"] = self.metadata
        return result


class BaseProvider(ABC):
    """
    Abstract base class for all LLM providers.

    Every provider must implement chat(), chat_stream(), health_check(),
    and count_tokens(). Provider-specific configuration is injected via
    the constructor.
    """

    def __init__(self, api_key: Optional[str] = None, **kwargs: Any):
        self._api_key = api_key
        self._config = kwargs
        self._total_requests: int = 0
        self._total_failures: int = 0
        self._total_latency_ms: float = 0.0

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    async def chat(self, request: LLMRequest) -> LLMResponse:
        """
        Send a chat completion request and return the full response.

        Args:
            request: The unified LLMRequest.

        Returns:
            An LLMResponse with content, tool calls, usage, and latency.
        """
        ...

    @abstractmethod
    async def chat_stream(self, request: LLMRequest) -> AsyncIterator[LLMResponse]:
        """
        Stream a chat completion, yielding partial LLMResponse chunks.

        Each chunk should contain incremental content in `content` and,
        once the stream ends, a final chunk with usage and finish_reason.

        Args:
            request: The unified LLMRequest (request.stream is ignored; streaming
                     is implied by calling this method).

        Yields:
            LLMResponse chunks with incremental content.
        """
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Verify connectivity to the provider's API.

        Returns:
            True if the provider is reachable and responsive.
        """
        ...

    @abstractmethod
    def count_tokens(self, text: str, model: Optional[str] = None) -> int:
        """
        Count the number of tokens in the given text for the specified model.

        Args:
            text: The input text to tokenize.
            model: Optional model override; defaults to the provider's default.

        Returns:
            Estimated token count.
        """
        ...

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable provider identifier (e.g., 'openai', 'anthropic')."""
        ...

    @property
    def context_window(self) -> int:
        """
        Maximum context window size for the currently configured model.

        Providers should override this to return a model-specific value.
        Default is 128000 for most modern models.
        """
        return 128000

    @property
    def supports_tools(self) -> bool:
        """
        Whether the provider natively supports function/tool calling.

        Default is True; llama.cpp and similar may override to False.
        """
        return True

    # ------------------------------------------------------------------
    # Metrics helpers
    # ------------------------------------------------------------------

    def _record_request(self, latency_ms: float, success: bool = True) -> None:
        """Update internal request counters."""
        self._total_requests += 1
        self._total_latency_ms += latency_ms
        if not success:
            self._total_failures += 1

    @property
    def average_latency_ms(self) -> float:
        if self._total_requests == 0:
            return 0.0
        return self._total_latency_ms / self._total_requests

    @property
    def failure_rate(self) -> float:
        if self._total_requests == 0:
            return 0.0
        return self._total_failures / self._total_requests

    # ------------------------------------------------------------------
    # Token counting helpers
    # ------------------------------------------------------------------

    def count_request_tokens(self, request: LLMRequest) -> int:
        """
        Estimate total tokens for an entire LLMRequest (messages + tools).

        Subclasses may override for more accurate counting.
        """
        total = 0
        for msg in request.messages:
            content = msg.content
            if isinstance(content, str):
                total += self.count_tokens(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and "text" in block:
                        total += self.count_tokens(block["text"])
        return total

    def _build_response(
        self,
        content: Optional[str],
        model: str,
        finish_reason: str,
        usage: TokenUsage,
        latency_ms: float,
        tool_calls: Optional[List[ToolCall]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> LLMResponse:
        """Convenience factory for constructing LLMResponse objects."""
        return LLMResponse(
            id=str(uuid.uuid4()),
            model=model,
            content=content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=usage,
            latency_ms=latency_ms,
            metadata=metadata or {},
        )
