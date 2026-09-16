"""Unit tests for MCP approval gate + CLI tool + business expert."""

import pytest

from src.mcp.approval import ApprovalGate, ApprovalDenied
from src.mcp.tools.cli_tool import CLITool
from src.mcp.tools.document_tool import DocumentTool
from src.agents.expert import BusinessExpert, ExpertConfig, ExpertResult


class TestApprovalGate:
    """Tests for the approval gate (每次授权)."""

    @pytest.mark.asyncio
    async def test_approve_flow(self):
        gate = ApprovalGate(timeout_seconds=5)
        req = gate.request("cli.execute", {"command": "ls"}, reason="测试")
        # Simulate user approving
        gate.approve(req.request_id)
        approved = await gate.wait_for_decision(req.request_id)
        assert approved is True

    @pytest.mark.asyncio
    async def test_reject_flow(self):
        gate = ApprovalGate(timeout_seconds=5)
        req = gate.request("cli.execute", {"command": "rm file"})
        gate.reject(req.request_id)
        approved = await gate.wait_for_decision(req.request_id)
        assert approved is False

    @pytest.mark.asyncio
    async def test_timeout_rejects(self):
        gate = ApprovalGate(timeout_seconds=0.5)
        req = gate.request("cli.execute", {"command": "ls"})
        # Don't approve -> should time out and reject (fail-closed)
        approved = await gate.wait_for_decision(req.request_id)
        assert approved is False

    def test_list_pending(self):
        gate = ApprovalGate()
        gate.request("cli.execute", {"command": "ls"})
        pending = gate.list_pending()
        assert len(pending) == 1


class TestCLITool:
    """Tests for the CLI tool."""

    def test_requires_approval(self):
        tool = CLITool()
        assert tool.definition.requires_approval is True

    @pytest.mark.asyncio
    async def test_blocked_destructive_command(self):
        tool = CLITool()
        result = await tool.execute(command="rm -rf /")
        assert result.status.value == "fatal_error"
        assert "永久禁止" in result.error

    @pytest.mark.asyncio
    async def test_simple_command(self):
        tool = CLITool(timeout=5)
        result = await tool.execute(command="echo hello")
        assert result.status.value == "success"
        assert "hello" in result.data["stdout"]


class TestBusinessExpert:
    """Tests for the business expert module."""

    def test_build_system_prompt(self):
        config = ExpertConfig(name="法务专家", role="你是法律顾问", system_prompt="回答要专业", skills=["document.generate"])
        expert = BusinessExpert(config=config, llm=None, tools={})
        prompt = expert.config.build_system_prompt()
        assert "法律顾问" in prompt
        assert "专业" in prompt

    @pytest.mark.asyncio
    async def test_run_without_llm_returns_error(self):
        config = ExpertConfig(name="测试专家")
        expert = BusinessExpert(config=config, llm=None, tools={})
        result = await expert.run("任务")
        assert result.status == "error"

    def test_repr(self):
        config = ExpertConfig(name="数据分析师", skills=["document.generate"])
        expert = BusinessExpert(config=config, llm=None, tools={"document.generate": None})
        assert "数据分析师" in repr(expert)
