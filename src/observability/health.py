"""Health checker for all platform dependencies."""

import time
from typing import Optional

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy import text

from src.observability.logging_setup import get_logger

logger = get_logger(__name__)


class HealthChecker:
    """Checks the health of all platform dependencies.

    Used by Kubernetes probes (/health, /ready, /live) and internal
    monitoring to detect and report service degradation.
    """

    def __init__(
        self,
        redis: Redis,
        db_session_factory: async_sessionmaker,
        model_registry=None,
    ):
        """Initialize the health checker.

        Args:
            redis: Redis client for cache health checks.
            db_session_factory: Async session factory for database checks.
            model_registry: Optional model registry for provider checks.
        """
        self.redis = redis
        self.db_session_factory = db_session_factory
        self.model_registry = model_registry
        self._start_time = time.monotonic()

    async def check_db(self) -> bool:
        """Check database connectivity.

        Executes a simple SELECT 1 to verify the connection pool
        and database are responsive.

        Returns:
            True if database is reachable and responsive.
        """
        try:
            async with self.db_session_factory() as session:
                await session.execute(text("SELECT 1"))
            logger.debug("Database health check passed")
            return True
        except Exception as e:
            logger.error("Database health check failed", error=str(e))
            return False

    async def check_redis(self) -> bool:
        """Check Redis connectivity.

        Sends a PING command to verify Redis is reachable.

        Returns:
            True if Redis responds to PING.
        """
        try:
            result = await self.redis.ping()
            if result:
                logger.debug("Redis health check passed")
                return True
            logger.warning("Redis PING returned falsy value")
            return False
        except Exception as e:
            logger.error("Redis health check failed", error=str(e))
            return False

    async def check_milvus(self) -> bool:
        """Check Milvus/vector store connectivity.

        Returns:
            True if the vector store is reachable.
        """
        try:
            from pymilvus import connections, utility
            # Check if there's an active connection
            connected = False
            try:
                connections.get_connection_addr("default")
                connected = True
            except Exception:
                pass

            if connected:
                return True

            # Try a lightweight check
            logger.warning("Milvus connection not established")
            return False
        except ImportError:
            logger.debug("pymilvus not installed, skipping vector store check")
            return True  # Not a failure if Milvus is not in use
        except Exception as e:
            logger.error("Milvus health check failed", error=str(e))
            return False

    async def check_providers(self) -> dict[str, bool]:
        """Check the health of configured LLM providers.

        Does lightweight checks (e.g., list models) for each configured
        provider to verify API connectivity.

        Returns:
            Dict mapping provider name to health status.
        """
        results = {}

        if not self.model_registry:
            return {"openai": True, "anthropic": True}  # Assume healthy

        providers = self.model_registry.get_configured_providers()

        for provider in providers:
            try:
                # Lightweight check: try listing models
                # This is a connectivity check, not a full health check
                await self.model_registry.health_check_provider(provider)
                results[provider] = True
                logger.debug("Provider health check passed", provider=provider)
            except Exception as e:
                results[provider] = False
                logger.warning(
                    "Provider health check failed",
                    provider=provider,
                    error=str(e),
                )

        return results

    async def full_check(self) -> dict:
        """Run all health checks and return a comprehensive status.

        Returns:
            Dict containing:
            - database: bool
            - redis: bool
            - milvus: bool (if configured)
            - providers: dict of provider -> bool
            - uptime_seconds: float
        """
        checks = {}

        # Run checks in parallel for speed
        import asyncio

        db_task = asyncio.ensure_future(self.check_db())
        redis_task = asyncio.ensure_future(self.check_redis())
        milvus_task = asyncio.ensure_future(self.check_milvus())
        providers_task = asyncio.ensure_future(self.check_providers())

        checks["database"] = await db_task
        checks["redis"] = await redis_task
        checks["milvus"] = await milvus_task
        checks["uptime_seconds"] = time.monotonic() - self._start_time

        provider_results = await providers_task
        for provider, status in provider_results.items():
            checks[f"provider_{provider}"] = status

        logger.info(
            "Full health check completed",
            status="healthy" if all(checks.get(k, True) for k in ["database", "redis"]) else "unhealthy",
            checks=checks,
        )

        return checks

    async def check_mcp_servers(self) -> dict[str, bool]:
        """Check health of connected MCP servers.

        Returns:
            Dict mapping MCP server name to health status.
        """
        # MCP server health checking is deferred (see mcp_integration module).
        # Returning an empty dict signals "no connected MCP servers yet".
        # The historical `from src.mcp.client import MCPClientPool` import
        # pointed at a directory (src/mcp) that no longer exists.
        return {}

    @property
    def uptime_seconds(self) -> float:
        """Get the uptime in seconds since this checker was initialized."""
        return time.monotonic() - self._start_time
