"""权限管理路由 — 配置工具/技能的授权规则。"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from src.api.dependencies import get_current_tenant
from src.api.dependencies import TenantContext
from src.observability.logging_setup import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/permissions", tags=["权限管理"])


class PermissionSetRequest(BaseModel):
    """设置一个工具的授权规则。"""

    tool_name: str = Field(..., description="工具名")
    requires_approval: bool = Field(..., description="是否需要授权")
    reason: str = Field("", description="授权原因/说明")


@router.get("", response_model=dict)
async def list_permissions(
    request: Request,
    tenant: TenantContext = Depends(get_current_tenant),
):
    """列出所有授权规则。"""
    store = request.app.state.permission_store
    return {"items": [r.to_dict() for r in store.list_rules()], "total": len(store.list_rules())}


@router.post("", response_model=dict)
async def set_permission(
    request_body: PermissionSetRequest,
    request: Request,
    tenant: TenantContext = Depends(get_current_tenant),
):
    """设置/更新一个工具的授权规则。"""
    store = request.app.state.permission_store
    rule = store.set_rule(request_body.tool_name, request_body.requires_approval, request_body.reason)
    return {"status": "saved", "rule": rule.to_dict()}
