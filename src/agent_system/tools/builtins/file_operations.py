"""
File operations tool for reading and writing within a sandboxed directory.

All paths are resolved relative to a configurable base directory to
prevent path-traversal attacks.
"""

import logging
import os
from pathlib import Path
from typing import Any

import aiofiles
import aiofiles.os as aio_os

from src.core.tools import BaseTool, ToolDefinition, ToolResult, ToolStatus

logger = logging.getLogger(__name__)


class FileOperationsTool(BaseTool):
    """Read and write files within a sandboxed directory.

    All paths are resolved relatively to a base directory. Path-traversal
    attempts (e.g., '../') are detected and blocked.

    Args:
        base_dir: The root directory for all file operations.
        max_file_size_mb: Maximum file size for read/write operations (default 50MB).
    """

    def __init__(self, base_dir: str | None = None, max_file_size_mb: int = 50):
        self._base_dir = Path(base_dir or os.getcwd()).resolve()
        self._max_size = max_file_size_mb * 1024 * 1024
        self._base_dir.mkdir(parents=True, exist_ok=True)

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="file_operations",
            description=(
                "Read from or write to files within a sandboxed directory. "
                "Operations: read (read entire file), write (create/overwrite file), "
                "list (list directory contents), exists (check if path exists). "
                "All paths are relative to the sandbox root."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["read", "write", "list", "exists", "delete"],
                        "description": "The file operation to perform.",
                    },
                    "path": {
                        "type": "string",
                        "description": "Relative path to the file or directory.",
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write (required for 'write' operation).",
                    },
                    "encoding": {
                        "type": "string",
                        "description": "File encoding (default 'utf-8').",
                        "default": "utf-8",
                    },
                },
                "required": ["operation", "path"],
            },
            category="filesystem",
            timeout_seconds=10,
            max_retries=1,
        )

    async def execute(self, **kwargs) -> ToolResult:
        is_valid, err = self.validate_args(**kwargs)
        if not is_valid:
            return ToolResult(status=ToolStatus.INVALID_ARGS, error=err)

        operation = kwargs["operation"]
        relative_path = kwargs["path"]
        encoding = kwargs.get("encoding", "utf-8")

        # Resolve and validate the path
        try:
            resolved = self._resolve_path(relative_path)
        except ValueError as e:
            return ToolResult(status=ToolStatus.INVALID_ARGS, error=str(e))

        try:
            if operation == "read":
                return await self._read_file(resolved, encoding)
            elif operation == "write":
                content = kwargs.get("content")
                if content is None:
                    return ToolResult(
                        status=ToolStatus.INVALID_ARGS,
                        error="'content' is required for 'write' operation.",
                    )
                return await self._write_file(resolved, content, encoding)
            elif operation == "list":
                return await self._list_dir(resolved)
            elif operation == "exists":
                return await self._check_exists(resolved)
            elif operation == "delete":
                return await self._delete_file(resolved)
            else:
                return ToolResult(
                    status=ToolStatus.INVALID_ARGS,
                    error=f"Unknown operation: {operation}",
                )
        except PermissionError as e:
            return ToolResult(
                status=ToolStatus.FATAL_ERROR,
                error=f"Permission denied: {e}",
            )
        except Exception as e:
            logger.exception("File operation failed: %s", e)
            return ToolResult(
                status=ToolStatus.FATAL_ERROR,
                error=str(e),
            )

    def _resolve_path(self, relative_path: str) -> Path:
        """Resolve a relative path safely, preventing directory traversal.

        Raises:
            ValueError: If the path escapes the base directory.
        """
        if not relative_path:
            raise ValueError("Empty path.")

        # Normalize the path
        normalized = Path(relative_path.strip("/\\"))

        # Resolve fully, then check it's within base_dir
        resolved = (self._base_dir / normalized).resolve()

        try:
            resolved.relative_to(self._base_dir)
        except ValueError:
            raise ValueError(
                f"Path traversal detected: '{relative_path}' escapes the sandbox directory."
            )

        return resolved

    async def _read_file(self, path: Path, encoding: str) -> ToolResult:
        """Read the contents of a file."""
        if not path.exists():
            return ToolResult(
                status=ToolStatus.INVALID_ARGS,
                error=f"File not found: {path.name}",
            )
        if not path.is_file():
            return ToolResult(
                status=ToolStatus.INVALID_ARGS,
                error=f"Not a file: {path.name}",
            )

        stat = await aio_os.stat(path)
        if stat.st_size > self._max_size:
            return ToolResult(
                status=ToolStatus.INVALID_ARGS,
                error=(
                    f"File too large: {stat.st_size} bytes "
                    f"(max {self._max_size} bytes)"
                ),
            )

        try:
            async with aiofiles.open(path, "r", encoding=encoding) as f:
                content = await f.read()
        except UnicodeDecodeError:
            # Try reading as binary and return hex representation
            async with aiofiles.open(path, "rb") as f:
                content = f"<binary file, {stat.st_size} bytes>"

        return ToolResult(
            status=ToolStatus.SUCCESS,
            data={
                "path": str(path.relative_to(self._base_dir)),
                "size_bytes": stat.st_size,
                "content": content,
                "operation": "read",
            },
        )

    async def _write_file(self, path: Path, content: str, encoding: str) -> ToolResult:
        """Write content to a file, creating parent directories as needed."""
        if len(content.encode(encoding)) > self._max_size:
            return ToolResult(
                status=ToolStatus.INVALID_ARGS,
                error=f"Content too large (max {self._max_size} bytes).",
            )

        path.parent.mkdir(parents=True, exist_ok=True)

        async with aiofiles.open(path, "w", encoding=encoding) as f:
            await f.write(content)

        written_size = len(content.encode(encoding))
        return ToolResult(
            status=ToolStatus.SUCCESS,
            data={
                "path": str(path.relative_to(self._base_dir)),
                "size_bytes": written_size,
                "operation": "write",
                "message": f"Successfully wrote {written_size} bytes.",
            },
        )

    async def _list_dir(self, path: Path) -> ToolResult:
        """List the contents of a directory."""
        if not path.exists():
            return ToolResult(
                status=ToolStatus.INVALID_ARGS,
                error=f"Directory not found: {path.name}",
            )
        if not path.is_dir():
            return ToolResult(
                status=ToolStatus.INVALID_ARGS,
                error=f"Not a directory: {path.name}",
            )

        entries = []
        try:
            for entry in sorted(path.iterdir()):
                stat = entry.stat()
                entries.append({
                    "name": entry.name,
                    "type": "directory" if entry.is_dir() else "file",
                    "size_bytes": stat.st_size if entry.is_file() else None,
                    "modified": stat.st_mtime,
                })
        except OSError as e:
            return ToolResult(
                status=ToolStatus.FATAL_ERROR,
                error=f"Failed to list directory: {e}",
            )

        return ToolResult(
            status=ToolStatus.SUCCESS,
            data={
                "path": str(path.relative_to(self._base_dir)),
                "entries": entries,
                "count": len(entries),
                "operation": "list",
            },
        )

    async def _check_exists(self, path: Path) -> ToolResult:
        """Check if a path exists."""
        return ToolResult(
            status=ToolStatus.SUCCESS,
            data={
                "path": str(path.relative_to(self._base_dir)),
                "exists": path.exists(),
                "is_file": path.is_file() if path.exists() else False,
                "is_directory": path.is_dir() if path.exists() else False,
                "operation": "exists",
            },
        )

    async def _delete_file(self, path: Path) -> ToolResult:
        """Delete a file or empty directory."""
        if not path.exists():
            return ToolResult(
                status=ToolStatus.INVALID_ARGS,
                error=f"Path not found: {path.name}",
            )

        try:
            if path.is_dir():
                await aio_os.rmdir(path)
            else:
                await aio_os.remove(path)
        except OSError as e:
            return ToolResult(
                status=ToolStatus.FATAL_ERROR,
                error=f"Failed to delete: {e}",
            )

        return ToolResult(
            status=ToolStatus.SUCCESS,
            data={
                "path": str(path.relative_to(self._base_dir)),
                "operation": "delete",
                "message": "Successfully deleted.",
            },
        )
