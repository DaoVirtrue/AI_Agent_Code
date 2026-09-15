"""MCP 集成路由：Model Context Protocol 服务器管理与工具调用。"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from src.api.dependencies import get_current_tenant
from src.api.dependencies import TenantContext
from src.api.schemas.common import ErrorResponse
from src.observability.logging_setup import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/mcp", tags=["MCP 集成"])


@router.get(
    "/.well-known",
    response_model=dict,
    responses={200: {"description": "MCP 服务器声明/发现端点"}},
)
async def mcp_manifest(
    request: Request,
):
    """MCP 服务器声明 —— 将此平台作为 MCP 服务器对外发布。

    此端点遵循 MCP 规范进行服务发现，允许 MCP 客户端发现
    可用的工具和资源。
    """
    return {
        "protocol_version": "0.2.0",
        "server_info": {
            "name": "llm-platform",
            "version": "1.0.0",
            "description": "LLM Platform MCP Server - Gateway, RAG, and Agent tools",
        },
        "capabilities": {
            "tools": True,
            "resources": True,
            "prompts": True,
        },
        "endpoints": {
            "tools": "/v1/mcp/tools/list",
            "resources": "/v1/mcp/resources/list",
            "prompts": "/v1/mcp/prompts/list",
        },
    }


@router.post(
    "/tools/list",
    response_model=dict,
    responses={200: {"description": "可用 MCP 工具列表"}},
)
async def mcp_list_tools(
    request: Request,
    server_name: Optional[str] = None,
    tenant: TenantContext = Depends(get_current_tenant),
):
    """列出 MCP 服务器提供的工具。

    如果指定了 server_name，则仅列出该服务器的工具。
    否则列出所有已连接 MCP 服务器的工具。
    """
    mcp_pool = getattr(request.app.state, "mcp_pool", None)
    if not mcp_pool:
        return {"tools": [], "servers": []}

    try:
        tools_result = await mcp_pool.list_tools(
            server_name=server_name,
            tenant_id=tenant.tenant_id,
        )
        return tools_result
    except Exception as e:
        logger.error("Failed to list MCP tools", error=str(e))
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                code="MCP_TOOL_LIST_FAILED",
                message=f"Failed to list MCP tools: {str(e)}",
            ).model_dump(),
        )


@router.post(
    "/tools/call",
    response_model=dict,
    responses={
        200: {"description": "MCP 工具调用成功"},
        400: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
)
async def mcp_call_tool(
    request: Request,
    server_name: str,
    tool_name: str,
    arguments: dict,
    tenant: TenantContext = Depends(get_current_tenant),
):
    """调用已连接 MCP 服务器上的工具。

    将工具调用路由到对应的 MCP 服务器并返回结果。
    支持 MCP 服务器的错误传播。
    """
    mcp_pool = getattr(request.app.state, "mcp_pool", None)
    if not mcp_pool:
        raise HTTPException(
            status_code=503,
            detail=ErrorResponse(
                code="MCP_SERVICE_UNAVAILABLE",
                message="MCP pool not initialized",
            ).model_dump(),
        )

    try:
        result = await mcp_pool.call_tool(
            server_name=server_name,
            tool_name=tool_name,
            arguments=arguments,
            tenant_id=tenant.tenant_id,
        )

        if result.get("isError"):
            raise HTTPException(
                status_code=400,
                detail=ErrorResponse(
                    code="MCP_TOOL_ERROR",
                    message=result.get("content", "Tool execution error"),
                    details={"server": server_name, "tool": tool_name},
                ).model_dump(),
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "MCP tool call failed",
            error=str(e),
            server=server_name,
            tool=tool_name,
        )
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                code="MCP_TOOL_CALL_FAILED",
                message=f"Tool call failed: {str(e)}",
            ).model_dump(),
        )


@router.get(
    "/servers",
    response_model=list[dict],
    responses={200: {"description": "已连接 MCP 服务器列表"}},
)
async def list_mcp_servers(
    request: Request,
    tenant: TenantContext = Depends(get_current_tenant),
):
    """列出所有已连接的 MCP 服务器及其状态。"""
    mcp_pool = getattr(request.app.state, "mcp_pool", None)
    if not mcp_pool:
        return []

    servers = await mcp_pool.get_servers(tenant_id=tenant.tenant_id)
    return [
        {
            "name": s.name,
            "url": s.url,
            "status": s.status,
            "connected_at": s.connected_at.isoformat() if hasattr(s, 'connected_at') and s.connected_at else None,
            "tools_count": s.tools_count,
            "capabilities": s.capabilities,
        }
        for s in servers
    ]


@router.post(
    "/servers/connect",
    response_model=dict,
    status_code=201,
    responses={
        201: {"description": "MCP 服务器已连接"},
        400: {"model": ErrorResponse},
    },
)
async def connect_mcp_server(
    request: Request,
    name: str,
    url: str,
    transport: str = "stdio",
    api_key: Optional[str] = None,
    tenant: TenantContext = Depends(get_current_tenant),
):
    """连接到新的 MCP 服务器。

    通过 stdio 或 HTTP 传输协议与外部 MCP 服务器建立连接，
    并注册其可用工具。
    """
    mcp_pool = getattr(request.app.state, "mcp_pool", None)
    if not mcp_pool:
        raise HTTPException(
            status_code=503,
            detail=ErrorResponse(
                code="MCP_SERVICE_UNAVAILABLE",
                message="MCP pool not initialized",
            ).model_dump(),
        )

    try:
        result = await mcp_pool.connect_server(
            name=name,
            url=url,
            transport=transport,
            api_key=api_key,
            tenant_id=tenant.tenant_id,
        )
        return {
            "status": "connected",
            "name": name,
            "tools_count": result.get("tools_count", 0),
        }
    except Exception as e:
        logger.error("MCP server connection failed", error=str(e), name=name, url=url)
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                code="MCP_CONNECTION_FAILED",
                message=f"Failed to connect to MCP server: {str(e)}",
            ).model_dump(),
        )


@router.delete(
    "/servers/{server_name}",
    response_model=dict,
    responses={
        200: {"description": "MCP 服务器已断开"},
        404: {"model": ErrorResponse},
    },
)
async def disconnect_mcp_server(
    server_name: str,
    request: Request,
    tenant: TenantContext = Depends(get_current_tenant),
):
    """断开与 MCP 服务器的连接。"""
    mcp_pool = getattr(request.app.state, "mcp_pool", None)
    if not mcp_pool:
        raise HTTPException(
            status_code=503,
            detail=ErrorResponse(
                code="MCP_SERVICE_UNAVAILABLE",
                message="MCP pool not initialized",
            ).model_dump(),
        )

    try:
        await mcp_pool.disconnect_server(server_name, tenant_id=tenant.tenant_id)
        return {"status": "disconnected", "name": server_name}
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(
                code="MCP_SERVER_NOT_FOUND",
                message=f"MCP server '{server_name}' not found",
            ).model_dump(),
        )


@router.get(
    "/resources/list",
    response_model=dict,
    responses={200: {"description": "可用 MCP 资源列表"}},
)
async def mcp_list_resources(
    request: Request,
    server_name: Optional[str] = None,
    tenant: TenantContext = Depends(get_current_tenant),
):
    """列出 MCP 服务器提供的资源。"""
    mcp_pool = getattr(request.app.state, "mcp_pool", None)
    if not mcp_pool:
        return {"resources": []}

    try:
        return await mcp_pool.list_resources(
            server_name=server_name,
            tenant_id=tenant.tenant_id,
        )
    except Exception as e:
        logger.error("Failed to list MCP resources", error=str(e))
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                code="MCP_RESOURCE_LIST_FAILED",
                message=f"Failed to list resources: {str(e)}",
            ).model_dump(),
        )
