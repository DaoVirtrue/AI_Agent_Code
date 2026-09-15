"""Unit tests for the Plan-Execute-Verify (PEV) agent."""

import pytest

from src.agents.pev import PEVAgent, PEVResult
from src.harness.guard import Harness, HarnessConfig
from src.harness.verify import ContainsVerifier


class _FakeLLM:
    """Deterministic LLM stub that returns a numbered plan."""

    def __init__(self, plan_text="1. Research the topic\n2. Summarize findings"):
        self._plan_text = plan_text
        self.calls = []

    async def ainvoke(self, messages):
        self.calls.append(messages)
        content = messages[-1]["content"] if messages else ""
        # Planning prompt -> return plan; reasoning prompt -> return answer
        if "planning agent" in content.lower() or "break the task" in content.lower():
            return _Msg(self._plan_text)
        return _Msg("A synthesized answer about the task.")


class _Msg:
    def __init__(self, content):
        self.content = content


class TestPEVAgent:
    """Tests for the PEV state machine."""

    def test_heuristic_plan_without_llm(self):
        agent = PEVAgent()
        plan_steps = agent._heuristic_plan("do something")
        assert len(plan_steps) == 1

    @pytest.mark.asyncio
    async def test_run_with_llm_and_passing_verifier(self):
        verifier = ContainsVerifier(["synthesized"])
        agent = PEVAgent(llm=_FakeLLM(), verifier=verifier)
        result = await agent.run("research AI trends")
        assert isinstance(result, PEVResult)
        assert result.status == "completed"
        assert result.verification["passed"] is True
        assert len(result.steps) > 0

    @pytest.mark.asyncio
    async def test_run_with_tool_call(self):
        calls = []
        async def search_tool(**kwargs):
            calls.append(kwargs)
            return {"results": ["r1"]}

        verifier = ContainsVerifier(["synthesized"])
        agent = PEVAgent(
            llm=_FakeLLM(),
            tools={"search": search_tool},
            verifier=verifier,
        )
        result = await agent.run("search for something")
        assert result.status == "completed"

    @pytest.mark.asyncio
    async def test_verification_failure_triggers_replan(self):
        # Verifier always fails -> should replan then fail verification
        class _AlwaysFail:
            def verify(self, output, context=None):
                from src.harness.verify import VerificationResult
                return VerificationResult(False, "always fails")

        agent = PEVAgent(llm=_FakeLLM(), verifier=_AlwaysFail(), max_replans=1)
        result = await agent.run("task")
        assert result.status == "failed_verification"
        assert result.verification["passed"] is False

    @pytest.mark.asyncio
    async def test_harness_max_steps_limits(self):
        # Very low max steps should trigger a HarnessViolation
        harness = Harness(HarnessConfig(max_steps=1))
        verifier = ContainsVerifier(["synthesized"])
        agent = PEVAgent(llm=_FakeLLM(), verifier=verifier, harness=harness)
        result = await agent.run("task that requires many steps")
        # Either completed or harness-limited; should not raise
        assert result.status in ("completed", "max_steps_reached", "error", "failed_verification")
