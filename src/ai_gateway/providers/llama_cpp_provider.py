"""
llama.cpp Provider

Connects to llama-cpp-python server mode via OpenAI-compatible API.
Supports GGUF quantized models for local/edge inference.
"""

from __future__ import annotations

import logging
import time
from typing import Any, AsyncIterator, Dict, List, Optional

import tiktoken
from openai import AsyncOpenAI

from src.ai_gateway.providers.base import (
    LLMRequest,
    LLMResponse,
    Message,
    ToolCall,
    TokenUsage,
    BaseProvider,
)

logger = logging.getLogger(__name__)

# Default llama.cpp server endpoint
DEFAULT_LLAMA_CPP_URL = "http://localhost:8080/v1"


class LlamaCppProvider(BaseProvider):
    """
    llama.cpp provider for GGUF quantized models.

    Uses llama-cpp-python's OpenAI-compatible server mode endpoint.
    Tool calling support depends on the specific GGUF model loaded.
    """

    _provider_name: str = "llama_cpp"

    def __init__(self, api_key: Optional[str] = None, **kwargs: Any):
        super().__init__(api_key=api_key, **kwargs)
        self._default_model = kwargs.get("default_model", "local-model")
        self._base_url = kwargs.get("base_url", DEFAULT_LLAMA_CPP_URL)
        self._context_window_size = kwargs.get("context_window", 4096)
        self._supports_tools_flag = kwargs.get("supports_tools", False)

        client_kwargs: Dict[str, Any] = {
            "api_key": api_key or "not-needed",
            "base_url": self._base_url,
            "timeout": kwargs.get("timeout", 300.0),
            "max_retries": kwargs.get("max_retries", 1),
        }
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
        return self._context_window_size

    @property
    def supports_tools(self) -> bool:
        # Many GGUF models do not support native function calling
        return self._supports_tools_flag

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    async def chat(self, request: LLMRequest) -> LLMResponse:
        """Execute chat completion via llama.cpp server."""
        model = request.model or self._default_model
        start = time.perf_counter()

        api_params: Dict[str, Any] = {
            "model": model,
            "messages": self._build_messages(request.messages),
            "temperature": request.temperature,
            "max_tokens": min(request.max_tokens, self._context_window_size),
            "stream": False,
        }

        # Only include tools if the model supports them
        if request.tools and self._supports_tools_flag:
            api_params["tools"] = request.tools
        if request.tool_choice and self._supports_tools_flag:
            api_params["tool_choice"] = request.tool_choice

        try:
            response = await self._client.chat.completions.create(**api_params)
        except Exception as exc:
            latency = (time.perf_counter() - start) * 1000
            self._record_request(latency, success=False)
            logger.error("llama.cpp chat failed: %s", exc)
            raise

        latency = (time.perf_counter() - start) * 1000
        self._record_request(latency, success=True)

        choice = response.choices[0]
        content = choice.message.content

        tool_calls = None
        if self._supports_tools_flag and choice.message.tool_calls:
            tool_calls = [
                ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=tc.function.arguments,
                )
                for tc in choice.message.tool_calls
            ]

        usage_obj = response.usage
        usage = TokenUsage(
            input_tokens=usage_obj.prompt_tokens if usage_obj else 0,
            output_tokens=usage_obj.completion_tokens if usage_obj else 0,
        )

        finish_reason = choice.finish_reason or "stop"

        return self._build_response(
            content=content,
            model=response.model or model,
            finish_reason=finish_reason,
            usage=usage,
            latency_ms=latency,
            tool_calls=tool_calls,
            metadata={
                "provider": self.provider_name,
                "base_url": self._base_url,
                "context_window": self._context_window_size,
            },
        )

    async def chat_stream(self, request: LLMRequest) -> AsyncIterator[LLMResponse]:
        """Stream chat completion chunks from llama.cpp server."""
        model = request.model or self._default_model
        start = time.perf_counter()

        api_params: Dict[str, Any] = {
            "model": model,
            "messages": self._build_messages(request.messages),
            "temperature": request.temperature,
            "max_tokens": min(request.max_tokens, self._context_window_size),
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if request.tools and self._supports_tools_flag:
            api_params["tools"] = request.tools
        if request.tool_choice and self._supports_tools_flag:
            api_params["tool_choice"] = request.tool_choice

        final_usage = TokenUsage()
        finish_reason = "stop"
        response_id = ""

        try:
            stream = await self._client.chat.completions.create(**api_params)

            async for chunk in stream:
                if not chunk.choices:
                    if chunk.usage:
                        final_usage = TokenUsage(
                            input_tokens=chunk.usage.prompt_tokens or 0,
                            output_tokens=chunk.usage.completion_tokens or 0,
                        )
                    continue

                delta = chunk.choices[0].delta
                chunk_finish = chunk.choices[0].finish_reason

                if chunk_finish:
                    finish_reason = chunk_finish

                if chunk.id:
                    response_id = chunk.id

                yield LLMResponse(
                    id=response_id,
                    model=model,
                    content=delta.content,
                    finish_reason=finish_reason if chunk_finish else None,
                    usage=TokenUsage(),
                    latency_ms=(time.perf_counter() - start) * 1000,
                )

            latency = (time.perf_counter() - start) * 1000
            self._record_request(latency, success=True)

            yield LLMResponse(
                id=response_id,
                model=model,
                content=None,
                tool_calls=None,
                finish_reason=finish_reason,
                usage=final_usage,
                latency_ms=latency,
                metadata={"provider": self.provider_name},
            )

        except Exception as exc:
            latency = (time.perf_counter() - start) * 1000
            self._record_request(latency, success=False)
            logger.error("llama.cpp stream failed: %s", exc)
            raise

    async def health_check(self) -> bool:
        """
        Verify llama.cpp server connectivity.

        Tries the /v1/models endpoint; falls back to a minimal chat request.
        """
        try:
            await self._client.models.list()
            return True
        except Exception:
            # Some llama.cpp builds don't support /models;
            # try a minimal chat completion as fallback
            try:
                await self._client.chat.completions.create(
                    model=self._default_model,
                    messages=[{"role": "user", "content": "ping"}],
                    max_tokens=1,
                )
                return True
            except Exception as exc:
                logger.warning("llama.cpp health check failed: %s", exc)
                return False

    # ------------------------------------------------------------------
    # Token counting
    # ------------------------------------------------------------------

    def count_tokens(self, text: str, model: Optional[str] = None) -> int:
        """
        Count tokens using tiktoken cl100k_base as approximation.

        The actual tokenizer depends on the GGUF model loaded.
        cl100k_base provides a reasonable estimate for most models.
        """
        if not text:
            return 0
        key = "cl100k_base"
        if key not in self._tokenizer_cache:
            try:
                self._tokenizer_cache[key] = tiktoken.get_encoding(key)
            except Exception:
                return len(text) // 4
        return len(self._tokenizer_cache[key].encode(text))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """Convert internal Message objects to API format."""
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
