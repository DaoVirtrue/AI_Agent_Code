"""MCP Pool — 服务器连接与工具聚合的统一服务池。

给 ``src/api/routes/mcp_routes.py`` 提供统一的 MCP 服务接口：
列表 / 连接 / 断开 / 工具列表 / 工具调用 / 资源列表。

真实环境里连接由 ``MCPRegistry`` + ``MCPClient`` 负责（stdio/sse 握手）；
这里提供轻量内存实现，让内置/示例 MCP 服务器开箱即用，前端即可「选择」真实工具。
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

from src.core.tools import BaseTool, ToolStatus

logger = logging.getLogger(__name__)


class MCPPool:
    """In-memory MCP server pool (production: MCPRegistry over stdio/sse).

    Args:
        tools_by_name: dict of tool_name -> BaseTool, used to execute tool calls.
    """

    def __init__(self, tools_by_name: Optional[dict[str, BaseTool]] = None):
        self._tools_by_name = tools_by_name or {}
        self._servers: dict[str, dict] = {}          # name -> server info
        self._server_tools: dict[str, list[dict]] = {}  # name -> tool defs
        self._connected_at: dict[str, float] = {}

    # ------------------------------------------------------------------
    # Server registration
    # ------------------------------------------------------------------

    def register_server(
        self,
        name: str,
        url: str = "",
        transport: str = "stdio",
        description: str = "",
        tools: Optional[list[str]] = None,
        status: str = "connected",
    ) -> None:
        """注册一个 MCP 服务器及其暴露的工具名列表。"""
        tools = tools or []
        self._servers[name] = {
            "name": name,
            "url": url,
            "transport": transport,
            "description": description,
            "status": status,
            "capabilities": {"tools": True, "resources": True, "prompts": True},
            "tools_count": len(tools),
        }
        self._server_tools[name] = [self._tool_def(t) for t in tools]
        self._connected_at[name] = time.time()
        logger.info("Registered MCP server '%s' (%d tools)", name, len(tools))

    def _tool_def(self, name: str) -> dict:
        """Build an MCP tool definition from a registered BaseTool."""
        tool = self._tools_by_name.get(name)
        if tool is None:
            return {
                "name": name,
                "description": "",
                "inputSchema": {"type": "object", "properties": {}, "required": []},
            }
        d = tool.definition
        return {
            "name": d.name,
            "description": d.description,
            "inputSchema": {
                "type": "object",
                "properties": d.parameters.get("properties", {}),
                "required": d.parameters.get("required", []),
            },
        }

    # ------------------------------------------------------------------
    # mcp_routes interface
    # ------------------------------------------------------------------

    async def get_servers(self, tenant_id: str = "default") -> list[dict]:
        """返回所有已注册服务器的状态。"""
        result = []
        for name, info in self._servers.items():
            result.append({
                "name": name,
                "url": info["url"],
                "transport": info["transport"],
                "status": info["status"],
                "description": info.get("description", ""),
                "tools_count": info["tools_count"],
                "capabilities": info["capabilities"],
                "tools": self._server_tools.get(name, []),
                "connected_at": self._connected_at.get(name),
            })
        return result

    async def list_tools(
        self,
        server_name: Optional[str] = None,
        tenant_id: str = "default",
    ) -> dict:
        """聚合列出所有（或指定）服务器的工具。"""
        tools: list[dict] = []
        servers = [s["name"] for s in self._servers.values()]
        for srv, defs in self._server_tools.items():
            if server_name and srv != server_name:
                continue
            for td in defs:
                tools.append({**td, "server_name": srv})
        return {"tools": tools, "servers": servers}

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict,
        tenant_id: str = "default",
    ) -> dict:
        """执行一个工具调用（路由到已注册的 BaseTool）。"""
        tool = self._tools_by_name.get(tool_name)
        if tool is None:
            return {
                "content": [{"type": "text", "text": f"未知工具: {tool_name}"}],
                "isError": True,
            }
        try:
            result: ToolResult = await tool.execute(**arguments)
            text = json.dumps(result.data, ensure_ascii=False, default=str) if result.data is not None else ""
            return {
                "content": [{"type": "text", "text": text}],
                "isError": result.status not in (ToolStatus.SUCCESS,),
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("MCP tool '%s' failed: %s", tool_name, exc)
            return {"content": [{"type": "text", "text": str(exc)}], "isError": True}

    async def connect_server(
        self,
        name: str,
        url: str,
        transport: str = "stdio",
        api_key: Optional[str] = None,
        tenant_id: str = "default",
    ) -> dict:
        """连接一个新的 MCP 服务器（演示：注册即连接）。"""
        if name in self._servers:
            self._servers[name]["status"] = "connected"
            self._connected_at[name] = time.time()
        else:
            self.register_server(name=name, url=url, transport=transport, description="", tools=[], status="connected")
        return {"tools_count": self._servers[name]["tools_count"]}

    async def disconnect_server(self, server_name: str, tenant_id: str = "default") -> dict:
        """断开一个服务器。"""
        if server_name not in self._servers:
            raise KeyError(server_name)
        self._servers[server_name]["status"] = "disconnected"
        return {"status": "disconnected", "name": server_name}

    async def list_resources(
        self,
        server_name: Optional[str] = None,
        tenant_id: str = "default",
    ) -> dict:
        return {"resources": []}

    def __repr__(self) -> str:
        return f"MCPPool(servers={len(self._servers)})"
