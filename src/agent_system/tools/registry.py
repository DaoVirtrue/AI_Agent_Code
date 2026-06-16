"""
Tool registry with dependency management, retry logic, timeout enforcement,
and semantic search capabilities.
"""

import asyncio
import logging
import time
from collections import defaultdict
from typing import Any

from agent_system.tools.base import BaseTool, ToolDefinition, ToolResult, ToolStatus
from agent_system.tools.sandbox import ExecutionSandbox

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Central registry for managing and executing tools.

    Handles:
    - Tool registration with dependency/conflict validation
    - Execution with automatic retries and timeouts via ExecutionSandbox
    - Semantic search over tool definitions
    - Conversion to OpenAI-compatible function call format
    """

    def __init__(self, default_sandbox: ExecutionSandbox | None = None):
        self._tools: dict[str, BaseTool] = {}
        self._categories: dict[str, list[str]] = defaultdict(list)
        self._dependency_graph: dict[str, set] = {}
        self._usage_stats: dict[str, dict] = defaultdict(lambda: {"calls": 0, "errors": 0, "total_ms": 0.0})
        self._sandbox = default_sandbox or ExecutionSandbox()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, tool: BaseTool) -> None:
        """Register a tool, validating dependencies and conflicts.

        Args:
            tool: The BaseTool instance to register.

        Raises:
            ValueError: If the tool's name is already registered, or if a
                        dependency is missing, or if a conflict exists.
        """
        definition = tool.definition
        name = definition.name

        if name in self._tools:
            raise ValueError(f"Tool '{name}' is already registered.")

        # Validate dependencies are registered
        for dep in definition.dependencies:
            if dep not in self._tools:
                raise ValueError(
                    f"Tool '{name}' declares dependency on '{dep}', "
                    f"but '{dep}' is not registered."
                )

        # Validate conflicts don't exist
        for conflict in definition.conflicts:
            if conflict in self._tools:
                raise ValueError(
                    f"Tool '{name}' conflicts with registered tool '{conflict}'."
                )

        self._tools[name] = tool
        self._categories[definition.category].append(name)
        self._dependency_graph[name] = set(definition.dependencies)
        logger.info("Registered tool: %s (category=%s)", name, definition.category)

    def unregister(self, name: str) -> None:
        """Unregister a tool by name.

        Raises:
            KeyError: If the tool is not registered.
        """
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' is not registered.")

        # Check if any other tool depends on this one
        dependents = [
            t_name for t_name, deps in self._dependency_graph.items()
            if name in deps
        ]
        if dependents:
            logger.warning(
                "Unregistering '%s' but tools %s depend on it.",
                name, dependents,
            )

        tool = self._tools.pop(name)
        self._categories[tool.definition.category].remove(name)
        self._dependency_graph.pop(name, None)
        logger.info("Unregistered tool: %s", name)

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def execute(self, name: str, **kwargs) -> ToolResult:
        """Execute a registered tool with retry and timeout logic.

        Args:
            name: The tool name.
            **kwargs: Arguments passed to the tool's execute method.

        Returns:
            ToolResult with the execution outcome.
        """
        if name not in self._tools:
            return ToolResult(
                status=ToolStatus.FATAL_ERROR,
                error=f"Unknown tool: {name}",
            )

        tool = self._tools[name]
        definition = tool.definition

        # Validate arguments
        is_valid, err_msg = tool.validate_args(**kwargs)
        if not is_valid:
            return ToolResult(
                status=ToolStatus.INVALID_ARGS,
                error=err_msg,
            )

        # Determine sandbox timeout
        sandbox = ExecutionSandbox(timeout=definition.timeout_seconds)

        start = time.perf_counter()
        last_error: str | None = None
        max_retries = definition.max_retries

        for attempt in range(max_retries + 1):
            try:
                result = await sandbox.execute(tool.execute, **kwargs)
                elapsed = (time.perf_counter() - start) * 1000
                result.execution_time_ms = elapsed
                result.retry_count = attempt

                # Update stats
                self._usage_stats[name]["calls"] += 1
                self._usage_stats[name]["total_ms"] += elapsed
                if result.status not in (ToolStatus.SUCCESS,):
                    self._usage_stats[name]["errors"] += 1

                return result

            except asyncio.TimeoutError:
                last_error = f"Tool '{name}' timed out after {definition.timeout_seconds}s"
                logger.warning("Tool timeout (attempt %d/%d): %s", attempt + 1, max_retries + 1, name)
                if attempt == max_retries:
                    return ToolResult(
                        status=ToolStatus.TIMEOUT,
                        error=last_error,
                        execution_time_ms=(time.perf_counter() - start) * 1000,
                        retry_count=attempt,
                    )
                await asyncio.sleep(min(2 ** attempt, 10))  # exponential backoff

            except Exception as e:
                last_error = str(e)
                logger.warning(
                    "Tool error (attempt %d/%d): %s - %s",
                    attempt + 1, max_retries + 1, name, e,
                )
                if attempt == max_retries:
                    is_retryable = self._is_retryable(e)
                    return ToolResult(
                        status=ToolStatus.RETRYABLE_ERROR if is_retryable else ToolStatus.FATAL_ERROR,
                        error=last_error,
                        execution_time_ms=(time.perf_counter() - start) * 1000,
                        retry_count=attempt,
                    )
                await asyncio.sleep(min(2 ** attempt, 10))

        # Should not reach here
        return ToolResult(
            status=ToolStatus.FATAL_ERROR,
            error=last_error or "Unknown execution failure",
            execution_time_ms=(time.perf_counter() - start) * 1000,
            retry_count=max_retries,
        )

    @staticmethod
    def _is_retryable(exception: Exception) -> bool:
        """Heuristic to decide if an error is likely retryable."""
        retryable_types = (
            TimeoutError,
            ConnectionError,
            asyncio.TimeoutError,
        )
        if isinstance(exception, retryable_types):
            return True
        msg = str(exception).lower()
        retryable_keywords = ["timeout", "connection", "rate limit", "503", "429", "temporary"]
        return any(kw in msg for kw in retryable_keywords)

    # ------------------------------------------------------------------
    # Query & Search
    # ------------------------------------------------------------------

    def search(self, query: str, top_k: int = 5) -> list[ToolDefinition]:
        """Semantic search over tool definitions using keyword matching.

        Searches tool names, descriptions, and category for matching keywords.
        Scores results by TF-IDF-like heuristic on overlapping tokens.

        Args:
            query: Natural language query describing the desired tool.
            top_k: Maximum number of results to return.

        Returns:
            List of matching ToolDefinition instances, sorted by relevance.
        """
        if not self._tools:
            return []

        query_tokens = set(query.lower().split())

        scored: list[tuple[float, ToolDefinition]] = []
        for tool in self._tools.values():
            definition = tool.definition
            doc = f"{definition.name} {definition.description} {definition.category}".lower()
            doc_tokens = set(doc.split())

            # Jaccard-like overlap score
            intersection = query_tokens & doc_tokens
            # Bias: exact name match gets high score
            score = len(intersection)
            if definition.name.lower() in query.lower():
                score += 10.0
            if query.lower() in definition.name.lower():
                score += 10.0

            # Boost by usage frequency
            usage = self._usage_stats.get(definition.name, {})
            score += min(usage.get("calls", 0) / 100.0, 1.0)

            scored.append((score, definition))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [definition for _, definition in scored[:top_k]]

    def list_all(self) -> list[ToolDefinition]:
        """Return definitions for all registered tools."""
        return [tool.definition for tool in self._tools.values()]

    def list_by_category(self, category: str) -> list[ToolDefinition]:
        """Return tool definitions for a specific category."""
        names = self._categories.get(category, [])
        return [self._tools[n].definition for n in names]

    def get_tool(self, name: str) -> BaseTool:
        """Get a tool instance by name.

        Raises:
            KeyError: If the tool is not registered.
        """
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' is not registered.")
        return self._tools[name]

    def get_openai_tools(self) -> list[dict]:
        """Convert all registered tools to OpenAI-compatible function call format.

        Returns:
            List of dicts suitable for use in OpenAI's `tools` parameter.
        """
        openai_tools = []
        for tool in self._tools.values():
            definition = tool.definition
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": definition.name,
                    "description": definition.description,
                    "parameters": {
                        "type": "object",
                        "properties": definition.parameters.get("properties", {}),
                        "required": definition.parameters.get("required", []),
                    },
                },
            })
        return openai_tools

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __repr__(self) -> str:
        return f"ToolRegistry(tools={list(self._tools.keys())})"
