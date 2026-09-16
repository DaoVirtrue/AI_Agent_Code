"""权限配置存储 — 工具/技能的授权规则管理.

让用户可配置：哪些工具需要每次授权、哪些可以信任（免授权）。
默认规则：cli.execute 每次授权（高危），document.generate/ocr 免授权。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class PermissionRule:
    """一条授权规则."""

    tool_name: str
    requires_approval: bool
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "tool_name": self.tool_name,
            "requires_approval": self.requires_approval,
            "reason": self.reason,
        }


class PermissionStore:
    """Stores per-tool authorization rules."""

    def __init__(self):
        self._rules: dict[str, PermissionRule] = {}
        # 默认规则
        self._rules["cli.execute"] = PermissionRule(
            tool_name="cli.execute", requires_approval=True, reason="执行 shell 命令（高危，操作电脑）"
        )

    def get_rule(self, tool_name: str) -> Optional[PermissionRule]:
        return self._rules.get(tool_name)

    def set_rule(self, tool_name: str, requires_approval: bool, reason: str = "") -> PermissionRule:
        rule = PermissionRule(tool_name=tool_name, requires_approval=requires_approval, reason=reason)
        self._rules[tool_name] = rule
        return rule

    def list_rules(self) -> list[PermissionRule]:
        return list(self._rules.values())

    def requires_approval(self, tool_name: str) -> bool:
        """Check whether a tool requires approval (default False for unknown)."""
        rule = self._rules.get(tool_name)
        return rule.requires_approval if rule else False

    def __repr__(self) -> str:
        return f"PermissionStore(rules={len(self._rules)})"
