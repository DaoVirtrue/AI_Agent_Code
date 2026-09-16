"""Skill 仓库 — 可复用技能的定义、存储、拉取与安装.

Skill = 一段可复用的能力定义：
- name: 技能名（唯一标识）
- description: 技能说明（中文）
- instructions: 技能提示词/指令（注入到系统提示词）
- tools: 绑定调用的 MCP 工具名列表
- author: 作者
- version: 版本号

支持：
- 创建/上传 skill（写入仓库）
- 列出/搜索 skill（拉取浏览）
- 安装 skill（绑定到专家/会话，注入 instructions）
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class SkillDefinition:
    """A reusable skill definition."""

    name: str
    description: str = ""
    instructions: str = ""
    tools: list[str] = field(default_factory=list)
    author: str = "user"
    version: str = "1.0.0"
    created_at: float = field(default_factory=time.time)
    skill_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    def to_dict(self) -> dict:
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "description": self.description,
            "instructions": self.instructions,
            "tools": self.tools,
            "author": self.author,
            "version": self.version,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SkillDefinition":
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            instructions=data.get("instructions", ""),
            tools=data.get("tools", []),
            author=data.get("author", "user"),
            version=data.get("version", "1.0.0"),
            created_at=data.get("created_at", time.time()),
            skill_id=data.get("skill_id", str(uuid.uuid4())[:8]),
        )


class SkillStore:
    """In-memory skill repository (production: PostgreSQL)."""

    def __init__(self):
        self._skills: dict[str, SkillDefinition] = {}

    def create(self, skill: SkillDefinition) -> SkillDefinition:
        """Create/upsert a skill into the repository."""
        if skill.name in self._skills:
            logger.info("Skill '%s' already exists, updating", skill.name)
        self._skills[skill.name] = skill
        return skill

    def get(self, name: str) -> Optional[SkillDefinition]:
        return self._skills.get(name)

    def list_all(self) -> list[SkillDefinition]:
        return list(self._skills.values())

    def search(self, query: str = "") -> list[SkillDefinition]:
        """Search skills by name/description (keyword match)."""
        if not query:
            return self.list_all()
        q = query.lower()
        return [
            s for s in self._skills.values()
            if q in s.name.lower() or q in s.description.lower()
        ]

    def delete(self, name: str) -> bool:
        if name in self._skills:
            del self._skills[name]
            return True
        return False

    def build_instructions(self, skill_names: list[str]) -> str:
        """Build a combined system-prompt fragment from installed skills."""
        parts = []
        for name in skill_names:
            s = self._skills.get(name)
            if s and s.instructions:
                parts.append(f"【技能：{s.name}】\n{s.instructions}")
        return "\n\n".join(parts)

    def __len__(self) -> int:
        return len(self._skills)

    def __repr__(self) -> str:
        return f"SkillStore(skills={len(self._skills)})"
