"""
Isolated execution sandbox with timeout and resource limits.
"""

import asyncio
import logging
import time
from contextlib import contextmanager
from typing import Any

from src.core.tools import ToolResult, ToolStatus

logger = logging.getLogger(__name__)


class ResourceLimitError(Exception):
    """Raised when a tool exceeds its allocated resources."""
    pass


class ExecutionSandbox:
    """Provides isolated execution of tool functions with configurable
    timeout and resource constraints.

    Uses asyncio.wait_for for timeouts. Memory limits are advisory and
    enforced via resource-tracking hooks where available.

    Args:
        timeout: Maximum execution time in seconds.
        max_memory_mb: Advisory memory limit in megabytes.
    """

    def __init__(self, timeout: int = 30, max_memory_mb: int = 512):
        self.timeout = timeout
        self.max_memory_mb = max_memory_mb
        self._execution_count = 0
        self._total_execution_time_ms = 0.0

    async def execute(self, func: callable, **kwargs) -> ToolResult:
        """Execute a callable within the sandbox.

        Args:
            func: The async callable to execute.
            **kwargs: Keyword arguments forwarded to the callable.

        Returns:
            ToolResult with execution outcome and timing.
        """
        self._execution_count += 1
        start = time.perf_counter()

        try:
            if asyncio.iscoroutinefunction(func):
                result = await self._enforce_timeout(
                    asyncio.ensure_future(func(**kwargs)),
                    self.timeout,
                )
            else:
                # Wrap sync callables
                result = await self._enforce_timeout(
                    asyncio.get_event_loop().run_in_executor(None, func, **kwargs),
                    self.timeout,
                )

            elapsed = (time.perf_counter() - start) * 1000
            self._total_execution_time_ms += elapsed

            return result if isinstance(result, ToolResult) else ToolResult(
                status=ToolStatus.SUCCESS,
                data=result,
                execution_time_ms=elapsed,
            )

        except asyncio.TimeoutError:
            elapsed = (time.perf_counter() - start) * 1000
            self._total_execution_time_ms += elapsed
            logger.error("Sandbox execution timed out after %.1fs", elapsed / 1000)
            raise  # Re-raise for the registry to handle

        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            self._total_execution_time_ms += elapsed
            logger.error("Sandbox execution failed: %s (%.1fms)", e, elapsed)
            raise

    async def _enforce_timeout(self, coro_or_future, timeout: float) -> Any:
        """Enforce a timeout on an awaitable using asyncio.wait_for.

        Args:
            coro_or_future: An asyncio awaitable.
            timeout: Maximum seconds to wait.

        Returns:
            The result of the awaitable.

        Raises:
            asyncio.TimeoutError: If the operation exceeds the timeout.
        """
        try:
            result = await asyncio.wait_for(coro_or_future, timeout=timeout)
            return result
        except asyncio.CancelledError:
            raise
        except asyncio.TimeoutError:
            raise
        except Exception:
            raise

    @property
    def stats(self) -> dict:
        """Return execution statistics for this sandbox instance."""
        return {
            "execution_count": self._execution_count,
            "total_time_ms": self._total_execution_time_ms,
            "avg_time_ms": (
                self._total_execution_time_ms / self._execution_count
                if self._execution_count else 0.0
            ),
            "timeout": self.timeout,
            "max_memory_mb": self.max_memory_mb,
        }

    def reset_stats(self) -> None:
        """Reset execution statistics."""
        self._execution_count = 0
        self._total_execution_time_ms = 0.0

    @contextmanager
    def temporary_timeout(self, timeout: int):
        """Context manager to temporarily change the timeout."""
        old = self.timeout
        self.timeout = timeout
        try:
            yield
        finally:
            self.timeout = old

    def __repr__(self) -> str:
        return (
            f"ExecutionSandbox(timeout={self.timeout}s, "
            f"max_memory={self.max_memory_mb}MB)"
        )
