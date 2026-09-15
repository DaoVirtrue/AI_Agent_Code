"""
DeepSeek Provider

OpenAI-compatible API via openai client with base_url pointing to
DeepSeek's API. Supports function calling with full OpenAI compatibility.
"""

from __future__ import annotations

import logging
import time
from typing import Any, AsyncIterator, Dict, List, Optional, Union

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

DEEPSEEK_BASE_URL = "https://api.deepseek.com"

# Context windows
_DEEPSEEK_CONTEXT_WINDOWS: Dict[str, int] = {
    "deepseek-chat": 65536,
    "deepseek-reasoner": 65536,
}

# Pricing per 1M tokens (input, output) — current DeepSeek pricing
_PRICING: Dict[str, tuple] = {
    "deepseek-chat": (0.27, 1.10),       # $0.27/M input, $1.10/M output
    "deepseek-reasoner": (0.55, 2.19),   # $0.55/M input, $2.19/M output
}


class DeepSeekProvider(BaseProvider):
    """
    DeepSeek provider via OpenAI-compatible API.

    Uses the openai AsyncOpenAI client pointed at api.deepseek.com.
    Fully compatible with OpenAI's function calling format.
    """

    _provider_name: str = "deepseek"

    def __init__(self, api_key: Optional[str] = None, **kwargs: Any):
        super().__init__(api_key=api_key, **kwargs)
        self._default_model = kwargs.get("default_model", "deepseek-chat")
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=kwargs.get("base_url", DEEPSEEK_BASE_URL),
        )
        self._tokenizer_cache: Dict[str, tiktoken.Encoding] = {}

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def context_window(self) -> int:
        return _DEEPSEEK_CONTEXT_WINDOWS.get(self._default_model, 65536)

    @property
    def supports_tools(self) -> bool:
        # DeepSeek supports OpenAI-compatible function calling
        return True

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    async def chat(self, request: LLMRequest) -> LLMResponse:
        """Execute chat completion via DeepSeek's OpenAI-compatible endpoint."""
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
            logger.error("DeepSeek chat failed: %s", exc)
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
            cached_tokens=0,  # DeepSeek does not expose cache tokens separately
        )

        finish_reason = choice.finish_reason or "stop"

        metadata: Dict[str, Any] = {
            "provider": self.provider_name,
            "request_model": request.model,
            "actual_model": response.model,
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
        """Stream chat completion chunks from DeepSeek."""
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
        actual_model = ""
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
                    actual_model = chunk.model

                yield LLMResponse(
                    id=response_id,
                    model=actual_model or model,
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
                model=actual_model or model,
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
            logger.error("DeepSeek stream failed: %s", exc)
            raise

    async def health_check(self) -> bool:
        """Verify connectivity by listing available models."""
        try:
            await self._client.models.list()
            return True
        except Exception as exc:
            logger.warning("DeepSeek health check failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Token counting
    # ------------------------------------------------------------------

    def count_tokens(self, text: str, model: Optional[str] = None) -> int:
        """
        Count tokens using tiktoken cl100k_base as approximation.

        DeepSeek uses a similar tokenizer to OpenAI's cl100k_base.
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

    def _compute_cost(self, model: str, usage: TokenUsage) -> float:
        """Compute USD cost based on DeepSeek pricing."""
        input_price, output_price = _PRICING.get(model, (0.0, 0.0))
        if input_price == 0.0:
            for known, prices in _PRICING.items():
                if model.startswith(known):
                    input_price, output_price = prices
                    break
        cost = (usage.input_tokens / 1_000_000) * input_price + \
               (usage.output_tokens / 1_000_000) * output_price
        return round(cost, 6)
