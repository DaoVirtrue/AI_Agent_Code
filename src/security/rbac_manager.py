"""Role-Based Access Control (RBAC) manager for LLM Platform."""

from typing import Optional, Callable

from src.observability.logging_setup import get_logger

logger = get_logger(__name__)


class RBACManager:
    """Role-Based Access Control manager.

    Enforces access control based on predefined roles with associated permissions.
    Each role maps to a set of allowed actions. Actions use a resource:verb pattern.

    Architecture:
    - Roles are hierarchical (admin > developer > viewer)
    - Admin role has wildcard ("*") permission for all actions
    - Permissions are additive
    """

    # Core role definitions
    ROLES: dict[str, list[str]] = {
        "admin": ["*"],
        "developer": [
            "read",
            "write",
            "execute",
            "models:read",
            "models:list",
            "prompts:read",
            "prompts:write",
            "prompts:execute",
            "rag:read",
            "rag:write",
            "rag:execute",
            "agent:read",
            "agent:execute",
            "api_keys:read",
            "api_keys:write",
            "usage:read",
        ],
        "viewer": [
            "read",
            "models:read",
            "models:list",
            "prompts:read",
            "rag:read",
            "agent:read",
            "usage:read",
        ],
        "operator": [
            "read",
            "execute",
            "models:read",
            "models:list",
            "prompts:read",
            "rag:read",
            "rag:execute",
            "agent:read",
            "agent:execute",
            "usage:read",
            "monitoring:read",
            "health:read",
        ],
    }

    # Action aliases
    ACTION_ALIASES: dict[str, str] = {
        "read": "models:read",
        "write": "models:write",
        "execute": "models:execute",
    }

    def __init__(self, custom_roles: Optional[dict[str, list[str]]] = None):
        """Initialize RBAC manager.

        Args:
            custom_roles: Optional custom role definitions to merge with defaults.
        """
        self.roles = self.ROLES.copy()
        if custom_roles:
            self.roles.update(custom_roles)

    def check_permission(
        self,
        role: str,
        action: str,
    ) -> bool:
        """Check if a role has permission to perform an action.

        Args:
            role: The user's role name (e.g., 'admin', 'developer', 'viewer').
            action: The action to check (e.g., 'models:read', 'write').

        Returns:
            True if the role has the required permission, False otherwise.
        """
        if role not in self.roles:
            logger.warning("Unknown role checked", role=role, action=action)
            return False

        allowed_actions = self.roles[role]

        # Admin has wildcard access
        if "*" in allowed_actions:
            return True

        # Direct action check
        if action in allowed_actions:
            return True

        # Check aliases
        if action in self.ACTION_ALIASES:
            resolved = self.ACTION_ALIASES[action]
            if resolved in allowed_actions:
                return True

        # Check prefix match (e.g., 'models:write' matches 'models:*')
        action_parts = action.split(":")
        for allowed in allowed_actions:
            allowed_parts = allowed.split(":")
            if len(allowed_parts) == 2 and allowed_parts[1] == "*":
                if allowed_parts[0] == action_parts[0]:
                    return True

        # Check simple verb match
        if ":" not in action:
            verb = action
            for allowed in allowed_actions:
                if allowed.startswith(f"{verb}:") or allowed == verb:
                    return True

        return False

    def check_permissions(
        self,
        role: str,
        actions: list[str],
    ) -> dict[str, bool]:
        """Check multiple permissions at once.

        Args:
            role: The user's role name.
            actions: List of actions to check.

        Returns:
            Dict mapping each action to its permission result.
        """
        return {
            action: self.check_permission(role, action)
            for action in actions
        }

    def require_permission(
        self,
        role: str,
        action: str,
    ) -> None:
        """Enforce a permission check, raising PermissionError if denied.

        Args:
            role: The user's role name.
            action: The action to check.

        Raises:
            PermissionError: If the role does not have the required permission.
        """
        if not self.check_permission(role, action):
            raise PermissionError(
                f"Role '{role}' does not have permission for action '{action}'"
            )

    def get_allowed_actions(self, role: str) -> list[str]:
        """Get all actions a role is allowed to perform.

        Args:
            role: The role name.

        Returns:
            List of allowed action strings.
        """
        return self.roles.get(role, [])

    def add_role(self, name: str, permissions: list[str]) -> None:
        """Add a new role definition.

        Args:
            name: Role name.
            permissions: List of permission strings.
        """
        if name in self.roles:
            logger.warning("Overwriting existing role", role=name)
        self.roles[name] = list(permissions)
        logger.info("Role added", role=name, permission_count=len(permissions))

    def update_role(self, name: str, permissions: list[str]) -> None:
        """Update an existing role's permissions.

        Args:
            name: Role name.
            permissions: New list of permission strings.

        Raises:
            ValueError: If the role does not exist.
        """
        if name not in self.roles:
            raise ValueError(f"Role '{name}' does not exist")
        self.roles[name] = list(permissions)
        logger.info("Role updated", role=name, permission_count=len(permissions))

    def remove_role(self, name: str) -> None:
        """Remove a role definition.

        Args:
            name: Role name.
        """
        if name in self.roles:
            del self.roles[name]
            logger.info("Role removed", role=name)

    def list_roles(self) -> dict[str, list[str]]:
        """List all defined roles and their permissions.

        Returns:
            Dict mapping role names to permission lists.
        """
        return self.roles.copy()

    def is_valid_role(self, role: str) -> bool:
        """Check if a role name is defined.

        Args:
            role: The role name to check.

        Returns:
            True if the role exists.
        """
        return role in self.roles


class PermissionDeniedError(Exception):
    """Raised when a permission check fails."""
    pass


def create_permission_checker(
    rbac: RBACManager,
    action: str,
) -> Callable:
    """Create a permission-checking dependency function.

    Args:
        rbac: RBACManager instance.
        action: The required action string.

    Returns:
        A callable that can be used as a dependency.
    """
    def checker(role: str) -> bool:
        if not rbac.check_permission(role, action):
            raise PermissionDeniedError(
                f"Role '{role}' does not have permission for action '{action}'"
            )
        return True
    return checker
