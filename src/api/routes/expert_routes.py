"""业务专家路由 — 定义/运行可配置角色化 Agent + MCP 授权端点。"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from src.api.dependencies import get_current_tenant
from src.api.dependencies import TenantContext
from src.observability.logging_setup import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/experts", tags=["业务专家"])


class ExpertDefineRequest(BaseModel):
    """定义一个业务专家。"""

    name: str = Field(..., description="专家名称", min_length=1, max_length=100)
    role: str = Field("", description="角色描述")
    system_prompt: str = Field("", description="自定义系统提示词")
    skills: list[str] = Field(default_factory=list, description="可调用的技能/工具名列表")
    description: str = Field("", description="专家简介")


class ExpertRunRequest(BaseModel):
    """运行一个业务专家。"""

    expert_name: str = Field(..., description="专家名称")
    task: str = Field(..., description="任务描述", min_length=1, max_length=50000)


class ApprovalDecision(BaseModel):
    """MCP 授权决定。"""

    approved: bool = Field(..., description="是否批准")
    comment: str = Field("", description="备注")


@router.post("", response_model=dict)
async def define_expert(
    request_body: ExpertDefineRequest,
    http_request: Request,
    tenant: TenantContext = Depends(get_current_tenant),
):
    """定义一个业务专家（角色+提示词+技能+MCP）。"""
    from src.agents.expert import ExpertConfig

    registry = http_request.app.state.expert_registry
    config = ExpertConfig(
        name=request_body.name,
        role=request_body.role,
        system_prompt=request_body.system_prompt,
        skills=request_body.skills,
        description=request_body.description,
    )
    registry.register(config, tenant_id=tenant.tenant_id)
    return {"name": config.name, "status": "defined", "skills": config.skills}


@router.get("", response_model=dict)
async def list_experts(
    http_request: Request,
    tenant: TenantContext = Depends(get_current_tenant),
):
    """列出已定义的业务专家。"""
    registry = http_request.app.state.expert_registry
    experts = registry.list_all(tenant_id=tenant.tenant_id)
    return {"items": experts, "total": len(experts)}


@router.post("/run", response_model=dict)
async def run_expert(
    request_body: ExpertRunRequest,
    http_request: Request,
    tenant: TenantContext = Depends(get_current_tenant),
):
    """运行一个业务专家完成任务。"""
    registry = http_request.app.state.expert_registry
    expert = registry.get(request_body.expert_name, tenant_id=tenant.tenant_id)
    if expert is None:
        raise HTTPException(status_code=404, detail=f"专家 '{request_body.expert_name}' 未定义")

    result = await expert.run(request_body.task)
    return {
        "expert_name": request_body.expert_name,
        "output": result.output,
        "tool_calls": result.tool_calls,
        "status": result.status,
        "error": result.error,
    }


@router.get("/approvals", response_model=dict)
async def list_approvals(
    http_request: Request,
    tenant: TenantContext = Depends(get_current_tenant),
):
    """列出待审批的 MCP 工具调用。"""
    gate = http_request.app.state.approval_gate
    return {"pending": gate.list_pending(), "history": gate.list_history()}


@router.post("/approvals/{request_id}", response_model=dict)
async def decide_approval(
    request_id: str,
    decision: ApprovalDecision,
    http_request: Request,
    tenant: TenantContext = Depends(get_current_tenant),
):
    """批准/拒绝一个待审批的 MCP 工具调用。"""
    gate = http_request.app.state.approval_gate
    ok = gate.approve(request_id) if decision.approved else gate.reject(request_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"审批请求 '{request_id}' 不存在或已处理")
    return {"request_id": request_id, "approved": decision.approved, "comment": decision.comment}
