"""
Anthropic Provider

Wraps the Anthropic AsyncAnthropic client for Claude models.
Supports ephemeral prompt caching via cache_control blocks.
"""

from __future__ import annotations

import logging
import time
from typing import Any, AsyncIterator, Dict, List, Optional, Union

import tiktoken
from anthropic import AsyncAnthropic

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
# Model-specific context windows (Claude models)
# ---------------------------------------------------------------------------
_ANTHROPIC_CONTEXT_WINDOWS: Dict[str, int] = {
    "claude-opus-4": 200000,
    "claude-sonnet-4": 200000,
    "claude-haiku-3.5": 200000,
    "claude-opus-3.5": 200000,
    "claude-sonnet-3.5": 200000,
    "claude-haiku-3": 200000,
    "claude-3-opus": 200000,
    "claude-3-sonnet": 200000,
    "claude-3-haiku": 200000,
}

# Pricing per 1M tokens (input, output)
_PRICING: Dict[str, tuple] = {
    "claude-opus-4": (15.00, 75.00),
    "claude-sonnet-4": (3.00, 15.00),
    "claude-haiku-3.5": (0.80, 4.00),
    "claude-opus-3.5": (15.00, 75.00),
    "claude-sonnet-3.5": (3.00, 15.00),
    "claude-haiku-3": (0.25, 1.25),
    "claude-3-opus": (15.00, 75.00),
    "claude-3-sonnet": (3.00, 15.00),
    "claude-3-haiku": (0.25, 1.25),
}

# Cached pricing multiplier (90% cost reduction for cache hits)
_CACHE_PRICE_MULTIPLIER = 0.10


class AnthropicProvider(BaseProvider):
    """
    Anthropic provider for Claude models.

    Handles:
      - Mapping messages to Anthropic's system/content format
      - Ephemeral prompt caching via cache_control blocks
      - Token counting via tiktoken approximation
    """

    _provider_name: str = "anthropic"

    def __init__(self, api_key: Optional[str] = None, **kwargs: Any):
        super().__init__(api_key=api_key, **kwargs)
        self._default_model = kwargs.get("default_model", "claude-sonnet-4")
        self._enable_caching = kwargs.get("enable_caching", True)
        client_kwargs: Dict[str, Any] = {"api_key": api_key}
        if "base_url" in kwargs:
            client_kwargs["base_url"] = kwargs["base_url"]
        self._client = AsyncAnthropic(**client_kwargs)
        self._tokenizer: Optional[tiktoken.Encoding] = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def context_window(self) -> int:
        return _ANTHROPIC_CONTEXT_WINDOWS.get(
            self._default_model, 200000
        )

    @property
    def supports_tools(self) -> bool:
        return True

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    async def chat(self, request: LLMRequest) -> LLMResponse:
        """Execute a chat completion via Anthropic's Messages API."""
        model = request.model or self._default_model
        start = time.perf_counter()

        system_content, messages_content = self._split_system_messages(request.messages)
        api_messages = self._build_messages(messages_content, enable_caching=self._enable_caching)

        api_params: Dict[str, Any] = {
            "model": model,
            "max_tokens": request.max_tokens,
            "messages": api_messages,
            "temperature": request.temperature,
        }

        if system_content:
            # Anthropic supports cache_control on system blocks
            if self._enable_caching:
                api_params["system"] = [
                    {
                        "type": "text",
                        "text": system_content,
                        "cache_control": {"type": "ephemeral"},
                    }
                ]
            else:
                api_params["system"] = system_content

        if request.tools:
            api_params["tools"] = self._convert_tools_for_anthropic(request.tools)
        if request.tool_choice:
            api_params["tool_choice"] = self._convert_tool_choice(request.tool_choice)

        try:
            response = await self._client.messages.create(**api_params)
        except Exception as exc:
            latency = (time.perf_counter() - start) * 1000
            self._record_request(latency, success=False)
            logger.error("Anthropic chat failed: %s", exc)
            raise

        latency = (time.perf_counter() - start) * 1000
        self._record_request(latency, success=True)

        # Parse response
        content = None
        tool_calls = None
        text_blocks: List[str] = []
        tool_blocks: List[ToolCall] = []

        for block in response.content:
            if block.type == "text":
                text_blocks.append(block.text)
            elif block.type == "tool_use":
                tool_blocks.append(
                    ToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=self._serialize_tool_input(block.input),
                    )
                )

        if text_blocks:
            content = "\n".join(text_blocks)
        if tool_blocks:
            tool_calls = tool_blocks

        # Parse usage
        usage_obj = response.usage
        cached_tokens = getattr(usage_obj, "cache_read_input_tokens", 0) if usage_obj else 0

        usage = TokenUsage(
            input_tokens=usage_obj.input_tokens if usage_obj else 0,
            output_tokens=usage_obj.output_tokens if usage_obj else 0,
            cached_tokens=cached_tokens,
        )

        finish_reason = response.stop_reason or "stop"
        if finish_reason == "end_turn":
            finish_reason = "stop"
        elif finish_reason == "tool_use":
            finish_reason = "tool_calls"

        metadata: Dict[str, Any] = {
            "provider": self.provider_name,
            "request_model": request.model,
            "actual_model": response.model,
            "stop_sequence": getattr(response, "stop_sequence", None),
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
        """Stream chat completion chunks from Anthropic."""
        model = request.model or self._default_model
        start = time.perf_counter()

        system_content, messages_content = self._split_system_messages(request.messages)
        api_messages = self._build_messages(messages_content, enable_caching=self._enable_caching)

        api_params: Dict[str, Any] = {
            "model": model,
            "max_tokens": request.max_tokens,
            "messages": api_messages,
            "temperature": request.temperature,
        }

        if system_content:
            if self._enable_caching:
                api_params["system"] = [
                    {
                        "type": "text",
                        "text": system_content,
                        "cache_control": {"type": "ephemeral"},
                    }
                ]
            else:
                api_params["system"] = system_content

        if request.tools:
            api_params["tools"] = self._convert_tools_for_anthropic(request.tools)
        if request.tool_choice:
            api_params["tool_choice"] = self._convert_tool_choice(request.tool_choice)

        accumulated_text: List[str] = []
        accumulated_tool_calls: Dict[str, Dict[str, Any]] = {}
        final_usage = TokenUsage()
        finish_reason = "stop"
        response_id = ""
        actual_model = ""

        try:
            async with self._client.messages.stream(**api_params) as stream:
                async for event in stream:
                    if event.type == "message_start":
                        if event.message:
                            response_id = event.message.id
                            actual_model = event.message.model
                            if hasattr(event.message, "usage") and event.message.usage:
                                final_usage.input_tokens = event.message.usage.input_tokens

                    elif event.type == "content_block_start":
                        block = event.content_block
                        if block.type == "tool_use":
                            accumulated_tool_calls[block.id] = {
                                "id": block.id,
                                "name": block.name,
                                "arguments": "",
                            }

                    elif event.type == "content_block_delta":
                        delta = event.delta
                        if delta.type == "text_delta":
                            accumulated_text.append(delta.text)
                            yield LLMResponse(
                                id=response_id,
                                model=actual_model or model,
                                content=delta.text,
                                finish_reason=None,
                                usage=TokenUsage(),
                                latency_ms=(time.perf_counter() - start) * 1000,
                            )
                        elif delta.type == "input_json_delta":
                            tc = accumulated_tool_calls.get(event.index or "")
                            if tc is not None:
                                tc["arguments"] += delta.partial_json

                    elif event.type == "message_delta":
                        if hasattr(event, "usage") and event.usage:
                            final_usage.output_tokens = event.usage.output_tokens
                        if hasattr(event.delta, "stop_reason"):
                            finish_reason = event.delta.stop_reason or "stop"
                            if finish_reason == "end_turn":
                                finish_reason = "stop"
                            elif finish_reason == "tool_use":
                                finish_reason = "tool_calls"

            # Build final tool calls
            tool_calls = None
            if accumulated_tool_calls:
                tool_calls = [
                    ToolCall(id=t["id"], name=t["name"], arguments=t["arguments"])
                    for t in accumulated_tool_calls.values()
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
            logger.error("Anthropic stream failed: %s", exc)
            raise

    async def health_check(self) -> bool:
        """Verify connectivity by making a minimal API call."""
        try:
            await self._client.messages.create(
                model=self._default_model,
                max_tokens=1,
                messages=[{"role": "user", "content": "ping"}],
            )
            return True
        except Exception as exc:
            logger.warning("Anthropic health check failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Token counting (tiktoken approximation for Claude)
    # ------------------------------------------------------------------

    def count_tokens(self, text: str, model: Optional[str] = None) -> int:
        """
        Estimate token count using tiktoken's cl100k_base encoding.

        Anthropic does not provide a public tokenizer; cl100k_base provides
        a close approximation for Claude models.
        """
        if not text:
            return 0
        if self._tokenizer is None:
            try:
                self._tokenizer = tiktoken.get_encoding("cl100k_base")
            except Exception:
                # Ultimate fallback: ~4 chars per token
                return len(text) // 4
        return len(self._tokenizer.encode(text))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _split_system_messages(
        messages: List[Message],
    ) -> tuple:
        """
        Split messages into a system prompt string and non-system messages.

        Anthropic's API requires system prompts in a separate 'system' parameter,
        not as regular messages.
        """
        system_parts: List[str] = []
        non_system: List[Message] = []

        for msg in messages:
            if msg.role == "system":
                content = msg.content
                if isinstance(content, str):
                    system_parts.append(content)
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and "text" in block:
                            system_parts.append(block["text"])
            else:
                non_system.append(msg)

        return ("\n\n".join(system_parts) if system_parts else "", non_system)

    def _build_messages(
        self,
        messages: List[Message],
        enable_caching: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Convert internal Message objects to Anthropic API format.

        Optionally adds cache_control to the last user message and last
        assistant message for ephemeral caching.
        """
        result: List[Dict[str, Any]] = []
        for i, msg in enumerate(messages):
            role = msg.role
            if role == "user":
                role = "user"
            elif role == "assistant":
                role = "assistant"
            else:
                continue

            content: Any = msg.content

            # If content is plain text, wrap in a text block
            if isinstance(content, str):
                if isinstance(content, str):
                    content_blocks: List[Dict[str, Any]] = [
                        {"type": "text", "text": content}
                    ]
                else:
                    content_blocks = content

            elif isinstance(content, list):
                content_blocks = content
            else:
                content_blocks = [{"type": "text", "text": str(content)}]

            # Add tool calls if present (for assistant messages)
            if msg.tool_calls and role == "assistant":
                for tc in msg.tool_calls:
                    try:
                        import json
                        tool_input = json.loads(tc.arguments)
                    except (json.JSONDecodeError, TypeError):
                        tool_input = {}
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.name,
                        "input": tool_input,
                    })

            # Add tool result blocks
            if msg.tool_call_id:
                content_blocks = [{
                    "type": "tool_result",
                    "tool_use_id": msg.tool_call_id,
                    "content": content if isinstance(content, str) else str(content),
                }]

            # Apply cache_control to the last content block
            if enable_caching and content_blocks:
                content_blocks[-1]["cache_control"] = {"type": "ephemeral"}

            result.append({"role": role, "content": content_blocks})

        return result

    @staticmethod
    def _convert_tools_for_anthropic(
        tools: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Convert OpenAI-style tool definitions to Anthropic format."""
        converted = []
        for tool in tools:
            if tool.get("type") == "function":
                func = tool["function"]
                converted.append({
                    "name": func["name"],
                    "description": func.get("description", ""),
                    "input_schema": func.get("parameters", {"type": "object", "properties": {}}),
                })
            else:
                converted.append(tool)
        return converted

    @staticmethod
    def _convert_tool_choice(
        tool_choice: Union[str, Dict[str, Any]],
    ) -> Any:
        """Convert OpenAI-style tool_choice to Anthropic format."""
        if isinstance(tool_choice, str):
            mapping = {
                "auto": {"type": "auto"},
                "none": {"type": "none"},
                "required": {"type": "any"},
            }
            return mapping.get(tool_choice, {"type": "auto"})
        if isinstance(tool_choice, dict) and "function" in tool_choice:
            return {"type": "tool", "name": tool_choice["function"]["name"]}
        return tool_choice

    @staticmethod
    def _serialize_tool_input(input_data: Any) -> str:
        """Serialize tool input dict to JSON string."""
        import json
        if isinstance(input_data, str):
            return input_data
        return json.dumps(input_data, ensure_ascii=False)

    def _compute_cost(self, model: str, usage: TokenUsage) -> float:
        """Compute approximate USD cost including cache discounts."""
        input_price, output_price = _PRICING.get(model, (0.0, 0.0))
        if input_price == 0.0:
            for known, prices in _PRICING.items():
                if model.startswith(known):
                    input_price, output_price = prices
                    break

        # Cache hits get 90% discount on input
        regular_input = usage.input_tokens - usage.cached_tokens
        cached_input = usage.cached_tokens

        cost = (regular_input / 1_000_000) * input_price + \
               (cached_input / 1_000_000) * input_price * _CACHE_PRICE_MULTIPLIER + \
               (usage.output_tokens / 1_000_000) * output_price
        return round(cost, 6)
