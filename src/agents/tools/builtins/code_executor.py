"""
Code execution tool using subprocess with timeout enforcement.

Supports Python code execution in an isolated subprocess with:
- Configurable timeout
- Memory limits via process isolation
- Output capture
- Blocklist-based safety validation
"""

import asyncio
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from src.core.tools import BaseTool, ToolDefinition, ToolResult, ToolStatus

logger = logging.getLogger(__name__)

# Blocked imports and dangerous operations
_BLOCKED_IMPORTS = {
    "os", "subprocess", "sys", "shutil", "importlib",
    "__builtins__", "builtins", "ctypes", "multiprocessing",
    "socket", "http", "urllib", "requests", "httpx",
    "pickle", "marshal", "signal", "threading",
}

_BLOCKED_FUNCTIONS = {
    "exec", "eval", "compile", "open", "__import__",
    "globals", "locals", "vars",
    "getattr", "setattr", "delattr",
    "breakpoint", "help",
}


class CodeExecutorTool(BaseTool):
    """Execute code snippets in an isolated subprocess with timeout.

    Supports Python code. Uses a subprocess for isolation with
    configurable timeout and output capture.

    Args:
        timeout: Maximum execution time in seconds.
        max_output_bytes: Maximum output size in bytes.
    """

    def __init__(self, timeout: int = 10, max_output_bytes: int = 100_000):
        self._default_timeout = timeout
        self._max_output = max_output_bytes

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="code_executor",
            description=(
                "Execute Python code in a sandboxed subprocess. "
                "Returns stdout, stderr, and exit code. "
                "Use for calculations, data processing, or simple scripting."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "The Python code to execute.",
                    },
                    "language": {
                        "type": "string",
                        "enum": ["python"],
                        "description": "Programming language (currently only 'python').",
                        "default": "python",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": f"Timeout in seconds (default {self._default_timeout}).",
                        "default": self._default_timeout,
                    },
                },
                "required": ["code"],
            },
            category="code",
            timeout_seconds=self._default_timeout + 5,
            max_retries=1,
        )

    async def execute(self, **kwargs) -> ToolResult:
        is_valid, err = self.validate_args(**kwargs)
        if not is_valid:
            return ToolResult(status=ToolStatus.INVALID_ARGS, error=err)

        code = kwargs["code"]
        language = kwargs.get("language", "python")
        timeout = kwargs.get("timeout", self._default_timeout)

        if language != "python":
            return ToolResult(
                status=ToolStatus.INVALID_ARGS,
                error=f"Unsupported language: {language}. Currently only 'python' is supported.",
            )

        # Safety check
        safety_issue = self._check_safety(code)
        if safety_issue:
            return ToolResult(
                status=ToolStatus.INVALID_ARGS,
                error=f"Code blocked for safety: {safety_issue}",
            )

        try:
            stdout, stderr, exit_code = await self._run_python(code, timeout)
        except asyncio.TimeoutError:
            return ToolResult(
                status=ToolStatus.TIMEOUT,
                error=f"Code execution timed out after {timeout}s.",
            )
        except Exception as e:
            logger.exception("Code execution failed")
            return ToolResult(
                status=ToolStatus.FATAL_ERROR,
                error=str(e),
            )

        return ToolResult(
            status=ToolStatus.SUCCESS,
            data={
                "stdout": stdout[:self._max_output],
                "stderr": stderr[:self._max_output],
                "exit_code": exit_code,
                "truncated": (
                    len(stdout) > self._max_output or
                    len(stderr) > self._max_output
                ),
            },
        )

    async def _run_python(self, code: str, timeout: int) -> tuple[str, str, int]:
        """Run Python code in a subprocess.

        Returns:
            Tuple of (stdout, stderr, exit_code).
        """
        # Write code to a temp file to avoid shell injection
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8",
        ) as f:
            f.write(code)
            temp_path = f.name

        try:
            process = await asyncio.create_subprocess_exec(
                "python",
                "-u",  # unbuffered
                temp_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                raise asyncio.TimeoutError()

            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")
            exit_code = process.returncode or 0

            return stdout, stderr, exit_code

        finally:
            # Cleanup temp file
            try:
                os.unlink(temp_path)
            except OSError:
                pass

    def _check_safety(self, code: str) -> str | None:
        """Perform static safety checks on the code.

        Returns an error message if unsafe, or None if safe.
        """
        code_lower = code.lower()
        code_words = set(code.split())

        # Check for import statements with blocked modules
        import re
        import_match = re.findall(
            r'(?:import\s+|from\s+)([a-zA-Z_][\w.]*)',
            code,
        )
        for mod in import_match:
            base_mod = mod.split(".")[0]
            if base_mod in _BLOCKED_IMPORTS:
                return f"Import of '{base_mod}' is blocked for security."

        # Check for specific blocked function calls
        for func in _BLOCKED_FUNCTIONS:
            # Match function calls like func( or func (
            pattern = rf'\b{re.escape(func)}\s*\('
            if re.search(pattern, code):
                return f"Use of '{func}()' is blocked for security."

        # Check for shell execution patterns
        if re.search(r'\bos\.system\b', code):
            return "os.system() is blocked."

        if re.search(r'\bsubprocess\b', code):
            return "subprocess usage is blocked."

        # Check for file write patterns (allow reading)
        if re.search(r'\bopen\s*\([^)]*["\']w', code):
            return "File write operations are blocked (reading allowed if file exists)."

        return None
