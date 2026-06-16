"""
Tool discovery for MCP clients.

Handles capability negotiation, tool schema discovery, and
periodic refresh of tool definitions from connected servers.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class DiscoveredTool:
    """Information about a discovered tool."""
    name: str
    description: str
    input_schema: dict
    server_name: str
    server_version: str = "unknown"
    discovered_at: float = field(default_factory=time.time)
    category: str = "general"


class ToolDiscovery:
    """Discovers and catalogs tools across multiple MCP servers.

    Maintains an up-to-date catalog of all tools from all connected
    servers, with periodic refresh and indexing for search.

    Args:
        refresh_interval: Seconds between automatic refresh cycles (default 300).
        max_tools: Maximum total tools to track across all servers.
    """

    def __init__(self, refresh_interval: float = 300.0, max_tools: int = 500):
        self.refresh_interval = refresh_interval
        self.max_tools = max_tools

        self._tools: dict[str, DiscoveredTool] = {}
        self._by_server: dict[str, list[str]] = {}
        self._by_category: dict[str, list[str]] = {}
        self._last_refresh = 0.0
        self._refresh_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    async def discover_from_client(self, client) -> int:
        """Discover tools from a single MCP client.

        Args:
            client: An MCPClient instance (must be connected).

        Returns:
            Number of new tools discovered.
        """
        if not hasattr(client, "_connected") or not client._connected:
            logger.warning("Cannot discover from disconnected client: %s", client.server_name)
            return 0

        try:
            tools = await client.discover_tools()
        except Exception as e:
            logger.error("Discovery failed for '%s': %s", client.server_name, e)
            return 0

        new_count = 0
        for tool in tools:
            tool_key = f"{client.server_name}:{tool['name']}"
            if tool_key not in self._tools:
                self._tools[tool_key] = DiscoveredTool(
                    name=tool["name"],
                    description=tool.get("description", ""),
                    input_schema=tool.get("inputSchema", {}),
                    server_name=client.server_name,
                    server_version=client._capabilities.get("serverInfo", {}).get("version", "unknown"),
                )
                self._by_server.setdefault(client.server_name, []).append(tool_key)
                category = self._categorize_tool(tool)
                self._by_category.setdefault(category, []).append(tool_key)
                new_count += 1

        logger.info(
            "Discovered %d new tools from '%s' (total: %d)",
            new_count, client.server_name, len(self._tools),
        )
        return new_count

    async def discover_from_clients(self, clients: list) -> dict[str, int]:
        """Discover tools from multiple MCP clients.

        Args:
            clients: List of MCPClient instances.

        Returns:
            Dict mapping server_name -> new tools count.
        """
        results = {}
        tasks = []

        for client in clients:
            tasks.append((client.server_name, self.discover_from_client(client)))

        gathered = await asyncio.gather(
            *[t[1] for t in tasks],
            return_exceptions=True,
        )

        for (server_name, _), result in zip(tasks, gathered):
            if isinstance(result, Exception):
                logger.error("Discovery failed for '%s': %s", server_name, result)
                results[server_name] = 0
            else:
                results[server_name] = result

        self._last_refresh = time.time()
        return results

    # ------------------------------------------------------------------
    # Auto-refresh
    # ------------------------------------------------------------------

    async def start_auto_refresh(self, clients: list) -> None:
        """Start periodic auto-refresh of tool discovery.

        Args:
            clients: List of MCPClient instances to refresh.
        """
        async def _refresh_loop():
            while True:
                await asyncio.sleep(self.refresh_interval)
                try:
                    await self.discover_from_clients(clients)
                except Exception as e:
                    logger.exception("Auto-refresh failed: %s", e)

        self._refresh_task = asyncio.create_task(_refresh_loop())
        logger.info("Auto-refresh started (interval=%.1fs)", self.refresh_interval)

    async def stop_auto_refresh(self) -> None:
        """Stop the auto-refresh task."""
        if self._refresh_task:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
            self._refresh_task = None

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_tool(self, server_name: str, tool_name: str) -> DiscoveredTool | None:
        """Get a specific discovered tool.

        Args:
            server_name: The server that hosts the tool.
            tool_name: The tool name.

        Returns:
            DiscoveredTool or None.
        """
        tool_key = f"{server_name}:{tool_name}"
        return self._tools.get(tool_key)

    def list_by_server(self, server_name: str) -> list[dict]:
        """List all tools from a specific server.

        Args:
            server_name: The server name.

        Returns:
            List of tool info dicts.
        """
        tool_keys = self._by_server.get(server_name, [])
        return [self._tool_to_dict(self._tools[k]) for k in tool_keys if k in self._tools]

    def list_by_category(self, category: str) -> list[dict]:
        """List all tools in a category.

        Args:
            category: The category name.

        Returns:
            List of tool info dicts.
        """
        tool_keys = self._by_category.get(category, [])
        return [self._tool_to_dict(self._tools[k]) for k in tool_keys if k in self._tools]

    def list_all(self) -> list[dict]:
        """List all discovered tools.

        Returns:
            List of tool info dicts for all tools.
        """
        return [self._tool_to_dict(t) for t in self._tools.values()]

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """Search discovered tools by name and description.

        Args:
            query: Search query string.
            top_k: Maximum results.

        Returns:
            List of matching tool info dicts.
        """
        query_lower = query.lower()
        scored = []

        for tool in self._tools.values():
            score = 0
            if query_lower in tool.name.lower():
                score += 10
            if query_lower in tool.description.lower():
                score += 5
            if query_lower in tool.category.lower():
                score += 3

            # Name prefix match bonus
            if tool.name.lower().startswith(query_lower):
                score += 8

            if score > 0:
                scored.append((score, tool))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [self._tool_to_dict(t) for _, t in scored[:top_k]]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _categorize_tool(tool: dict) -> str:
        """Categorize a tool based on its name and description."""
        name_lower = tool.get("name", "").lower()
        desc_lower = tool.get("description", "").lower()
        combined = f"{name_lower} {desc_lower}"

        if any(kw in combined for kw in ("search", "find", "lookup")):
            return "search"
        if any(kw in combined for kw in ("file", "read", "write", "directory")):
            return "filesystem"
        if any(kw in combined for kw in ("database", "sql", "query", "data")):
            return "database"
        if any(kw in combined for kw in ("code", "execute", "run", "python", "js")):
            return "code"
        if any(kw in combined for kw in ("web", "http", "fetch", "url", "browser")):
            return "web"
        if any(kw in combined for kw in ("math", "calculate", "compute", "eval")):
            return "math"

        return "general"

    @staticmethod
    def _tool_to_dict(tool: DiscoveredTool) -> dict:
        """Convert a DiscoveredTool to a serializable dict."""
        return {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.input_schema,
            "server_name": tool.server_name,
            "server_version": tool.server_version,
            "category": tool.category,
            "discovered_at": tool.discovered_at,
        }

    @property
    def tool_count(self) -> int:
        """Total number of discovered tools."""
        return len(self._tools)

    @property
    def server_count(self) -> int:
        """Number of servers with discovered tools."""
        return len(self._by_server)

    def __repr__(self) -> str:
        return f"ToolDiscovery(tools={len(self._tools)}, servers={len(self._by_server)})"
