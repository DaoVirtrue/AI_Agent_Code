"""Integration tests for gateway routing with mocked LLM providers."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestGatewayRouting:
    """Integration tests for the gateway routing logic."""

    @pytest.fixture
    async def gateway_setup(self, test_redis):
        """Set up a gateway router with mocked dependencies."""
        from src.gateway.router import GatewayRouter
        from src.gateway.model_registry import ModelRegistry
        from src.gateway.circuit_breaker import CircuitBreakerRegistry
        from src.gateway.rate_limiter import RateLimiter

        # Create test model registry
        registry = ModelRegistry()
        registry.add_model(
            id="gpt-4o",
            provider="openai",
            display_name="GPT-4o",
            context_window=128000,
            max_output_tokens=16384,
            capabilities=["chat", "function_calling", "vision"],
            pricing={"input": 0.0025, "output": 0.01},
        )
        registry.add_model(
            id="claude-3-opus",
            provider="anthropic",
            display_name="Claude 3 Opus",
            context_window=200000,
            max_output_tokens=4096,
            capabilities=["chat", "function_calling", "vision"],
            pricing={"input": 0.015, "output": 0.075},
        )
        registry.add_model(
            id="gpt-3.5-turbo",
            provider="openai",
            display_name="GPT-3.5 Turbo",
            context_window=16385,
            max_output_tokens=4096,
            capabilities=["chat", "function_calling"],
            pricing={"input": 0.0005, "output": 0.0015},
        )

        cb_registry = CircuitBreakerRegistry()
        rate_limiter = RateLimiter(redis=test_redis)

        gateway = GatewayRouter(
            model_registry=registry,
            circuit_breaker_registry=cb_registry,
            rate_limiter=rate_limiter,
            redis=test_redis,
        )

        # Mock the provider adapter
        mock_adapter = AsyncMock()
        mock_adapter.complete = AsyncMock(return_value={
            "content": "Mocked LLM response",
            "finish_reason": "stop",
            "provider": "openai",
            "output_tokens": 50,
            "cost_usd": 0.001,
            "cached_tokens": 0,
            "tool_calls": None,
        })
        mock_adapter.stream_complete = AsyncMock(return_value=AsyncMock())
        mock_adapter.health_check = AsyncMock(return_value=True)
        gateway._adapters = {"openai": mock_adapter, "anthropic": mock_adapter}

        return gateway

    @pytest.mark.asyncio
    async def test_route_basic_completion(self, gateway_setup):
        """Test basic chat completion routing."""
        result = await gateway_setup.route(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Hello"}],
            temperature=0.7,
            max_tokens=100,
            tenant_id="test-tenant",
        )
        assert "content" in result
        assert result.get("provider", "")

    @pytest.mark.asyncio
    async def test_route_to_specific_provider(self, gateway_setup):
        """Test routing to a specific provider's model."""
        result = await gateway_setup.route(
            model="claude-3-opus",
            messages=[{"role": "user", "content": "Test"}],
            tenant_id="test-tenant",
        )
        assert result.get("provider") == "openai"  # Mock adapter is shared

    @pytest.mark.asyncio
    async def test_list_models(self, gateway_setup):
        """Test listing available models."""
        models = await gateway_setup.list_models(tenant_id="test-tenant")
        assert len(models) == 3
        model_ids = [m.id for m in models]
        assert "gpt-4o" in model_ids
        assert "claude-3-opus" in model_ids
        assert "gpt-3.5-turbo" in model_ids

    @pytest.mark.asyncio
    async def test_health_check(self, gateway_setup):
        """Test gateway health check endpoint."""
        health = await gateway_setup.health_check()
        assert "status" in health
        assert "providers" in health or health["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_route_with_tools(self, gateway_setup):
        """Test routing a request with tool definitions."""
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get current weather",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {"type": "string"},
                        },
                    },
                },
            }
        ]

        result = await gateway_setup.route(
            model="gpt-4o",
            messages=[{"role": "user", "content": "What's the weather?"}],
            tools=tools,
            tenant_id="test-tenant",
        )
        assert "content" in result

    @pytest.mark.asyncio
    async def test_route_invalid_model(self, gateway_setup):
        """Test routing to an invalid model raises an error."""
        with pytest.raises(ValueError, match="not found"):
            await gateway_setup.route(
                model="nonexistent-model",
                messages=[{"role": "user", "content": "Test"}],
                tenant_id="test-tenant",
            )

    @pytest.mark.asyncio
    async def test_model_routing_preference(self, gateway_setup):
        """Test that gateway respects model preferences."""
        # GPT-3.5-turbo should be routed to openai
        result = await gateway_setup.route(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": "Test"}],
            tenant_id="test-tenant",
        )
        assert result.get("provider") == "openai"
