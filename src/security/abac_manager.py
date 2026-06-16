"""Attribute-Based Access Control (ABAC) manager for fine-grained authorization."""

from datetime import datetime, time
from typing import Optional

from src.monitoring.logging_setup import get_logger

logger = get_logger(__name__)


class ABACPolicy:
    """A single ABAC policy rule."""

    def __init__(
        self,
        name: str,
        conditions: list[dict],
        effect: str = "allow",
        priority: int = 0,
    ):
        """Initialize an ABAC policy.

        Args:
            name: Policy name for identification.
            conditions: List of condition dicts. Each condition has:
                - attribute: str (e.g., 'user.role', 'resource.type', 'context.time')
                - operator: str (e.g., 'equals', 'in', 'contains', 'gt', 'lt', 'between')
                - value: Any (the comparison value)
            effect: 'allow' or 'deny'. Deny takes precedence.
            priority: Higher priority policies are evaluated first.
        """
        self.name = name
        self.conditions = conditions
        self.effect = effect
        self.priority = priority


class ABACManager:
    """Attribute-Based Access Control manager.

    Unlike RBAC (which checks only roles), ABAC evaluates access decisions
    based on multiple attributes:
    - User attributes: role, department, clearance_level, tenant_id, ip_address
    - Resource attributes: type, sensitivity, owner, classification
    - Context attributes: time_of_day, day_of_week, location, auth_method
    - Action attributes: verb, resource_type, risk_level

    Policies are evaluated in priority order. Deny rules take precedence over
    allow rules (default-deny principle).
    """

    def __init__(self):
        """Initialize the ABAC manager with default policies."""
        self._policies: list[ABACPolicy] = []

    def add_policy(self, policy: ABACPolicy) -> None:
        """Add a new ABAC policy.

        Args:
            policy: The ABACPolicy to add.
        """
        self._policies.append(policy)
        self._policies.sort(key=lambda p: -p.priority)

    def remove_policy(self, name: str) -> None:
        """Remove a policy by name.

        Args:
            name: The policy name to remove.
        """
        self._policies = [p for p in self._policies if p.name != name]

    def list_policies(self) -> list[dict]:
        """List all policies.

        Returns:
            List of policy dicts.
        """
        return [
            {
                "name": p.name,
                "conditions": p.conditions,
                "effect": p.effect,
                "priority": p.priority,
            }
            for p in self._policies
        ]

    async def check_access(
        self,
        user_attrs: dict,
        resource_attrs: dict,
        context: Optional[dict] = None,
    ) -> bool:
        """Check if access should be granted based on attributes.

        Evaluates all applicable policies. The decision logic:
        1. If any DENY policy matches -> access is DENIED
        2. If at least one ALLOW policy matches -> access is ALLOWED
        3. Default: DENY (no policy matches)

        Args:
            user_attrs: User attributes dict.
                Example: {"role": "developer", "tenant_id": "org-1", "clearance": 2}
            resource_attrs: Resource attributes dict.
                Example: {"type": "model", "id": "gpt-4o", "sensitivity": "internal"}
            context: Optional context attributes dict.
                Example: {"time": "14:30", "location": "office", "auth_method": "api_key"}

        Returns:
            True if access should be granted, False if denied.
        """
        context = context or {}

        # Merge all attributes into a single namespace with prefixes
        all_attrs = {}
        for k, v in user_attrs.items():
            all_attrs[f"user.{k}"] = v
        for k, v in resource_attrs.items():
            all_attrs[f"resource.{k}"] = v
        for k, v in context.items():
            all_attrs[f"context.{k}"] = v

        any_allow = False
        any_deny = False

        for policy in self._policies:
            if self._evaluate_policy(policy, all_attrs):
                if policy.effect == "deny":
                    any_deny = True
                    logger.debug(
                        "Access denied by policy",
                        policy=policy.name,
                        user_attrs=user_attrs.get("tenant_id", "unknown"),
                    )
                    break  # Deny takes precedence, stop evaluation
                elif policy.effect == "allow":
                    any_allow = True

        # Deny has precedence
        if any_deny:
            return False

        return any_allow

    def _evaluate_policy(
        self,
        policy: ABACPolicy,
        attributes: dict,
    ) -> bool:
        """Evaluate if a policy's conditions match the given attributes.

        All conditions must be satisfied (AND logic).

        Args:
            policy: The policy to evaluate.
            attributes: All available attributes.

        Returns:
            True if all conditions match.
        """
        if not policy.conditions:
            return True

        for condition in policy.conditions:
            if not self._evaluate_condition(condition, attributes):
                return False

        return True

    def _evaluate_condition(
        self,
        condition: dict,
        attributes: dict,
    ) -> bool:
        """Evaluate a single condition against attributes.

        Args:
            condition: Condition dict with attribute, operator, value.
            attributes: All available attributes.

        Returns:
            True if the condition is satisfied.
        """
        attr = condition.get("attribute", "")
        operator = condition.get("operator", "equals")
        expected = condition.get("value")

        actual = attributes.get(attr)

        # Special operators
        if operator == "exists":
            return attr in attributes

        if operator == "not_exists":
            return attr not in attributes

        if actual is None:
            return False

        # Comparison operators
        if operator == "equals":
            if isinstance(actual, str) and isinstance(expected, str):
                return actual.lower() == expected.lower()
            return actual == expected

        if operator == "not_equals":
            return actual != expected

        if operator == "in":
            if isinstance(expected, (list, tuple, set)):
                return actual in expected
            return actual == expected

        if operator == "not_in":
            if isinstance(expected, (list, tuple, set)):
                return actual not in expected
            return actual != expected

        if operator == "contains":
            if isinstance(actual, str) and isinstance(expected, str):
                return expected.lower() in actual.lower()
            if isinstance(actual, (list, tuple, set)):
                return expected in actual
            return False

        if operator == "starts_with":
            if isinstance(actual, str) and isinstance(expected, str):
                return actual.lower().startswith(expected.lower())
            return False

        if operator == "ends_with":
            if isinstance(actual, str) and isinstance(expected, str):
                return actual.lower().endswith(expected.lower())
            return False

        # Numeric comparisons
        if operator == "gt":
            try:
                return float(actual) > float(expected)
            except (TypeError, ValueError):
                return False

        if operator == "gte":
            try:
                return float(actual) >= float(expected)
            except (TypeError, ValueError):
                return False

        if operator == "lt":
            try:
                return float(actual) < float(expected)
            except (TypeError, ValueError):
                return False

        if operator == "lte":
            try:
                return float(actual) <= float(expected)
            except (TypeError, ValueError):
                return False

        if operator == "between":
            try:
                low, high = expected if isinstance(expected, (list, tuple)) else (expected, expected)
                return float(low) <= float(actual) <= float(high)
            except (TypeError, ValueError):
                return False

        # Time-based comparisons (for context.time attributes)
        if operator == "time_before":
            return self._compare_time(actual, expected, "before")

        if operator == "time_after":
            return self._compare_time(actual, expected, "after")

        if operator == "time_between":
            if isinstance(expected, (list, tuple)) and len(expected) == 2:
                return (
                    self._compare_time(actual, expected[0], "after")
                    and self._compare_time(actual, expected[1], "before")
                )
            return False

        logger.warning("Unknown operator", operator=operator)
        return False

    @staticmethod
    def _compare_time(actual, expected, direction: str) -> bool:
        """Compare time strings in HH:MM format."""
        try:
            actual_t = datetime.strptime(str(actual)[:5], "%H:%M").time()
            expected_t = datetime.strptime(str(expected)[:5], "%H:%M").time()
            if direction == "before":
                return actual_t < expected_t
            elif direction == "after":
                return actual_t > expected_t
            return False
        except (ValueError, TypeError):
            return False

    def make_access_decision(
        self,
        user_attrs: dict,
        resource_attrs: dict,
        context: Optional[dict] = None,
    ) -> dict:
        """Make and explain an access decision.

        Returns a detailed decision with reasoning.

        Args:
            user_attrs: User attributes.
            resource_attrs: Resource attributes.
            context: Context attributes.

        Returns:
            Dict with 'allowed', 'reason', and 'matching_policies'.
        """
        context = context or {}
        all_attrs = {}

        for k, v in user_attrs.items():
            all_attrs[f"user.{k}"] = v
        for k, v in resource_attrs.items():
            all_attrs[f"resource.{k}"] = v
        for k, v in context.items():
            all_attrs[f"context.{k}"] = v

        matching_policies = []
        denied = False
        allowed = False

        for policy in self._policies:
            if self._evaluate_policy(policy, all_attrs):
                matching_policies.append({
                    "name": policy.name,
                    "effect": policy.effect,
                    "priority": policy.priority,
                })
                if policy.effect == "deny":
                    denied = True
                    break
                elif policy.effect == "allow":
                    allowed = True

        if denied:
            reason = f"Access denied by policy: {matching_policies[-1]['name']}"
            return {"allowed": False, "reason": reason, "matching_policies": matching_policies}
        elif allowed:
            reason = f"Access allowed by {len([p for p in matching_policies if p['effect']=='allow'])} policies"
            return {"allowed": True, "reason": reason, "matching_policies": matching_policies}
        else:
            return {"allowed": False, "reason": "No matching policy (default deny)", "matching_policies": []}
