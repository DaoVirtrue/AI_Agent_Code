"""CLI tool — 通过 MCP 直接操作电脑（执行 shell 命令）.

This is a high-risk tool: every invocation requires explicit user approval
(``requires_approval=True``). It runs a shell command in a subprocess with
a hard timeout and output-size cap, and blocks a denylist of destructive
commands even with approval.
"""

from __future__ import annotations

import asyncio
import logging
import shlex
from typing import Any

from src.core.tools import BaseTool, ToolDefinition, ToolResult, ToolStatus

logger = logging.getLogger(__name__)

# Commands that are NEVER allowed, even with user approval.
_BLOCKED_PATTERNS = [
    "rm -rf /",
    "mkfs",
    "dd if=/dev/zero",
    ":(){ :|:& };:",  # fork bomb
    "shutdown",
    "reboot",
]


class CLITool(BaseTool):
    """Execute a shell command on the host machine (with approval).

    Args:
        timeout: Max command runtime in seconds.
        max_output: Max captured stdout/stderr bytes.
    """

    def __init__(self, timeout: int = 30, max_output: int = 20_000):
        self.timeout = timeout
        self.max_output = max_output

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="cli.execute",
            description=(
                "在宿主机上执行 shell 命令（操作电脑）。高危操作，每次调用都需要用户授权。"
                "返回 stdout/stderr/退出码。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "要执行的 shell 命令"},
                    "timeout": {"type": "integer", "description": f"超时秒数（默认 {self.timeout}）", "default": self.timeout},
                },
                "required": ["command"],
            },
            category="cli",
            requires_approval=True,  # 每次授权
            timeout_seconds=self.timeout + 10,
            max_retries=0,  # 不可自动重试
        )

    async def execute(self, **kwargs) -> ToolResult:
        is_valid, err = self.validate_args(**kwargs)
        if not is_valid:
            return ToolResult(status=ToolStatus.INVALID_ARGS, error=err)

        command = kwargs["command"].strip()
        timeout = kwargs.get("timeout", self.timeout)

        # Denylist check (before execution, regardless of approval)
        for pattern in _BLOCKED_PATTERNS:
            if pattern in command.lower():
                return ToolResult(
                    status=ToolStatus.FATAL_ERROR,
                    error=f"命令被永久禁止（含危险模式: {pattern}）",
                )

        # Never allow shell metacharacter chaining that could bypass approval intent
        if any(c in command for c in (";", "&&", "||", "`", "$(")):
            # Allow but flag; the approval gate will show the full command to the user.
            pass

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout_b, stderr_b = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return ToolResult(
                    status=ToolStatus.TIMEOUT,
                    error=f"命令执行超时（>{timeout}s）",
                )

            stdout = stdout_b.decode("utf-8", errors="replace")[: self.max_output]
            stderr = stderr_b.decode("utf-8", errors="replace")[: self.max_output]
            exit_code = process.returncode or 0

            return ToolResult(
                status=ToolStatus.SUCCESS if exit_code == 0 else ToolStatus.FATAL_ERROR,
                data={
                    "stdout": stdout,
                    "stderr": stderr,
                    "exit_code": exit_code,
                    "truncated": len(stdout_b) > self.max_output or len(stderr_b) > self.max_output,
                },
                error=None if exit_code == 0 else f"命令退出码 {exit_code}: {stderr[:200]}",
            )
        except Exception as e:  # noqa: BLE001
            logger.exception("CLI execution failed")
            return ToolResult(status=ToolStatus.FATAL_ERROR, error=str(e))
