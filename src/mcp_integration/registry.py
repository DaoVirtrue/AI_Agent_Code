"""
MCP Registry for managing multiple external MCP server connections.

Maintains a catalog of configured MCP servers, handles connection
lifecycle, and provides aggregated tool access across all servers.
"""

import asyncio
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class MCPRegistry:
    """Registry of external MCP server connections.

    Manages multiple MCP server configurations, handles connection
    establishment, aggregates tools across all servers, and performs
    health monitoring.

    Args:
        health_check_interval: Seconds between health checks (default 60).
        auto_reconnect: If True, attempt to reconnect unhealthy servers.
    """

    def __init__(
        self,
        health_check_interval: float = 60.0,
        auto_reconnect: bool = True,
    ):
        self.health_check_interval = health_check_interval
        self.auto_reconnect = auto_reconnect

        self._servers: dict[str, dict] = {}
        self._clients: dict[str, Any] = {}  # server_id -> MCPClient
        self._health: dict[str, bool] = {}
        self._health_task: asyncio.Task | None = None
        self._running = False

    # ------------------------------------------------------------------
    # Server registration
    # ------------------------------------------------------------------

    def register(self, server_id: str, config: dict) -> None:
        """Register an external MCP server configuration.

        Config format:
        {
            "transport": "stdio" | "sse",
            "command": "...",   # for stdio
            "args": [...],      # for stdio
            "base_url": "...",  # for sse
            "api_key": "...",   # optional
            "description": "...",
            "timeout": 30,
        }

        Args:
            server_id: Unique identifier for this server.
            config: Server configuration dict.
        """
        if server_id in self._servers:
            logger.warning("Server '%s' already registered, updating.", server_id)

        # Ensure required fields
        if "transport" not in config:
            raise ValueError(f"Server '{server_id}' config must specify 'transport'.")

        transport = config["transport"]
        if transport == "stdio" and "command" not in config:
            raise ValueError(f"stdio transport requires 'command' in config for '{server_id}'.")
        if transport == "sse" and "base_url" not in config:
            raise ValueError(f"sse transport requires 'base_url' in config for '{server_id}'.")

        self._servers[server_id] = config
        logger.info("Registered MCP server: %s (transport=%s)", server_id, transport)

    def unregister(self, server_id: str) -> None:
        """Remove a server from the registry.

        Disconnects if currently connected.

        Args:
            server_id: The server ID to remove.
        """
        if server_id in self._clients:
            try:
                asyncio.create_task(self._disconnect_server(server_id))
            except Exception:
                pass

        self._servers.pop(server_id, None)
        self._clients.pop(server_id, None)
        self._health.pop(server_id, None)

    async def _disconnect_server(self, server_id: str) -> None:
        """Disconnect a server client."""
        client = self._clients.pop(server_id, None)
        if client:
            try:
                await client.close()
            except Exception as e:
                logger.warning("Error disconnecting '%s': %s", server_id, e)

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    async def connect_all(self) -> dict[str, bool]:
        """Connect to all registered servers.

        Returns:
            Dict mapping server_id -> connection success.
        """
        results = {}

        async def connect_one(server_id: str, config: dict):
            try:
                from src.mcp_integration.client.client import MCPClient

                client = MCPClient(
                    server_name=server_id,
                    transport=config["transport"],
                    **{k: v for k, v in config.items()
                       if k not in ("transport", "description", "timeout")},
                )
                await client.connect()
                self._clients[server_id] = client
                return server_id, True
            except Exception as e:
                logger.error("Failed to connect '%s': %s", server_id, e)
                return server_id, False

        tasks = [
            connect_one(sid, cfg)
            for sid, cfg in self._servers.items()
        ]
        gathered = await asyncio.gather(*tasks, return_exceptions=True)

        for result in gathered:
            if isinstance(result, Exception):
                logger.error("Connection task failed: %s", result)
            elif isinstance(result, tuple):
                sid, ok = result
                results[sid] = ok
                self._health[sid] = ok

        logger.info(
            "Connected to %d/%d MCP servers",
            sum(1 for v in results.values() if v),
            len(self._servers),
        )
        return results

    async def disconnect_all(self) -> None:
        """Disconnect from all servers."""
        tasks = [
            self._disconnect_server(sid)
            for sid in list(self._clients.keys())
        ]
        await asyncio.gather(*tasks, return_exceptions=True)
        self._health.clear()

    # ------------------------------------------------------------------
    # Tool access
    # ------------------------------------------------------------------

    async def get_all_tools(self) -> dict[str, list[dict]]:
        """Get tools from all connected servers.

        Returns:
            Dict mapping server_id -> list of tool dicts.
        """
        all_tools: dict[str, list[dict]] = {}

        for server_id, client in self._clients.items():
            try:
                tools = await client.discover_tools()
                all_tools[server_id] = tools
            except Exception as e:
                logger.warning("Failed to get tools from '%s': %s", server_id, e)
                all_tools[server_id] = []

        return all_tools

    async def get_openai_tools(self) -> list[dict]:
        """Get all tools from all servers in OpenAI function format.

        Each tool is prefixed with its server ID to avoid name collisions.

        Returns:
            List of OpenAI compatible tool dicts.
        """
        tools = []
        for server_id, client in self._clients.items():
            try:
                prefix = f"{server_id}__"
                server_tools = client.to_openai_tools(prefix=prefix)
                tools.extend(server_tools)
            except Exception as e:
                logger.warning("Failed to convert tools from '%s': %s", server_id, e)

        return tools

    async def call_tool(self, server_id: str, tool_name: str, arguments: dict) -> dict | None:
        """Call a tool on a specific server.

        Args:
            server_id: The server to call.
            tool_name: The tool name.
            arguments: Tool arguments.

        Returns:
            Tool result dict, or None on failure.
        """
        client = self._clients.get(server_id)
        if not client:
            logger.error("Server not connected: %s", server_id)
            return None

        try:
            return await client.call_tool(tool_name, arguments)
        except Exception as e:
            logger.error("Tool call failed on '%s': %s", server_id, e)
            return None

    # ------------------------------------------------------------------
    # Health monitoring
    # ------------------------------------------------------------------

    async def health_check_all(self) -> dict[str, bool]:
        """Check health of all registered servers.

        Returns:
            Dict mapping server_id -> is_healthy.
        """
        results = {}

        for server_id in list(self._servers.keys()):
            client = self._clients.get(server_id)

            if not client or not client._connected:
                results[server_id] = False
                # Auto-reconnect if configured
                if self.auto_reconnect and server_id in self._servers:
                    try:
                        await self.connect_all()
                    except Exception:
                        pass
                continue

            try:
                result = await asyncio.wait_for(
                    client._send_request("ping", {}),
                    timeout=5.0,
                )
                results[server_id] = result is not None
            except Exception:
                results[server_id] = False
                if self.auto_reconnect:
                    logger.warning("Server '%s' unhealthy, attempting reconnect.", server_id)
                    await self._disconnect_server(server_id)
                    if server_id in self._servers:
                        try:
                            new_client = self._create_client(server_id, self._servers[server_id])
                            await new_client.connect()
                            self._clients[server_id] = new_client
                            results[server_id] = True
                            logger.info("Reconnected to '%s'", server_id)
                        except Exception as e:
                            logger.error("Reconnect failed for '%s': %s", server_id, e)

        self._health = results
        return results

    async def start_health_monitor(self) -> None:
        """Start periodic health monitoring."""
        if self._running:
            return

        self._running = True

        async def _monitor_loop():
            while self._running:
                try:
                    await self.health_check_all()
                except Exception as e:
                    logger.exception("Health check error: %s", e)
                await asyncio.sleep(self.health_check_interval)

        self._health_task = asyncio.create_task(_monitor_loop())
        logger.info("Health monitor started (interval=%.1fs)", self.health_check_interval)

    async def stop_health_monitor(self) -> None:
        """Stop health monitoring."""
        self._running = False
        if self._health_task:
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass
            self._health_task = None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _create_client(self, server_id: str, config: dict) -> Any:
        """Create an MCP client from config."""
        from src.mcp_integration.client.client import MCPClient

        client_config = {
            k: v for k, v in config.items()
            if k not in ("transport", "description", "timeout")
        }

        client_config["server_name"] = server_id
        return MCPClient(
            server_name=server_id,
            transport=config["transport"],
            **{k: v for k, v in config.items()
               if k not in ("transport", "description", "timeout")},
        )

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    @property
    def stats(self) -> dict:
        """Return registry statistics."""
        return {
            "total_servers": len(self._servers),
            "connected_servers": sum(1 for c in self._clients.values() if c._connected),
            "health": dict(self._health),
            "servers": list(self._servers.keys()),
            "auto_reconnect": self.auto_reconnect,
        }

    def __len__(self) -> int:
        return len(self._servers)

    def __contains__(self, server_id: str) -> bool:
        return server_id in self._servers

    def __repr__(self) -> str:
        connected = sum(1 for c in self._clients.values() if c._connected)
        return (
            f"MCPRegistry(servers={len(self._servers)}, "
            f"connected={connected}/{len(self._servers)})"
        )
