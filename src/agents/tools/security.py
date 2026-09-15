"""
Tool security manager with RBAC, approval workflows, and audit logging.
"""

import json
import logging
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

from src.core.tools import ToolResult, ToolStatus

logger = logging.getLogger(__name__)

# Sensitivity levels
SENSITIVITY_LOW = "low"
SENSITIVITY_MEDIUM = "medium"
SENSITIVITY_HIGH = "high"
SENSITIVITY_CRITICAL = "critical"

# Tool categorization by sensitivity for auto-approval logic
_SENSITIVITY_MAP: dict[str, str] = {
    "web_search": SENSITIVITY_LOW,
    "calculator": SENSITIVITY_LOW,
    "web_fetch": SENSITIVITY_LOW,
    "file_operations": SENSITIVITY_MEDIUM,
    "database_query": SENSITIVITY_MEDIUM,
    "code_executor": SENSITIVITY_HIGH,
}

# RBAC matrix: role -> allowed tool categories
_ROLE_PERMISSIONS: dict[str, set[str]] = {
    "admin": {"*"},  # all access
    "developer": {"general", "utility", "web", "data", "code", "filesystem"},
    "analyst": {"general", "utility", "web", "data"},
    "viewer": {"general", "utility"},
    "agent": {"general", "utility", "web", "data", "code", "filesystem"},
}


class ToolSecurityManager:
    """Manages tool access control, approval requirements, and audit logging.

    Features:
    - Role-Based Access Control (RBAC) for tool execution
    - Sensitivity-based approval requirements
    - Audit trail for all tool calls
    - Parameter-level validation hooks
    """

    def __init__(self, audit_log_path: str | None = None):
        self._audit_log: list[dict] = []
        self._audit_log_path = audit_log_path
        self._custom_permissions: dict[tuple[str, str], bool] = {}
        self._approval_hooks: dict[str, callable] = {}

    # ------------------------------------------------------------------
    # Permission checking
    # ------------------------------------------------------------------

    def check_permission(self, user_role: str, tool_name: str, **kwargs) -> bool:
        """Check if a user role has permission to execute a tool.

        Args:
            user_role: The role of the user (admin, developer, analyst, viewer, agent).
            tool_name: The name of the tool being executed.
            **kwargs: Additional context (e.g., specific parameters).

        Returns:
            True if the role is permitted to use the tool.
        """
        # Check custom overrides first
        key = (user_role, tool_name)
        if key in self._custom_permissions:
            return self._custom_permissions[key]

        # Normalize role
        role = user_role.lower()
        if role not in _ROLE_PERMISSIONS:
            logger.warning("Unknown role: %s", user_role)
            return False

        # Admin has universal access
        allowed_categories = _ROLE_PERMISSIONS[role]
        if "*" in allowed_categories:
            return True

        # Check tool-specific permissions
        # We need a way to map tool_name -> category. We use the sensitivity map
        # as a proxy: if a tool is in the sensitivity map, it's accessible based
        # on category. In practice, the caller would pass the tool's category.
        tool_category = kwargs.get("tool_category", "general")
        if tool_category not in allowed_categories:
            return False

        return True

    def set_permission(self, user_role: str, tool_name: str, allowed: bool) -> None:
        """Set a custom permission for a specific role/tool pair."""
        self._custom_permissions[(user_role.lower(), tool_name)] = allowed

    def revoke_permission(self, user_role: str, tool_name: str) -> None:
        """Revoke a custom permission."""
        key = (user_role.lower(), tool_name)
        self._custom_permissions.pop(key, None)

    # ------------------------------------------------------------------
    # Approval requirements
    # ------------------------------------------------------------------

    def requires_approval(self, tool_name: str, **kwargs) -> bool:
        """Determine if a tool call requires human approval.

        Based on the tool's sensitivity level and the specific parameters
        being passed.

        Args:
            tool_name: The name of the tool.
            **kwargs: The arguments being passed to the tool.

        Returns:
            True if the tool call requires approval before execution.
        """
        sensitivity = self._get_sensitivity(tool_name)

        # High and critical sensitivity always requires approval
        if sensitivity in (SENSITIVITY_HIGH, SENSITIVITY_CRITICAL):
            return True

        # Medium sensitivity may require approval for certain operations
        if sensitivity == SENSITIVITY_MEDIUM:
            # Check if there's a custom approval hook
            if tool_name in self._approval_hooks:
                return self._approval_hooks[tool_name](tool_name, kwargs)
            return True  # Default: medium sensitivity needs approval

        # Low sensitivity generally doesn't need approval
        if sensitivity == SENSITIVITY_LOW:
            # Unless there's a custom hook requiring it
            if tool_name in self._approval_hooks:
                return self._approval_hooks[tool_name](tool_name, kwargs)
            return False

        return True  # Unknown: require approval

    def register_approval_hook(self, tool_name: str, hook: callable) -> None:
        """Register a custom approval hook for a tool.

        The hook receives (tool_name, kwargs) and returns a bool.
        """
        self._approval_hooks[tool_name] = hook

    def _get_sensitivity(self, tool_name: str) -> str:
        """Get the sensitivity level for a tool."""
        return _SENSITIVITY_MAP.get(tool_name, SENSITIVITY_MEDIUM)

    # ------------------------------------------------------------------
    # Audit logging
    # ------------------------------------------------------------------

    def audit_tool_call(
        self,
        user_id: str,
        tool_name: str,
        params: dict,
        result: ToolResult,
        approved_by: str | None = None,
    ) -> None:
        """Log a tool execution for audit purposes.

        Args:
            user_id: The ID of the user or agent that made the call.
            tool_name: The name of the tool executed.
            params: The parameters passed to the tool.
            result: The ToolResult from execution.
            approved_by: If approval was required, who approved it.
        """
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_id": user_id,
            "tool_name": tool_name,
            "params": self._sanitize_params(params),
            "status": result.status.value,
            "error": result.error,
            "execution_time_ms": result.execution_time_ms,
            "retry_count": result.retry_count,
            "approved_by": approved_by,
        }
        self._audit_log.append(entry)
        logger.info(
            "AUDIT: user=%s tool=%s status=%s time=%.1fms",
            user_id, tool_name, result.status.value, result.execution_time_ms,
        )

        # Persist to file if configured
        if self._audit_log_path:
            self._flush_audit_log()

    def recent_audit_entries(self, limit: int = 50) -> list[dict]:
        """Return the most recent audit entries."""
        return self._audit_log[-limit:]

    def _sanitize_params(self, params: dict) -> dict:
        """Redact sensitive parameter values from audit logs."""
        SENSITIVE_KEYS = {"password", "token", "secret", "api_key", "auth", "credential"}
        sanitized = {}
        for key, value in params.items():
            if any(sk in key.lower() for sk in SENSITIVE_KEYS):
                sanitized[key] = "<REDACTED>"
            else:
                sanitized[key] = value
        return sanitized

    def _flush_audit_log(self) -> None:
        """Persist the audit log to disk."""
        if not self._audit_log_path:
            return
        try:
            with open(self._audit_log_path, "a", encoding="utf-8") as f:
                for entry in self._audit_log[-100:]:  # batch write recent
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError as e:
            logger.error("Failed to write audit log: %s", e)
