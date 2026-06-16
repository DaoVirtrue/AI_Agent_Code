"""
vLLM Provider

Connects to internally hosted vLLM servers via their OpenAI-compatible API.
Supports local models served by vLLM with high-throughput inference.
"""

from __future__ import annotations

import logging
import time
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx
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

# Default vLLM internal endpoints
DEFAULT_VLLM_URL = "http://localhost:8000/v1"


class VLLMProvider(BaseProvider):
    """
    vLLM provider for locally hosted models.

    Connects via OpenAI-compatible API. Supports health checking via
    the /health endpoint on the vLLM server.
    """

    _provider_name: str = "vllm"

    def __init__(self, api_key: Optional[str] = None, **kwargs: Any):
        super().__init__(api_key=api_key, **kwargs)
        self._default_model = kwargs.get("default_model", "vllm-model")
        self._base_url = kwargs.get("base_url", DEFAULT_VLLM_URL)
        self._context_window_size = kwargs.get("context_window", 128000)

        # vLLM uses a placeholder API key internally
        client_kwargs: Dict[str, Any] = {
            "api_key": api_key or "EMPTY",
            "base_url": self._base_url,
            "timeout": kwargs.get("timeout", 300.0),
        }
        self._client = AsyncOpenAI(**client_kwargs)
        self._http_client: Optional[httpx.AsyncClient] = None
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
        # vLLM supports OpenAI-compatible function calling on supported models
        return True

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    async def chat(self, request: LLMRequest) -> LLMResponse:
        """Execute chat completion via vLLM's OpenAI-compatible endpoint."""
        model = request.model or self._default_model
        start = time.perf_counter()

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
            logger.error("vLLM chat failed: %s", exc)
            raise

        latency = (time.perf_counter() - start) * 1000
        self._record_request(latency, success=True)

        choice = response.choices[0]
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
            metadata={"provider": self.provider_name, "base_url": self._base_url},
        )

    async def chat_stream(self, request: LLMRequest) -> AsyncIterator[LLMResponse]:
        """Stream chat completion chunks from vLLM."""
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

        final_usage = TokenUsage()
        finish_reason = "stop"
        response_id = ""
        accumulated_tool_calls: Dict[int, Dict[str, Any]] = {}

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
                    pass  # vLLM may not return model per-chunk

                yield LLMResponse(
                    id=response_id,
                    model=model,
                    content=delta.content,
                    finish_reason=finish_reason if chunk_finish else None,
                    usage=TokenUsage(),
                    latency_ms=(time.perf_counter() - start) * 1000,
                )

            tool_calls = None
            if accumulated_tool_calls:
                tool_calls = [
                    ToolCall(
                        id=t["id"],
                        name=t["name"],
                        arguments=t["arguments"],
                    )
                    for t in sorted(accumulated_tool_calls.values(), key=lambda x: x.get("id", ""))
                    if t["name"]
                ]

            latency = (time.perf_counter() - start) * 1000
            self._record_request(latency, success=True)

            yield LLMResponse(
                id=response_id,
                model=model,
                content=None,
                tool_calls=tool_calls,
                finish_reason=finish_reason,
                usage=final_usage,
                latency_ms=latency,
                metadata={"provider": self.provider_name},
            )

        except Exception as exc:
            latency = (time.perf_counter() - start) * 1000
            self._record_request(latency, success=False)
            logger.error("vLLM stream failed: %s", exc)
            raise

    async def health_check(self) -> bool:
        """
        Verify vLLM server connectivity via the /health endpoint.

        vLLM exposes a /health endpoint on the root server (not the /v1 prefix).
        """
        try:
            # Construct the health URL from the base URL
            health_url = self._base_url.rstrip("/").replace("/v1", "") + "/health"
            if self._http_client is None:
                self._http_client = httpx.AsyncClient(timeout=10.0)

            response = await self._http_client.get(health_url)
            return response.status_code == 200
        except Exception as exc:
            logger.warning("vLLM health check failed at %s: %s", self._base_url, exc)
            return False

    # ------------------------------------------------------------------
    # Token counting
    # ------------------------------------------------------------------

    def count_tokens(self, text: str, model: Optional[str] = None) -> int:
        """
        Count tokens using tiktoken cl100k_base as approximation.

        Many vLLM-served models use tokenizers similar to OpenAI's.
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

    async def close(self) -> None:
        """Release HTTP resources."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
