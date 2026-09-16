"""Expert registry — 管理已定义的业务专家实例.

Each expert is a configured BusinessExpert (role + prompt + skills + MCP).
The registry maps (tenant_id, name) -> expert instance, so different tenants
can define their own experts.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from src.agents.expert import BusinessExpert, ExpertConfig

logger = logging.getLogger(__name__)


class ExpertRegistry:
    """Registry of business experts.

    Args:
        llm: LLM used by all experts.
        tools: Dict of tool_name -> BaseTool available to experts.
        approval_gate: ApprovalGate for requiring user approval on tool calls.
    """

    def __init__(self, llm: Any = None, tools: Optional[dict] = None, approval_gate: Any = None, rag_pipeline: Any = None):
        self.llm = llm
        self.tools = tools or {}
        self.approval_gate = approval_gate
        self.rag_pipeline = rag_pipeline
        self._experts: dict[tuple[str, str], BusinessExpert] = {}  # (tenant_id, name) -> expert

    def register(self, config: ExpertConfig, tenant_id: str = "default") -> BusinessExpert:
        """Define (or redefine) an expert for a tenant."""
        expert = BusinessExpert(
            config=config,
            llm=self.llm,
            tools=self.tools,
            approval_gate=self.approval_gate,
            rag_pipeline=self.rag_pipeline,
        )
        self._experts[(tenant_id, config.name)] = expert
        logger.info("Defined expert '%s' (tenant=%s, skills=%s, kb=%s)", config.name, tenant_id, config.skills, config.knowledge_bases)
        return expert

    def get(self, name: str, tenant_id: str = "default") -> Optional[BusinessExpert]:
        return self._experts.get((tenant_id, name))

    def list_all(self, tenant_id: str = "default") -> list[dict]:
        """List expert configs for a tenant."""
        result = []
        for (tid, name), expert in self._experts.items():
            if tid == tenant_id:
                result.append({
                    "name": name,
                    "role": expert.config.role,
                    "skills": expert.config.skills,
                    "description": expert.config.description,
                })
        return result

    def __len__(self) -> int:
        return len(self._experts)

    def __repr__(self) -> str:
        return f"ExpertRegistry(experts={len(self._experts)})"
