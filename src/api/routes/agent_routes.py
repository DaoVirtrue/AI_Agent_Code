"""Agent 智能体路由：运行 Agent、编排多 Agent 及 Agent 管理。"""

import time
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks

from src.api.dependencies import get_current_tenant, get_token_counter
from src.api.dependencies import TenantContext
from src.api.schemas.agent import (
    AgentRunRequest,
    AgentRunResponse,
    AgentStep,
    OrchestrateRequest,
    ApprovalDecision,
)
from src.api.schemas.common import ErrorResponse
from src.monitoring.logging_setup import get_logger
from src.monitoring.metrics import (
    agent_steps as agent_steps_metric,
    agent_loop_detections,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/agent", tags=["Agent 智能体"])

# In-memory conversation/approval store (production: use Redis/DB)
_conversation_store: dict[str, dict] = {}
_pending_approvals: dict[str, dict] = {}


@router.post(
    "/run",
    response_model=AgentRunResponse,
    responses={
        200: {"description": "Agent 执行完成"},
        400: {"model": ErrorResponse},
        408: {"model": ErrorResponse},
    },
)
async def run_agent(
    request_body: AgentRunRequest,
    http_request: Request,
    tenant: TenantContext = Depends(get_current_tenant),
    token_counter=Depends(get_token_counter),
):
    """运行 Agent 自主执行任务。

    Agent 使用 ReAct（推理+行动）循环或其他配置的 Agent 类型，
    迭代地进行推理和使用工具，直至任务完成。

    支持人机协同（Human-in-the-Loop）审批，适用于敏感工具的执行。
    """
    run_id = f"run-{uuid.uuid4().hex[:12]}"
    start_time = time.monotonic()

    # Get agent executor from app state
    agent_executor = getattr(http_request.app.state, "agent_executor", None)
    if not agent_executor:
        raise HTTPException(
            status_code=503,
            detail=ErrorResponse(
                code="AGENT_SERVICE_UNAVAILABLE",
                message="Agent executor not initialized",
            ).model_dump(),
        )

    try:
        execution_result = await agent_executor.execute(
            task=request_body.task,
            agent_type=request_body.agent_type,
            tools=request_body.tools,
            max_steps=request_body.max_steps,
            model=request_body.model,
            temperature=request_body.temperature,
            system_prompt=request_body.system_prompt,
            verbose=request_body.verbose,
            tenant_id=tenant.tenant_id,
        )
    except Exception as e:
        logger.error("Agent execution failed", error=str(e), task=request_body.task[:200])
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                code="AGENT_EXECUTION_FAILED",
                message=f"Agent execution failed: {str(e)}",
            ).model_dump(),
        )

    elapsed_ms = (time.monotonic() - start_time) * 1000

    # Build step objects
    steps = []
    total_tokens = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for i, step_data in enumerate(execution_result.steps):
        step = AgentStep(
            step_number=i,
            action=step_data.get("action", ""),
            thought=step_data.get("thought"),
            observation=step_data.get("observation"),
            tool_name=step_data.get("tool_name"),
            tool_input=step_data.get("tool_input"),
            tool_output=step_data.get("tool_output"),
            elapsed_ms=step_data.get("elapsed_ms", 0),
            tokens_used=step_data.get("tokens_used", 0),
        )
        steps.append(step)

        total_tokens["prompt_tokens"] += step_data.get("prompt_tokens", 0)
        total_tokens["completion_tokens"] += step_data.get("completion_tokens", 0)
        total_tokens["total_tokens"] += step_data.get("tokens_used", 0)

    # Record metrics
    agent_steps_metric.labels(agent_type=request_body.agent_type).observe(len(steps))

    if execution_result.loop_detected:
        agent_loop_detections.labels(agent_type=request_body.agent_type).inc()

    return AgentRunResponse(
        run_id=run_id,
        result=execution_result.final_output,
        status=execution_result.status,
        steps=steps,
        total_steps=len(steps),
        token_usage=total_tokens,
        elapsed_ms=round(elapsed_ms, 2),
        cost_usd=execution_result.cost_usd,
        loop_detected=execution_result.loop_detected,
    )


@router.post(
    "/orchestrate",
    response_model=dict,
    responses={200: {"description": "多 Agent 编排完成"}},
)
async def orchestrate(
    request_body: OrchestrateRequest,
    http_request: Request,
    tenant: TenantContext = Depends(get_current_tenant),
):
    """编排多个 Agent 协作完成复杂任务。

    支持多种工作流：顺序执行、并行执行、辩论模式和层级模式。
    多个 Agent 协作完成需要多种技能的复杂任务。
    """
    orchestrator = getattr(http_request.app.state, "agent_orchestrator", None)
    if not orchestrator:
        raise HTTPException(
            status_code=503,
            detail=ErrorResponse(
                code="ORCHESTRATOR_UNAVAILABLE",
                message="Agent orchestrator not initialized",
            ).model_dump(),
        )

    try:
        result = await orchestrator.orchestrate(
            task=request_body.task,
            agents=request_body.agents,
            workflow=request_body.workflow,
            max_steps_total=request_body.max_steps_total,
            model=request_body.model,
            tenant_id=tenant.tenant_id,
        )
        return result
    except Exception as e:
        logger.error("Orchestration failed", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                code="ORCHESTRATION_FAILED",
                message=f"Orchestration failed: {str(e)}",
            ).model_dump(),
        )


@router.get(
    "/tools",
    response_model=list[dict],
    responses={200: {"description": "可用 Agent 工具列表"}},
)
async def list_tools(
    http_request: Request,
    tenant: TenantContext = Depends(get_current_tenant),
):
    """列出 Agent 可用的所有工具。

    返回工具定义，包含名称、描述和参数 Schema。
    """
    tool_registry = getattr(http_request.app.state, "tool_registry", None)
    if not tool_registry:
        return []

    tools = await tool_registry.list_tools(tenant_id=tenant.tenant_id)
    return [
        {
            "name": t.name,
            "description": t.description,
            "parameters": t.parameters,
            "requires_approval": t.requires_approval,
        }
        for t in tools
    ]


@router.post(
    "/conversations/{conv_id}/approve",
    response_model=dict,
    responses={
        200: {"description": "审批决定已记录"},
        404: {"model": ErrorResponse},
    },
)
async def approve_tool_execution(
    conv_id: str,
    decision: ApprovalDecision,
    tenant: TenantContext = Depends(get_current_tenant),
):
    """人机协同：批准或拒绝待处理的 Agent 工具执行。

    当 Agent 需要对工具调用进行审批时，它会暂停并等待
    通过此端点的审批决定。
    """
    pending = _pending_approvals.get(conv_id)
    if not pending:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(
                code="APPROVAL_NOT_FOUND",
                message=f"No pending approval for conversation {conv_id}",
            ).model_dump(),
        )

    if decision.approved:
        tool_input = decision.modified_input if decision.modified_input else pending["tool_input"]
        _pending_approvals[conv_id] = {
            **pending,
            "status": "approved",
            "tool_input": tool_input,
            "comment": decision.comment,
        }
        logger.info(
            "Tool execution approved",
            conv_id=conv_id,
            tool_name=pending["tool_name"],
        )
    else:
        _pending_approvals[conv_id] = {
            **pending,
            "status": "rejected",
            "comment": decision.comment,
        }
        logger.info(
            "Tool execution rejected",
            conv_id=conv_id,
            tool_name=pending["tool_name"],
            reason=decision.comment,
        )

    return {
        "conv_id": conv_id,
        "status": "approved" if decision.approved else "rejected",
        "comment": decision.comment,
    }


@router.get(
    "/conversations",
    response_model=dict,
    responses={200: {"description": "Agent 对话列表"}},
)
async def list_conversations(
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    tenant: TenantContext = Depends(get_current_tenant),
):
    """列出当前租户的 Agent 对话历史。"""
    tenant_conversations = [
        conv for conv in _conversation_store.values()
        if conv.get("tenant_id") == tenant.tenant_id
    ]

    if status:
        tenant_conversations = [
            c for c in tenant_conversations if c.get("status") == status
        ]

    # Paginate
    total = len(tenant_conversations)
    start = (page - 1) * page_size
    end = start + page_size
    items = tenant_conversations[start:end]

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get(
    "/conversations/{conv_id}",
    response_model=dict,
    responses={
        200: {"description": "对话详情"},
        404: {"model": ErrorResponse},
    },
)
async def get_conversation(
    conv_id: str,
    tenant: TenantContext = Depends(get_current_tenant),
):
    """获取指定 Agent 对话的详细信息。"""
    conv = _conversation_store.get(conv_id)
    if not conv:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(
                code="CONVERSATION_NOT_FOUND",
                message=f"Conversation {conv_id} not found",
            ).model_dump(),
        )

    if conv.get("tenant_id") != tenant.tenant_id:
        raise HTTPException(
            status_code=403,
            detail=ErrorResponse(
                code="FORBIDDEN",
                message="This conversation belongs to a different tenant",
            ).model_dump(),
        )

    return conv
