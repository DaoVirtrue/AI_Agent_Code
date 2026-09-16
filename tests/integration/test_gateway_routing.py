"""Integration tests for gateway routing (real GatewayRouter, async interface)."""

import pytest
from unittest.mock import AsyncMock

from src.ai_gateway.gateway import GatewayRouter, GatewayConfig, RequestContext
from src.ai_gateway.providers.base import LLMRequest, Message, LLMResponse, TokenUsage
from src.ai_gateway.provider_registry import ProviderRegistry
from src.ai_gateway.providers.deepseek_provider import DeepSeekProvider


class TestGatewayRouting:
    """Tests for the real GatewayRouter (async)."""

    @pytest.fixture
    def registry(self):
        return ProviderRegistry()

    @pytest.fixture
    def gateway(self, registry):
        return GatewayRouter(
            provider_registry=registry,
            config=GatewayConfig(enable_rate_limiting=False, enable_cache=False),
        )

    @pytest.mark.asyncio
    async def test_route_basic_completion(self, gateway):
        """Route a basic completion with a mocked provider chat."""
        provider = DeepSeekProvider(api_key="test-key")
        await gateway._registry.register("deepseek", provider)
        gateway.register_api_key("test-key", "test-tenant")

        # Mock the provider's chat method
        gateway._registry._providers["deepseek"].chat = AsyncMock(return_value=LLMResponse(
            model="deepseek-chat", content="hi", finish_reason="stop",
            usage=TokenUsage(input_tokens=5, output_tokens=2),
        ))

        request = LLMRequest(
            model="deepseek-chat",
            messages=[Message(role="user", content="Hello")],
        )
        context = RequestContext(tenant_id="test-tenant", api_key="test-key")

        response = await gateway.route(request, context)
        assert response.content == "hi"
        assert response.model == "deepseek-chat"

    @pytest.mark.asyncio
    async def test_auth_required(self, gateway):
        """Missing API key -> AuthenticationError."""
        from src.ai_gateway.gateway import AuthenticationError

        request = LLMRequest(model="deepseek-chat", messages=[Message(role="user", content="hi")])
        context = RequestContext(tenant_id="t1", api_key="")

        with pytest.raises(AuthenticationError):
            await gateway.route(request, context)

    @pytest.mark.asyncio
    async def test_health_report(self, gateway):
        """Health report returns gateway/providers keys."""
        report = await gateway.health_report()
        assert "gateway" in report
        assert "providers" in report
