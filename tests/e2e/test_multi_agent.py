"""End-to-end tests for multi-agent orchestration + business expert."""

import pytest

from src.agents.expert import BusinessExpert, ExpertConfig, ExpertResult
from src.agents.expert_registry import ExpertRegistry
from src.agents.orchestration.sequential import SequentialOrchestrator
from src.mcp.approval import ApprovalGate


class _FakeLLM:
    """Deterministic LLM stub."""

    def __init__(self, response="expert answer"):
        self._response = response

    async def ainvoke(self, messages):
        class _Msg:
            content = self._response
        return _Msg()


class _FakeTool:
    """A simple tool with a definition."""

    def __init__(self, name, description=""):
        self._name = name
        self._description = description or f"Tool {name}"

    @property
    def definition(self):
        from src.core.tools import ToolDefinition
        return ToolDefinition(name=self._name, description=self._description,
                              parameters={"type": "object", "properties": {}, "required": []})

    async def execute(self, **kwargs):
        from src.core.tools import ToolResult, ToolStatus
        return ToolResult(status=ToolStatus.SUCCESS, data={"ok": True})


class TestMultiAgentOrchestration:
    """End-to-end: expert registry + business expert + sequential orchestrator."""

    def test_expert_registry_register_and_get(self):
        registry = ExpertRegistry(llm=_FakeLLM(), tools={"doc": _FakeTool("doc")})
        config = ExpertConfig(name="分析师", role="数据分析", skills=["doc"])
        registry.register(config, tenant_id="t1")

        expert = registry.get("分析师", tenant_id="t1")
        assert expert is not None
        assert expert.config.name == "分析师"

    @pytest.mark.asyncio
    async def test_expert_run_with_llm(self):
        expert = BusinessExpert(
            config=ExpertConfig(name="助手", role="通用助手"),
            llm=_FakeLLM("这是专家的回答"),
            tools={},
        )
        result = await expert.run("你好")
        assert result.status == "completed"
        assert "回答" in result.output

    @pytest.mark.asyncio
    async def test_sequential_orchestrator(self):
        """Sequential orchestrator chains two agents (using simple runnables)."""
        class _Agent:
            def __init__(self, name, output):
                self.name = name
                self.output = output
                self.steps = 1
                self.success = True
                self.error = None
                self.tools_used = []

            async def run(self, task):
                class _R:
                    answer = self.output
                    steps = 1
                    tools_used = []
                    success = True
                    error = None
                return _R()

        orch = SequentialOrchestrator(agents=[_Agent("a", "第一步结果"), _Agent("b", "最终答案")])
        result = await orch.run("任务")
        assert result is not None

    @pytest.mark.asyncio
    async def test_approval_gate_blocks_and_approves(self):
        gate = ApprovalGate(timeout_seconds=5)
        req = gate.request("cli.execute", {"command": "ls"})
        # Approve then check
        gate.approve(req.request_id)
        approved = await gate.wait_for_decision(req.request_id)
        assert approved is True
