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
    """定义一个业务专家（专属智能体）。"""

    name: str = Field(..., description="专家名称", min_length=1, max_length=100)
    role: str = Field("", description="角色描述")
    system_prompt: str = Field("", description="自定义系统提示词")
    skills: list[str] = Field(default_factory=list, description="可调用的技能/MCP 工具名列表")
    knowledge_bases: list[str] = Field(default_factory=list, description="绑定的专属知识库名列表")
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
        knowledge_bases=request_body.knowledge_bases,
        description=request_body.description,
    )
    registry.register(config, tenant_id=tenant.tenant_id)
    return {"name": config.name, "status": "defined", "skills": config.skills, "knowledge_bases": config.knowledge_bases}


@router.get("", response_model=dict)
async def list_experts(
    http_request: Request,
    tenant: TenantContext = Depends(get_current_tenant),
):
    """列出已定义的业务专家。"""
    registry = http_request.app.state.expert_registry
    experts = registry.list_all(tenant_id=tenant.tenant_id)
    return {"items": experts, "total": len(experts)}


@router.get("/available-tools", response_model=dict)
async def list_available_tools(
    http_request: Request,
    tenant: TenantContext = Depends(get_current_tenant),
):
    """列出可绑定到专家的所有技能/MCP 工具（含中文名）。"""
    registry = http_request.app.state.expert_registry
    tools = []
    for name, tool in registry.tools.items():
        d = tool.definition
        tools.append({
            "name": name,
            "label": _TOOL_LABELS.get(name, name),
            "description": d.description,
            "category": d.category,
            "requires_approval": d.requires_approval,
        })
    return {"tools": tools, "total": len(tools)}


# 工具名 -> 中文名（前端展示用，value 仍用英文 name 作为内部标识）
_TOOL_LABELS = {
    "cli.execute": "执行命令行（操作电脑）",
    "document.generate": "生成文档（md/docx/xlsx/pptx）",
    "document.ocr": "图片文字识别（OCR）",
    "web_search": "网络搜索",
    "calculator": "计算器",
    "web_fetch": "网页抓取",
    "search": "搜索",
    "search_web": "网络搜索",
    "search_knowledge_base": "知识库检索",
    "query_database": "数据库查询",
    "execute_code": "执行代码",
    "send_email": "发送邮件",
    "create_document": "创建文档",
    "schedule_task": "定时任务",
    "call_api": "调用 API",
    "read_file": "读取文件",
    "write_file": "写入文件",
    "list_directory": "列出目录",
    "search_files": "搜索文件",
}


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
