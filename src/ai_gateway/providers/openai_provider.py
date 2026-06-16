"""
OpenAI Provider

Wraps the OpenAI AsyncOpenAI client. Supports GPT-4o, GPT-4, GPT-3.5,
o-series models, and any OpenAI-compatible endpoint.
"""

from __future__ import annotations

import logging
import time
from typing import Any, AsyncIterator, Dict, List, Optional, Union

import tiktoken
from openai import AsyncOpenAI

from ai_gateway.providers.base import (
    LLMRequest,
    LLMResponse,
    Message,
    ToolCall,
    TokenUsage,
    BaseProvider,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model-specific context windows
# ---------------------------------------------------------------------------
_OPENAI_CONTEXT_WINDOWS: Dict[str, int] = {
    "gpt-4o": 128000,
    "gpt-4o-mini": 128000,
    "gpt-4": 8192,
    "gpt-4-32k": 32768,
    "gpt-3.5-turbo": 16385,
    "gpt-3.5-turbo-16k": 16385,
    "o1": 200000,
    "o1-mini": 128000,
    "o3-mini": 200000,
}

# Model-specific tokenizer encodings
_TOKENIZER_MAP: Dict[str, str] = {
    "gpt-4o": "o200k_base",
    "gpt-4o-mini": "o200k_base",
    "gpt-4": "cl100k_base",
    "gpt-4-32k": "cl100k_base",
    "gpt-3.5-turbo": "cl100k_base",
    "gpt-3.5-turbo-16k": "cl100k_base",
    "o1": "o200k_base",
    "o1-mini": "o200k_base",
    "o3-mini": "o200k_base",
}

_DEFAULT_ENCODING = "o200k_base"

# Pricing per 1M tokens (input, output)
_PRICING: Dict[str, tuple] = {
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4": (30.00, 60.00),
    "gpt-3.5-turbo": (0.50, 1.50),
    "o1": (15.00, 60.00),
    "o1-mini": (3.00, 12.00),
    "o3-mini": (1.10, 4.40),
}


class OpenAIProvider(BaseProvider):
    """
    OpenAI provider using the official AsyncOpenAI client.

    Configuration keys (via kwargs):
        api_key: OpenAI API key.
        base_url: Optional custom base URL (for proxies / Azure).
        organization: Optional organization ID.
        default_model: Model used when LLMRequest.model is not set.
    """

    _provider_name: str = "openai"

    def __init__(self, api_key: Optional[str] = None, **kwargs: Any):
        super().__init__(api_key=api_key, **kwargs)
        self._default_model = kwargs.get("default_model", "gpt-4o")
        client_kwargs: Dict[str, Any] = {"api_key": api_key}
        if "base_url" in kwargs:
            client_kwargs["base_url"] = kwargs["base_url"]
        if "organization" in kwargs:
            client_kwargs["organization"] = kwargs["organization"]
        self._client = AsyncOpenAI(**client_kwargs)
        self._tokenizer_cache: Dict[str, tiktoken.Encoding] = {}

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def context_window(self) -> int:
        return _OPENAI_CONTEXT_WINDOWS.get(
            self._default_model, 128000
        )

    @property
    def supports_tools(self) -> bool:
        return True

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    async def chat(self, request: LLMRequest) -> LLMResponse:
        """
        Execute a chat completion via the OpenAI API.

        Handles:
          - Mapping messages, tools, tool_choice to OpenAI format
          - Extracting token usage including cached_tokens from prompt_tokens_details
          - Measuring latency
        """
        model = request.model or self._default_model
        start = time.perf_counter()

        # Build API parameters
        api_params: Dict[str, Any] = {
            "model": model,
            "messages": self._build_messages(request.messages),
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": False,
        }

        if request.tools:
            api_params["tools"] = request.tools
        if request.tool_choice:
            api_params["tool_choice"] = request.tool_choice

        try:
            response = await self._client.chat.completions.create(**api_params)
        except Exception as exc:
            latency = (time.perf_counter() - start) * 1000
            self._record_request(latency, success=False)
            logger.error("OpenAI chat failed: %s", exc)
            raise

        latency = (time.perf_counter() - start) * 1000
        self._record_request(latency, success=True)

        choice = response.choices[0]

        # Parse content and tool calls
        content = choice.message.content
        tool_calls = None
        if choice.message.tool_calls:
            tool_calls = [
                ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=tc.function.arguments,
                )
                for tc in choice.message.tool_calls
            ]

        # Parse usage, including cached_tokens details
        usage_obj = response.usage
        cached_tokens = 0
        if usage_obj and hasattr(usage_obj, "prompt_tokens_details"):
            details = usage_obj.prompt_tokens_details
            if details and hasattr(details, "cached_tokens"):
                cached_tokens = details.cached_tokens or 0

        usage = TokenUsage(
            input_tokens=usage_obj.prompt_tokens if usage_obj else 0,
            output_tokens=usage_obj.completion_tokens if usage_obj else 0,
            cached_tokens=cached_tokens,
        )

        finish_reason = choice.finish_reason or "stop"

        metadata: Dict[str, Any] = {
            "provider": self.provider_name,
            "request_model": request.model,
            "actual_model": response.model,
            "system_fingerprint": getattr(response, "system_fingerprint", None),
            "cost": self._compute_cost(model, usage),
        }

        return self._build_response(
            content=content,
            model=response.model or model,
            finish_reason=finish_reason,
            usage=usage,
            latency_ms=latency,
            tool_calls=tool_calls,
            metadata=metadata,
        )

    async def chat_stream(self, request: LLMRequest) -> AsyncIterator[LLMResponse]:
        """
        Stream chat completion chunks from OpenAI.

        Yields partial LLMResponse objects with incremental content and null
        usage. The final chunk includes complete usage and finish_reason.
        """
        model = request.model or self._default_model
        start = time.perf_counter()

        api_params: Dict[str, Any] = {
            "model": model,
            "messages": self._build_messages(request.messages),
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if request.tools:
            api_params["tools"] = request.tools
        if request.tool_choice:
            api_params["tool_choice"] = request.tool_choice

        accumulated_content: List[str] = []
        accumulated_tool_calls: Dict[int, Dict[str, Any]] = {}
        final_usage = TokenUsage()
        finish_reason = "stop"
        response_id = ""
        actual_model = ""

        try:
            stream = await self._client.chat.completions.create(**api_params)

            async for chunk in stream:
                if not chunk.choices:
                    # Usage-only chunk (stream_options include_usage)
                    if chunk.usage:
                        final_usage = TokenUsage(
                            input_tokens=chunk.usage.prompt_tokens or 0,
                            output_tokens=chunk.usage.completion_tokens or 0,
                        )
                    continue

                delta = chunk.choices[0].delta
                chunk_finish = chunk.choices[0].finish_reason

                if delta.content:
                    accumulated_content.append(delta.content)

                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in accumulated_tool_calls:
                            accumulated_tool_calls[idx] = {
                                "id": tc.id or "",
                                "name": "",
                                "arguments": "",
                            }
                        if tc.id:
                            accumulated_tool_calls[idx]["id"] = tc.id
                        if tc.function and tc.function.name:
                            accumulated_tool_calls[idx]["name"] += tc.function.name
                        if tc.function and tc.function.arguments:
                            accumulated_tool_calls[idx]["arguments"] += tc.function.arguments

                if chunk_finish:
                    finish_reason = chunk_finish

                if chunk.id:
                    response_id = chunk.id
                if chunk.model:
                    actual_model = chunk.model

                # Yield incremental chunk
                yield LLMResponse(
                    id=response_id,
                    model=actual_model or model,
                    content=delta.content,
                    finish_reason=finish_reason if chunk_finish else None,
                    usage=TokenUsage(),
                    latency_ms=(time.perf_counter() - start) * 1000,
                )

            # Yield final chunk with aggregated data
            tool_calls = None
            if accumulated_tool_calls:
                tool_calls = [
                    ToolCall(
                        id=tc["id"],
                        name=tc["name"],
                        arguments=tc["arguments"],
                    )
                    for tc in sorted(accumulated_tool_calls.values(), key=lambda x: x.get("id", ""))
                    if tc["name"]
                ]

            latency = (time.perf_counter() - start) * 1000
            self._record_request(latency, success=True)

            yield LLMResponse(
                id=response_id,
                model=actual_model or model,
                content=None,  # Final chunk carries usage only
                tool_calls=tool_calls,
                finish_reason=finish_reason,
                usage=final_usage,
                latency_ms=latency,
                metadata={"provider": self.provider_name},
            )

        except Exception as exc:
            latency = (time.perf_counter() - start) * 1000
            self._record_request(latency, success=False)
            logger.error("OpenAI stream failed: %s", exc)
            raise

    async def health_check(self) -> bool:
        """Verify connectivity by listing available models."""
        try:
            await self._client.models.list()
            return True
        except Exception as exc:
            logger.warning("OpenAI health check failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Token counting
    # ------------------------------------------------------------------

    def count_tokens(self, text: str, model: Optional[str] = None) -> int:
        """
        Count tokens using tiktoken with model-appropriate encoding.

        Uses o200k_base for gpt-4o/o-series, cl100k_base for gpt-4/gpt-3.5.
        Falls back to cl100k_base if the model is unknown.
        """
        if not text:
            return 0

        model_key = model or self._default_model
        encoding_name = _TOKENIZER_MAP.get(model_key, _DEFAULT_ENCODING)

        if encoding_name not in self._tokenizer_cache:
            try:
                self._tokenizer_cache[encoding_name] = tiktoken.get_encoding(encoding_name)
            except Exception:
                # Fallback to cl100k_base if o200k_base is unavailable
                self._tokenizer_cache[encoding_name] = tiktoken.get_encoding("cl100k_base")

        enc = self._tokenizer_cache[encoding_name]
        return len(enc.encode(text))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """Convert internal Message objects to OpenAI API format."""
        result: List[Dict[str, Any]] = []
        for msg in messages:
            entry: Dict[str, Any] = {"role": msg.role, "content": msg.content}
            if msg.name:
                entry["name"] = msg.name
            if msg.tool_calls:
                entry["tool_calls"] = [tc.to_dict() for tc in msg.tool_calls]
            if msg.tool_call_id:
                entry["tool_call_id"] = msg.tool_call_id
            result.append(entry)
        return result

    def _compute_cost(self, model: str, usage: TokenUsage) -> float:
        """
        Compute approximate USD cost for the request.

        Uses cached pricing rates. Returns 0.0 for unknown models.
        """
        input_price, output_price = _PRICING.get(model, (0.0, 0.0))
        if input_price == 0.0:
            # Try prefix match
            for known, prices in _PRICING.items():
                if model.startswith(known):
                    input_price, output_price = prices
                    break

        cost = (usage.input_tokens / 1_000_000) * input_price + \
               (usage.output_tokens / 1_000_000) * output_price
        return round(cost, 6)
