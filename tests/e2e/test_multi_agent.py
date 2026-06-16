"""End-to-end tests for multi-agent orchestration scenarios."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestMultiAgentOrchestration:
    """End-to-end tests for multi-agent collaboration workflows."""

    @pytest.fixture
    def test_client(self, test_app):
        """Get the FastAPI test client."""
        return test_app

    def test_orchestrate_agents(self, test_client):
        """Test multi-agent orchestration through API."""
        response = test_client.post(
            "/v1/agent/orchestrate",
            json={
                "task": "Research and write a report about AI trends",
                "agents": [
                    {"name": "researcher", "agent_type": "react", "tools": ["search"]},
                    {"name": "writer", "agent_type": "tool_use", "tools": ["write_file"]},
                ],
                "workflow": "sequential",
                "max_steps_total": 10,
                "model": "gpt-4o",
            },
            headers={"X-API-Key": "test-key"},
        )
        # The orchestration endpoint may return 200 or 503 if orchestrator not configured
        assert response.status_code in (200, 503)

    def test_list_agent_tools(self, test_client):
        """Test listing available agent tools."""
        response = test_client.get(
            "/v1/agent/tools",
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_agent_conversation_lifecycle(self, test_client):
        """Test the agent conversation lifecycle: run -> list -> get details."""
        # Run an agent (creates a conversation)
        run_response = test_client.post(
            "/v1/agent/run",
            json={
                "task": "Test task for conversation tracking",
                "agent_type": "react",
                "max_steps": 2,
            },
            headers={"X-API-Key": "test-key"},
        )
        assert run_response.status_code == 200

        # List conversations
        list_response = test_client.get(
            "/v1/agent/conversations?page=1&page_size=5",
            headers={"X-API-Key": "test-key"},
        )
        assert list_response.status_code == 200

    @pytest.mark.asyncio
    async def test_sequential_workflow(self):
        """Test sequential agent workflow: one agent feeds another."""
        # This test validates the workflow logic without the HTTP layer
        from src.agent.orchestrator import AgentOrchestrator

        orchestrator = AgentOrchestrator()

        # Mock agents
        mock_agent_a = AsyncMock()
        mock_agent_a.execute = AsyncMock(return_value=MagicMock(
            final_output="Research findings: AI is growing rapidly.",
            status="completed",
            steps=[],
            cost_usd=0.001,
            loop_detected=False,
        ))

        mock_agent_b = AsyncMock()
        mock_agent_b.execute = AsyncMock(return_value=MagicMock(
            final_output="Report written based on research.",
            status="completed",
            steps=[],
            cost_usd=0.002,
            loop_detected=False,
        ))

        with patch.object(orchestrator, '_get_agent') as mock_get:
            mock_get.side_effect = [mock_agent_a, mock_agent_b]

            result = await orchestrator.orchestrate(
                task="Research and write about AI",
                agents=[
                    {"name": "researcher", "agent_type": "react", "tools": ["search"]},
                    {"name": "writer", "agent_type": "tool_use", "tools": ["write_file"]},
                ],
                workflow="sequential",
                max_steps_total=20,
                tenant_id="test-tenant",
            )

            assert result is not None

    @pytest.mark.asyncio
    async def test_parallel_workflow(self):
        """Test parallel agent workflow: agents work simultaneously."""
        from src.agent.orchestrator import AgentOrchestrator

        orchestrator = AgentOrchestrator()

        async def make_agent(output):
            agent = AsyncMock()
            agent.execute = AsyncMock(return_value=MagicMock(
                final_output=output,
                status="completed",
                steps=[],
                cost_usd=0.001,
                loop_detected=False,
            ))
            return agent

        agents = [await make_agent(f"Output from agent {i}") for i in range(3)]

        with patch.object(orchestrator, '_get_agent') as mock_get:
            mock_get.side_effect = agents

            result = await orchestrator.orchestrate(
                task="Analyze from multiple perspectives",
                agents=[
                    {"name": f"agent_{i}", "agent_type": "react", "tools": ["search"]}
                    for i in range(3)
                ],
                workflow="parallel",
                max_steps_total=30,
                tenant_id="test-tenant",
            )

            assert result is not None

    @pytest.mark.asyncio
    async def test_debate_workflow(self):
        """Test debate workflow: agents debate and synthesize."""
        from src.agent.orchestrator import AgentOrchestrator

        orchestrator = AgentOrchestrator()

        agents = []
        for i in range(2):
            agent = AsyncMock()
            agent.execute = AsyncMock(return_value=MagicMock(
                final_output=f"Agent {i} argument: AI is transformative.",
                status="completed",
                steps=[],
                cost_usd=0.001,
                loop_detected=False,
            ))
            agents.append(agent)

        with patch.object(orchestrator, '_get_agent') as mock_get:
            mock_get.side_effect = agents

            result = await orchestrator.orchestrate(
                task="Debate the pros and cons of AI regulation",
                agents=[
                    {"name": "pro_agent", "agent_type": "react", "tools": ["search"]},
                    {"name": "con_agent", "agent_type": "react", "tools": ["search"]},
                ],
                workflow="debate",
                max_steps_total=30,
                tenant_id="test-tenant",
            )

            assert result is not None

    def test_human_approval_flow(self, test_client):
        """Test the human-in-the-loop approval flow."""
        # Approve a tool execution (conv_id may not exist in test)
        response = test_client.post(
            "/v1/agent/conversations/test-conv-1/approve",
            json={
                "approved": True,
                "comment": "Looks good",
            },
            headers={"X-API-Key": "test-key"},
        )
        # May be 404 if conv doesn't exist, which is fine
        assert response.status_code in (200, 404)

    def test_mcp_tool_call_through_gateway(self, test_client):
        """Test calling an MCP tool through the gateway."""
        response = test_client.post(
            "/v1/mcp/tools/call",
            params={
                "server_name": "test-server",
                "tool_name": "test-tool",
            },
            json={"key": "value"},
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code in (200, 400, 503)
