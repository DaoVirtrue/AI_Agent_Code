"""
Session manager with connection pooling for MCP clients.

Manages lifecycle of multiple MCP server connections, providing
connection pooling, health checks, and request load balancing.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SessionInfo:
    """Information about an active MCP client session."""
    server_name: str
    transport: str
    config: dict
    client: Any = None  # MCPClient instance
    connected_at: float = 0.0
    last_activity: float = 0.0
    request_count: int = 0
    error_count: int = 0
    status: str = "disconnected"


class SessionManager:
    """Manages MCP client sessions with connection pooling.

    Features:
    - Lazy connection establishment
    - Connection pooling with max connections
    - Automatic reconnection on failure
    - Health checks
    - Load balancing across sessions

    Args:
        max_connections: Maximum concurrent connections.
        idle_timeout: Seconds before idle connections are closed.
        max_retries: Maximum reconnection attempts.
    """

    def __init__(
        self,
        max_connections: int = 10,
        idle_timeout: float = 300.0,
        max_retries: int = 3,
    ):
        self.max_connections = max_connections
        self.idle_timeout = idle_timeout
        self.max_retries = max_retries

        self._sessions: dict[str, SessionInfo] = {}
        self._active_count = 0
        self._lock = asyncio.Lock()
        self._cleanup_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def register_server(self, server_name: str, transport: str, config: dict) -> None:
        """Register a server configuration for future connection.

        Args:
            server_name: Unique server identifier.
            transport: Transport type ("stdio" or "sse").
            config: Transport-specific configuration.
        """
        if server_name in self._sessions:
            logger.warning("Server '%s' already registered, updating config.", server_name)

        self._sessions[server_name] = SessionInfo(
            server_name=server_name,
            transport=transport,
            config=config,
            status="disconnected",
        )
        logger.info("Registered MCP server config: %s (%s)", server_name, transport)

    def unregister_server(self, server_name: str) -> None:
        """Remove a server registration."""
        self._sessions.pop(server_name, None)

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    async def connect(self, server_name: str) -> Any:
        """Get or create a connected session for a server.

        Args:
            server_name: The server to connect to.

        Returns:
            Connected MCPClient instance.

        Raises:
            ValueError: If server not registered.
            RuntimeError: If connection fails after max_retries.
        """
        if server_name not in self._sessions:
            raise ValueError(f"Server '{server_name}' is not registered.")

        session = self._sessions[server_name]

        async with self._lock:
            if session.client and session.status == "connected":
                # Already connected - verify health
                session.last_activity = time.time()
                return session.client

            # Enforce connection limit
            if self._active_count >= self.max_connections:
                await self._evict_least_recent()

            # Create and connect
            from src.mcp.client.client import MCPClient

            client = MCPClient(
                server_name=server_name,
                transport=session.transport,
                **session.config,
            )

            for attempt in range(self.max_retries + 1):
                try:
                    await client.connect()
                    session.client = client
                    session.connected_at = time.time()
                    session.last_activity = time.time()
                    session.status = "connected"
                    self._active_count += 1
                    return client
                except Exception as e:
                    logger.warning(
                        "Connection attempt %d/%d failed for '%s': %s",
                        attempt + 1, self.max_retries + 1, server_name, e,
                    )
                    if attempt < self.max_retries:
                        await asyncio.sleep(min(2 ** attempt, 10))
                    else:
                        session.status = "error"
                        raise RuntimeError(
                            f"Failed to connect to '{server_name}' after "
                            f"{self.max_retries + 1} attempts."
                        )

    async def disconnect(self, server_name: str) -> None:
        """Disconnect and release a session.

        Args:
            server_name: The server to disconnect.
        """
        async with self._lock:
            session = self._sessions.get(server_name)
            if not session:
                return

            if session.client:
                try:
                    await session.client.close()
                except Exception as e:
                    logger.warning("Error closing client '%s': %s", server_name, e)

            session.client = None
            session.status = "disconnected"
            session.connected_at = 0.0
            self._active_count = max(0, self._active_count - 1)
            logger.info("Disconnected from '%s'", server_name)

    async def disconnect_all(self) -> None:
        """Disconnect all active sessions."""
        tasks = []
        for server_name in list(self._sessions.keys()):
            tasks.append(self.disconnect(server_name))
        await asyncio.gather(*tasks, return_exceptions=True)

    # ------------------------------------------------------------------
    # Health checks
    # ------------------------------------------------------------------

    async def health_check(self, server_name: str) -> bool:
        """Check if a server connection is healthy.

        Args:
            server_name: The server to check.

        Returns:
            True if the server is connected and responsive.
        """
        session = self._sessions.get(server_name)
        if not session or not session.client:
            return False

        if not session.client._connected:
            session.status = "disconnected"
            return False

        try:
            # Ping the server
            result = await asyncio.wait_for(
                session.client._send_request("ping", {}),
                timeout=5.0,
            )
            return result is not None
        except Exception:
            session.status = "unhealthy"
            return False

    async def health_check_all(self) -> dict[str, bool]:
        """Check health of all registered servers.

        Returns:
            Dict mapping server_name -> is_healthy.
        """
        tasks = {
            name: self.health_check(name)
            for name in self._sessions
        }

        results = {}
        for name, coro in tasks.items():
            try:
                results[name] = await coro
            except Exception:
                results[name] = False

        return results

    # ------------------------------------------------------------------
    # Connection pooling
    # ------------------------------------------------------------------

    async def _evict_least_recent(self) -> None:
        """Evict the least recently active idle connection."""
        idle_sessions = [
            (s.last_activity, name, s)
            for name, s in self._sessions.items()
            if s.status == "connected"
        ]

        if not idle_sessions:
            logger.warning("No idle sessions to evict; max_connections=%d", self.max_connections)
            return

        idle_sessions.sort(key=lambda x: x[0])
        _, server_name, _ = idle_sessions[0]

        logger.info("Evicting least recently used session: %s", server_name)
        await self.disconnect(server_name)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    async def start_cleanup(self) -> None:
        """Start periodic cleanup of idle connections."""
        async def _cleanup_loop():
            while True:
                await asyncio.sleep(60)  # Check every minute
                try:
                    await self._cleanup_idle()
                except Exception as e:
                    logger.exception("Cleanup error: %s", e)

        self._cleanup_task = asyncio.create_task(_cleanup_loop())

    async def stop_cleanup(self) -> None:
        """Stop the cleanup task."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None

    async def _cleanup_idle(self) -> None:
        """Close sessions that have been idle too long."""
        now = time.time()
        to_close = []

        for name, session in self._sessions.items():
            if session.status == "connected":
                idle_time = now - session.last_activity
                if idle_time > self.idle_timeout:
                    to_close.append(name)

        for name in to_close:
            logger.info("Closing idle session: %s (idle for %.1fs)", name, now - self._sessions[name].last_activity)
            await self.disconnect(name)

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    @property
    def stats(self) -> dict:
        """Return session manager statistics."""
        sessions = {}
        for name, session in self._sessions.items():
            sessions[name] = {
                "status": session.status,
                "transport": session.transport,
                "requests": session.request_count,
                "errors": session.error_count,
                "uptime": time.time() - session.connected_at if session.connected_at else 0,
            }

        return {
            "total_sessions": len(self._sessions),
            "active_sessions": self._active_count,
            "max_connections": self.max_connections,
            "sessions": sessions,
        }

    def get_active(self) -> list[str]:
        """Get list of currently active server connections."""
        return [
            name for name, s in self._sessions.items()
            if s.status == "connected"
        ]

    def __repr__(self) -> str:
        return (
            f"SessionManager(sessions={len(self._sessions)}, "
            f"active={self._active_count}/{self.max_connections})"
        )
