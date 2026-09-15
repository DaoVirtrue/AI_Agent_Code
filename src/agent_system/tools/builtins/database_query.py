"""
Read-only SQLite query tool for agent use.

Only SELECT statements are permitted. All other SQL commands are rejected.
Supports parameterized queries to prevent SQL injection.
"""

import logging
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from src.core.tools import BaseTool, ToolDefinition, ToolResult, ToolStatus

logger = logging.getLogger(__name__)


class DatabaseQueryTool(BaseTool):
    """Execute read-only (SELECT) queries against SQLite databases.

    Designed for agent-driven data exploration. Enforces read-only access
    with query validation and row limits.

    Args:
        database_path: Path to the SQLite database file.
        max_rows: Maximum number of rows to return per query (default 1000).
    """

    def __init__(self, database_path: str = ":memory:", max_rows: int = 1000):
        self._db_path = database_path
        self._max_rows = max_rows
        self._connection: sqlite3.Connection | None = None

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="database_query",
            description=(
                "Execute a read-only SQL SELECT query against a SQLite database. "
                "Returns results as a list of dictionaries. "
                "Use this to explore tables, filter data, and compute aggregates. "
                "Only SELECT statements are allowed."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The SELECT SQL query to execute.",
                    },
                    "params": {
                        "type": "array",
                        "description": "Optional parameterized query values for placeholders (?).",
                        "items": {"type": "string"},
                        "default": [],
                    },
                },
                "required": ["query"],
            },
            category="data",
            timeout_seconds=15,
            max_retries=1,
        )

    async def execute(self, **kwargs) -> ToolResult:
        is_valid, err = self.validate_args(**kwargs)
        if not is_valid:
            return ToolResult(status=ToolStatus.INVALID_ARGS, error=err)

        query = kwargs["query"].strip()
        params = kwargs.get("params", []) or []

        # Validate read-only
        validation_error = self._validate_query(query)
        if validation_error:
            return ToolResult(status=ToolStatus.INVALID_ARGS, error=validation_error)

        try:
            conn = self._get_connection()
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(f"{query} LIMIT {self._max_rows + 1}", params)

            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            rows = [dict(row) for row in cursor.fetchall()]
            cursor.close()

            truncated = len(rows) > self._max_rows
            if truncated:
                rows = rows[:self._max_rows]

            return ToolResult(
                status=ToolStatus.SUCCESS,
                data={
                    "query": query,
                    "columns": columns,
                    "rows": rows,
                    "row_count": len(rows),
                    "truncated": truncated,
                },
            )

        except sqlite3.OperationalError as e:
            return ToolResult(
                status=ToolStatus.INVALID_ARGS,
                error=f"Database error: {e}",
            )
        except sqlite3.IntegrityError as e:
            return ToolResult(
                status=ToolStatus.INVALID_ARGS,
                error=f"Integrity error: {e}",
            )
        except Exception as e:
            logger.exception("Unexpected error in database_query")
            return ToolResult(
                status=ToolStatus.FATAL_ERROR,
                error=f"Unexpected error: {e}",
            )

    def _get_connection(self) -> sqlite3.Connection:
        """Get or create a SQLite connection in read-only mode."""
        if self._connection is None:
            if self._db_path == ":memory:":
                self._connection = sqlite3.connect(":memory:")
            else:
                # Open as read-only using URI mode
                self._connection = sqlite3.connect(
                    f"file:{self._db_path}?mode=ro",
                    uri=True,
                )
            self._connection.row_factory = sqlite3.Row
        return self._connection

    def _validate_query(self, query: str) -> str | None:
        """Validate that the query is a read-only SELECT statement.

        Returns an error message if invalid, or None if valid.
        """
        if not query:
            return "Empty query."

        normalized = query.strip().upper()

        # Must start with SELECT or WITH (CTE)
        if not (normalized.startswith("SELECT") or normalized.startswith("WITH")):
            return (
                f"Only SELECT queries are allowed. "
                f"Query starts with: {normalized.split()[0] if normalized.split() else 'nothing'}"
            )

        # Block dangerous operations
        dangerous_keywords = [
            "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE",
            "TRUNCATE", "REPLACE", "ATTACH", "DETACH", "PRAGMA",
            "VACUUM", "REINDEX",
        ]
        for kw in dangerous_keywords:
            # Match whole-word only (preceded/followed by non-alphanumeric)
            import re
            pattern = rf'\b{kw}\b'
            if re.search(pattern, normalized, re.IGNORECASE):
                return f"Disallowed operation detected: {kw}. Only SELECT queries are permitted."

        return None

    def load_schema(self, schema_sql: str) -> None:
        """Load a schema into an in-memory database for querying.

        Args:
            schema_sql: DDL SQL statements to create tables and insert data.
        """
        conn = self._get_connection()
        conn.executescript(schema_sql)
        conn.commit()

    async def close(self) -> None:
        """Close the database connection."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None
