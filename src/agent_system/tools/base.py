"""
Base tool definitions for the agent system.
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ToolStatus(str, Enum):
    """Status codes for tool execution results."""
    SUCCESS = "success"
    TIMEOUT = "timeout"
    RETRYABLE_ERROR = "retryable_error"
    FATAL_ERROR = "fatal_error"
    INVALID_ARGS = "invalid_args"


class ToolDefinition(BaseModel):
    """Metadata and schema describing a tool."""
    name: str
    description: str
    parameters: dict  # JSON Schema for the tool's arguments
    category: str = "general"
    requires_approval: bool = False
    timeout_seconds: int = 30
    max_retries: int = 2
    dependencies: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)


class ToolResult(BaseModel):
    """Result returned from a tool execution."""
    status: ToolStatus
    data: Any = None
    error: str | None = None
    execution_time_ms: float = 0.0
    retry_count: int = 0


class BaseTool(ABC):
    """Abstract base class for all tools in the agent system."""

    @property
    @abstractmethod
    def definition(self) -> ToolDefinition:
        """Return the tool's definition (name, description, parameter schema, etc.)."""
        ...

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """Execute the tool with the given keyword arguments.

        Args:
            **kwargs: Arguments matching the tool's parameter schema.

        Returns:
            ToolResult with status, data, error, and timing information.
        """
        ...

    def validate_args(self, **kwargs) -> tuple[bool, str | None]:
        """Validate that the provided arguments match the tool's parameter schema.

        This performs basic type checking based on the JSON Schema definition.
        Returns (is_valid, error_message).
        """
        params = self.definition.parameters
        required = params.get("required", [])
        properties = params.get("properties", {})

        for param_name in required:
            if param_name not in kwargs:
                return False, f"Missing required parameter: {param_name}"

        for param_name, value in kwargs.items():
            if param_name not in properties:
                continue  # Extra args allowed

            param_schema = properties[param_name]
            expected_type = param_schema.get("type")

            if expected_type == "string" and not isinstance(value, str):
                return False, f"Parameter '{param_name}' must be a string"
            elif expected_type == "number" and not isinstance(value, (int, float)):
                return False, f"Parameter '{param_name}' must be a number"
            elif expected_type == "integer" and not isinstance(value, int):
                return False, f"Parameter '{param_name}' must be an integer"
            elif expected_type == "boolean" and not isinstance(value, bool):
                return False, f"Parameter '{param_name}' must be a boolean"
            elif expected_type == "array" and not isinstance(value, list):
                return False, f"Parameter '{param_name}' must be an array"
            elif expected_type == "object" and not isinstance(value, dict):
                return False, f"Parameter '{param_name}' must be an object"

            # Check enum constraints
            if "enum" in param_schema and value not in param_schema["enum"]:
                return False, (
                    f"Parameter '{param_name}' must be one of {param_schema['enum']}, "
                    f"got {value!r}"
                )

        return True, None

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.definition.name!r})"
