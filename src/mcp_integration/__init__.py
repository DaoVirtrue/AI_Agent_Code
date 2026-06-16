"""
MCP (Model Context Protocol) Integration module.

Provides:
- Full MCP Server with JSON-RPC 2.0 handling (stdio + SSE transports)
- MCP Client for connecting to external MCP servers
- Server registry for managing multiple MCP server connections
- Tool conversion between MCP and OpenAI formats
"""

__version__ = "1.0.0"

from mcp_integration.server.server import MCPServer
from mcp_integration.client.client import MCPClient
from mcp_integration.registry import MCPRegistry

__all__ = [
    "MCPServer",
    "MCPClient",
    "MCPRegistry",
]
