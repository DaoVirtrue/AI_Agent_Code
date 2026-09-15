"""AI 网关路由：Chat Completions、模型列表和网关健康检查。"""

import time
import uuid
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse

from src.api.dependencies import get_gateway, get_current_tenant, get_token_counter
from src.api.schemas.gateway import (
    ChatRequest,
    ChatResponse,
    ModelInfo,
    TokenUsage,
    StreamChunk,
    MessageDict,
)
from src.api.schemas.common import ErrorResponse
from src.observability.logging_setup import get_logger
from src.observability.metrics import (
    gateway_requests as gw_requests_metric,
    gateway_latency as gw_latency_metric,
    token_usage as token_usage_metric,
    cost_total as cost_total_metric,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/gateway", tags=["AI 网关"])


@router.post(
    "/chat/completions",
    response_model=ChatResponse,
    responses={
        200: {"description": "Chat Completion 成功"},
        400: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
async def chat_completions(
    request_body: ChatRequest,
    http_request: Request,
    gateway=Depends(get_gateway),
    tenant=Depends(get_current_tenant),
    token_counter=Depends(get_token_counter),
):
    """向 LLM 网关发送 Chat Completion 请求。

    支持流式（SSE）响应，设置 stream=True 即可启用。
    网关负责路由、故障转移、速率限制和成本追踪。
    """
    request_id = str(uuid.uuid4())
    start_time = time.monotonic()

    # Check rate limits
    rate_limit_result = await gateway.rate_limiter.check(
        tenant_id=tenant.tenant_id,
        model=request_body.model,
    )
    if not rate_limit_result.allowed:
        raise HTTPException(
            status_code=429,
            detail=ErrorResponse(
                code="RATE_LIMITED",
                message=f"Rate limit exceeded. Retry after {rate_limit_result.retry_after} seconds.",
                details={
                    "retry_after_seconds": rate_limit_result.retry_after,
                    "limit": rate_limit_result.limit,
                    "current": rate_limit_result.current,
                },
            ).model_dump(),
        )

    # Convert messages to dicts
    messages = [msg.model_dump() for msg in request_body.messages]

    # Estimate input tokens
    input_tokens = await token_counter.count_tokens(
        model=request_body.model,
        messages=messages,
    )

    # Handle streaming
    if request_body.stream:
        return await _handle_streaming(
            gateway=gateway,
            request_body=request_body,
            messages=messages,
            request_id=request_id,
            tenant=tenant,
            input_tokens=input_tokens,
            token_counter=token_counter,
        )

    # Non-streaming request
    try:
        result = await gateway.route(
            model=request_body.model,
            messages=messages,
            temperature=request_body.temperature,
            max_tokens=request_body.max_tokens,
            top_p=request_body.top_p,
            tools=request_body.tools,
            tool_choice=request_body.tool_choice,
            stop=request_body.stop,
            response_format=request_body.response_format,
            tenant_id=tenant.tenant_id,
        )
    except Exception as e:
        elapsed_ms = (time.monotonic() - start_time) * 1000
        gw_requests_metric.labels(
            tenant_id=tenant.tenant_id,
            provider="unknown",
            model=request_body.model,
            status="error",
        ).inc()
        logger.error("Gateway routing error", error=str(e), tenant_id=tenant.tenant_id)
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                code="GATEWAY_ERROR",
                message=f"Failed to route request: {str(e)}",
                details={"model": request_body.model},
            ).model_dump(),
        )

    elapsed_ms = (time.monotonic() - start_time) * 1000

    # Track token usage
    output_tokens = result.get("output_tokens", 0)
    cached_tokens = result.get("cached_tokens", 0)
    provider = result.get("provider", "unknown")
    total_tokens = input_tokens + output_tokens

    token_usage_metric.labels(
        tenant_id=tenant.tenant_id,
        provider=provider,
        model=request_body.model,
        type="input",
    ).inc(input_tokens)
    token_usage_metric.labels(
        tenant_id=tenant.tenant_id,
        provider=provider,
        model=request_body.model,
        type="output",
    ).inc(output_tokens)
    if cached_tokens:
        token_usage_metric.labels(
            tenant_id=tenant.tenant_id,
            provider=provider,
            model=request_body.model,
            type="cached",
        ).inc(cached_tokens)

    # Track cost
    cost_usd = result.get("cost_usd", 0.0)
    cost_total_metric.labels(
        tenant_id=tenant.tenant_id,
        provider=provider,
        model=request_body.model,
    ).inc(cost_usd)

    # Record metrics
    gw_requests_metric.labels(
        tenant_id=tenant.tenant_id,
        provider=provider,
        model=request_body.model,
        status="success",
    ).inc()
    gw_latency_metric.labels(
        provider=provider,
        model=request_body.model,
    ).observe(elapsed_ms / 1000)

    usage = TokenUsage(
        prompt_tokens=input_tokens,
        completion_tokens=output_tokens,
        total_tokens=total_tokens,
        cached_tokens=cached_tokens,
    )

    return ChatResponse(
        id=request_id,
        model=request_body.model,
        content=result.get("content", ""),
        finish_reason=result.get("finish_reason", "stop"),
        usage=usage,
        cost_usd=cost_usd,
        latency_ms=round(elapsed_ms, 2),
        tool_calls=result.get("tool_calls"),
    )


async def _handle_streaming(
    gateway,
    request_body: ChatRequest,
    messages: list,
    request_id: str,
    tenant,
    input_tokens: int,
    token_counter,
) -> StreamingResponse:
    """处理流式 Chat Completion（SSE）。"""

    async def event_generator():
        start_time = time.monotonic()
        chunk_index = 0
        total_content = ""
        first_token_time = None

        try:
            async for chunk in gateway.route_stream(
                model=request_body.model,
                messages=messages,
                temperature=request_body.temperature,
                max_tokens=request_body.max_tokens,
                top_p=request_body.top_p,
                tools=request_body.tools,
                tenant_id=tenant.tenant_id,
            ):
                if first_token_time is None:
                    first_token_time = time.monotonic()
                    from src.observability.metrics import ttft_histogram
                    ttft_histogram.observe(first_token_time - start_time)

                content_delta = chunk.get("content_delta", "")
                total_content += content_delta

                chunk_data = StreamChunk(
                    id=request_id,
                    model=request_body.model,
                    delta_content=content_delta,
                    delta_tool_calls=chunk.get("tool_call_delta"),
                    finish_reason=chunk.get("finish_reason"),
                    index=chunk_index,
                )

                yield {
                    "event": "delta",
                    "data": chunk_data.model_dump_json(),
                }
                chunk_index += 1

                # Record inter-token latency
                from src.observability.metrics import itl_histogram
                itl_histogram.observe(time.monotonic() - start_time)

            # Send final event
            elapsed_ms = (time.monotonic() - start_time) * 1000
            final_usage = await token_counter.count_tokens(
                model=request_body.model,
                text=total_content,
            )

            yield {
                "event": "done",
                "data": json.dumps({
                    "id": request_id,
                    "model": request_body.model,
                    "usage": {
                        "prompt_tokens": input_tokens,
                        "completion_tokens": final_usage,
                        "total_tokens": input_tokens + final_usage,
                    },
                    "finish_reason": "stop",
                    "latency_ms": round(elapsed_ms, 2),
                }),
            }

        except Exception as e:
            logger.error("Streaming error", error=str(e))
            yield {
                "event": "error",
                "data": json.dumps({"error": str(e)}),
            }

    return EventSourceResponse(event_generator())


@router.get(
    "/models",
    response_model=list[ModelInfo],
    responses={200: {"description": "可用模型列表"}},
)
async def list_models(
    gateway=Depends(get_gateway),
    tenant=Depends(get_current_tenant),
):
    """列出所有可用的 LLM 模型及其能力和定价。

    返回按租户访问权限过滤的模型列表。
    """
    models = await gateway.list_models(tenant_id=tenant.tenant_id)

    return [
        ModelInfo(
            id=m.id,
            provider=m.provider,
            display_name=m.display_name,
            context_window=m.context_window,
            max_output_tokens=m.max_output_tokens,
            capabilities=m.capabilities,
            pricing=m.pricing,
            supports_streaming=m.supports_streaming,
            supports_tools=m.supports_tools,
            availability=m.availability,
        )
        for m in models
    ]


@router.get(
    "/health",
    response_model=dict,
    responses={200: {"description": "网关健康状态"}},
)
async def gateway_health(
    gateway=Depends(get_gateway),
):
    """获取网关健康状态。

    返回 provider 状态、断路器状态和速率限制器状态。
    """
    health_data = await gateway.health_check()
    return {
        "status": health_data.get("status", "healthy"),
        "providers": health_data.get("providers", {}),
        "circuit_breakers": health_data.get("circuit_breakers", {}),
        "rate_limiters": health_data.get("rate_limiters", {}),
        "uptime_seconds": health_data.get("uptime_seconds", 0),
    }
