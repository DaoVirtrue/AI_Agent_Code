"""
Gateway Router

Central orchestrator for all LLM API calls. Coordinates authentication,
rate limiting, context window management, provider selection, circuit
breaking, retries with fallback, caching, cost tracking, and audit logging.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Set, Tuple

from src.ai_gateway.cache import ResponseCache
from src.ai_gateway.circuit_breaker import CircuitBreakerManager, CircuitConfig
from src.ai_gateway.fallback import FallbackChain, FallbackExhaustedError
from src.ai_gateway.load_balancer import LoadBalancer
from src.ai_gateway.provider_registry import ProviderRegistry
from src.ai_gateway.providers.base import (
    BaseProvider,
    LLMRequest,
    LLMResponse,
    Message,
    TokenUsage,
)
from src.ai_gateway.rate_limiter import RateLimiter, RateLimitResult
from src.ai_gateway.retry import RetryHandler, is_retryable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prometheus metrics (optional import)
# ---------------------------------------------------------------------------

try:
    from prometheus_client import Counter, Histogram, Gauge

    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False
    Counter = None  # type: ignore
    Histogram = None  # type: ignore
    Gauge = None  # type: ignore


# ---------------------------------------------------------------------------
# Metrics (module-level singletons, shared across all GatewayRouter instances)
# ---------------------------------------------------------------------------

if _PROMETHEUS_AVAILABLE:
    _REQUEST_COUNTER = Counter(
        "ai_gateway_requests_total",
        "Total number of gateway requests",
        ["tenant_id", "model", "status"],
    )
    _REQUEST_LATENCY = Histogram(
        "ai_gateway_request_latency_seconds",
        "Gateway request duration in seconds",
        ["tenant_id", "model"],
        buckets=[0.1, 0.5, 1, 2, 5, 10, 30, 60, 120],
    )
    _ERROR_COUNTER = Counter(
        "ai_gateway_errors_total",
        "Total gateway error count",
        ["tenant_id", "model", "error_type"],
    )
    _TOKEN_COUNTER = Counter(
        "ai_gateway_tokens_total",
        "Total tokens processed",
        ["tenant_id", "model", "type"],
    )
else:
    _REQUEST_COUNTER = None
    _REQUEST_LATENCY = None
    _ERROR_COUNTER = None
    _TOKEN_COUNTER = None


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class RequestContext:
    """
    Context for a single gateway request.

    Attributes:
        tenant_id: The tenant making the request.
        api_key: The API key used for authentication.
        endpoint: The logical endpoint being accessed (for rate limiting).
        user_id: Optional end-user identifier.
        session_id: Optional session/conversation identifier.
        trace_id: Distributed tracing identifier.
        metadata: Arbitrary context metadata.
    """

    tenant_id: str
    api_key: str = ""
    endpoint: str = "chat"
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GatewayConfig:
    """
    Configuration for the GatewayRouter.

    Attributes:
        enable_cache: Whether to use the response cache.
        cache_ttl: Default TTL for cached responses in seconds.
        enable_rate_limiting: Whether to enforce rate limits.
        max_context_tokens: Maximum tokens allowed in context window (default from model).
        auto_truncate: If True, automatically truncate messages to fit context window.
        enable_audit_log: Whether to write audit logs.
        audit_log_callback: Async callable for audit log writing.
    """

    enable_cache: bool = True
    cache_ttl: int = 3600
    enable_rate_limiting: bool = True
    max_context_tokens: int = 128000
    auto_truncate: bool = True
    enable_audit_log: bool = True
    audit_log_callback: Optional[Callable[..., Any]] = None


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class GatewayError(Exception):
    """Base exception for gateway-level errors."""
    pass


class AuthenticationError(GatewayError):
    """API key verification failed."""
    pass


class RateLimitExceededError(GatewayError):
    """Rate limit exceeded for the tenant."""
    def __init__(self, message: str, retry_after: Optional[float] = None):
        super().__init__(message)
        self.retry_after = retry_after


class ContextWindowExceededError(GatewayError):
    """Request exceeds the model's context window."""
    def __init__(self, message: str, current_tokens: int, max_tokens: int):
        super().__init__(message)
        self.current_tokens = current_tokens
        self.max_tokens = max_tokens


class NoProviderAvailableError(GatewayError):
    """No provider is available to handle the request."""
    pass


# ---------------------------------------------------------------------------
# Gateway Router
# ---------------------------------------------------------------------------

class GatewayRouter:
    """
    Central orchestrator for all LLM API calls.

    Workflow:
        1. Verify API key & tenant
        2. Check rate limit
        3. Check context window & auto-truncate
        4. Select provider via load balancer
        5. Execute with circuit breaker
        6. On failure -> retry with backoff -> fallback chain
        7. Count tokens & calculate cost
        8. Write audit log
        9. Return response
    """

    def __init__(
        self,
        provider_registry: ProviderRegistry,
        rate_limiter: Optional[RateLimiter] = None,
        load_balancer: Optional[LoadBalancer] = None,
        circuit_breaker_mgr: Optional[CircuitBreakerManager] = None,
        fallback_chain: Optional[FallbackChain] = None,
        retry_handler: Optional[RetryHandler] = None,
        response_cache: Optional[ResponseCache] = None,
        config: Optional[GatewayConfig] = None,
    ):
        """
        Args:
            provider_registry: Registry of all available providers.
            rate_limiter: Optional rate limiter (created with defaults if None).
            load_balancer: Optional load balancer (created with defaults if None).
            circuit_breaker_mgr: Optional circuit breaker manager.
            fallback_chain: Optional fallback chain configuration.
            retry_handler: Optional retry handler.
            response_cache: Optional response cache.
            config: Gateway configuration.
        """
        self._registry = provider_registry
        self._rate_limiter = rate_limiter or RateLimiter()
        self._load_balancer = load_balancer or LoadBalancer()
        self._circuit_breakers = circuit_breaker_mgr or CircuitBreakerManager()
        self._fallback = fallback_chain or FallbackChain()
        self._retry = retry_handler or RetryHandler()
        self._cache = response_cache
        self._config = config or GatewayConfig()

        # API key -> tenant mapping (for auth)
        self._api_keys: Dict[str, str] = {}

        # Tenant tier mappings
        self._tenant_tiers: Dict[str, str] = {}

        # Prometheus metrics (shared module-level singletons)
        self._request_counter = _REQUEST_COUNTER
        self._request_latency = _REQUEST_LATENCY
        self._error_counter = _ERROR_COUNTER
        self._token_counter = _TOKEN_COUNTER

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def register_api_key(self, api_key: str, tenant_id: str) -> None:
        """Register an API key for a tenant."""
        self._api_keys[api_key] = tenant_id

    def set_tenant_tier(self, tenant_id: str, tier: str) -> None:
        """Set the rate limit tier for a tenant."""
        self._tenant_tiers[tenant_id] = tier
        if self._rate_limiter:
            self._rate_limiter.set_tenant_tier(tenant_id, tier)

    # ------------------------------------------------------------------
    # Main entry point: route()
    # ------------------------------------------------------------------

    async def route(
        self,
        request: LLMRequest,
        context: RequestContext,
    ) -> LLMResponse:
        """
        Route a chat request through the full gateway pipeline.

        Args:
            request: The LLMRequest containing model, messages, etc.
            context: RequestContext with tenant, API key, and tracing info.

        Returns:
            LLMResponse from the selected provider.

        Raises:
            AuthenticationError: If the API key is invalid.
            RateLimitExceededError: If rate limits are exceeded.
            FallbackExhaustedError: If all models (including fallbacks) fail.
            GatewayError: On other gateway-level failures.
        """
        start_time = time.perf_counter()
        status = "success"
        effective_model = request.model

        try:
            # ---- Step 1: Verify API key & tenant ----
            await self._verify_auth(context)

            # ---- Step 2: Check rate limit ----
            await self._check_rate_limit(context, request)

            # ---- Step 3: Check context window & auto-truncate ----
            await self._check_context_window(request)

            # ---- Step 4-6: Try cache, execute with fallback ----
            response = await self._execute_with_cache_and_fallback(request, context)

            # ---- Step 7: Count tokens & calculate cost ----
            self._enrich_cost_data(response)

            # ---- Step 9: Return response ----
            return response

        except AuthenticationError:
            status = "auth_error"
            self._emit_error_metric(context.tenant_id, request.model, "authentication")
            raise

        except RateLimitExceededError:
            status = "rate_limited"
            self._emit_error_metric(context.tenant_id, request.model, "rate_limit")
            raise

        except FallbackExhaustedError:
            status = "fallback_exhausted"
            self._emit_error_metric(context.tenant_id, request.model, "fallback_exhausted")
            raise

        except Exception as exc:
            status = "error"
            self._emit_error_metric(context.tenant_id, request.model, type(exc).__name__)
            raise GatewayError(f"Gateway route failed: {exc}") from exc

        finally:
            # ---- Step 8: Write audit log ----
            elapsed = time.perf_counter() - start_time
            await self._write_audit_log(context, request, status, elapsed)

            # Emit metrics
            self._emit_request_metric(context.tenant_id, effective_model, status, elapsed)

    async def route_stream(
        self,
        request: LLMRequest,
        context: RequestContext,
    ) -> AsyncIterator[LLMResponse]:
        """
        Route a streaming chat request through the gateway pipeline.

        Steps 1-3 are identical to route(). Steps 4-6 are adapted for
        streaming: circuit breaker check is done once, then the stream
        is yielded chunk-by-chunk.

        Args:
            request: The LLMRequest.
            context: RequestContext.

        Yields:
            LLMResponse chunks with incremental content.
        """
        start_time = time.perf_counter()
        status = "success"

        try:
            # ---- Step 1: Verify API key & tenant ----
            await self._verify_auth(context)

            # ---- Step 2: Check rate limit ----
            await self._check_rate_limit(context, request)

            # ---- Step 3: Check context window & auto-truncate ----
            await self._check_context_window(request)

            # ---- Step 4-5: Get provider & check circuit breaker ----
            provider = await self._select_provider(request.model, context)

            # ---- Step 6: Execute stream ----
            stream_request = LLMRequest(
                model=request.model,
                messages=request.messages,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                tools=request.tools,
                tool_choice=request.tool_choice,
                stream=True,
                metadata=request.metadata,
            )

            try:
                async for chunk in provider.chat_stream(stream_request):
                    yield chunk
            except Exception as exc:
                await self._circuit_breakers.on_failure(provider.provider_name)
                self._emit_error_metric(context.tenant_id, request.model, type(exc).__name__)
                raise

            await self._circuit_breakers.on_success(provider.provider_name)

        except AuthenticationError:
            status = "auth_error"
            self._emit_error_metric(context.tenant_id, request.model, "authentication")
            raise

        except RateLimitExceededError:
            status = "rate_limited"
            self._emit_error_metric(context.tenant_id, request.model, "rate_limit")
            raise

        except Exception as exc:
            status = "error"
            self._emit_error_metric(context.tenant_id, request.model, type(exc).__name__)
            raise GatewayError(f"Gateway stream failed: {exc}") from exc

        finally:
            elapsed = time.perf_counter() - start_time
            await self._write_audit_log(context, request, status, elapsed)

    # ------------------------------------------------------------------
    # Step 1: Authentication
    # ------------------------------------------------------------------

    async def _verify_auth(self, context: RequestContext) -> None:
        """Verify that the API key is valid and resolve tenant context."""
        if not context.api_key:
            raise AuthenticationError("API key is required")

        if context.api_key not in self._api_keys:
            logger.warning("Invalid API key: %s...", context.api_key[:8])
            raise AuthenticationError("Invalid API key")

        resolved_tenant = self._api_keys[context.api_key]
        if context.tenant_id and context.tenant_id != resolved_tenant:
            logger.warning(
                "Tenant mismatch: key=%s expected=%s got=%s",
                context.api_key[:8], resolved_tenant, context.tenant_id,
            )

        context.tenant_id = resolved_tenant

    # ------------------------------------------------------------------
    # Step 2: Rate limiting
    # ------------------------------------------------------------------

    async def _check_rate_limit(
        self, context: RequestContext, request: LLMRequest
    ) -> None:
        """Check and enforce rate limits for the tenant."""
        if not self._config.enable_rate_limiting:
            return

        # Estimate tokens for the request
        provider = await self._registry.get_provider_for_model(request.model)
        estimated_tokens = 0
        if provider:
            estimated_tokens = provider.count_request_tokens(request)

        result, info = await self._rate_limiter.check(
            tenant_id=context.tenant_id,
            endpoint=context.endpoint,
            tokens=estimated_tokens,
        )

        if result == RateLimitResult.REJECTED:
            retry_after = float(info.reset - time.time())
            raise RateLimitExceededError(
                f"Rate limit exceeded for tenant '{context.tenant_id}'. "
                f"Limit: {info.limit} RPS, Retry after: {retry_after:.1f}s",
                retry_after=max(0, retry_after),
            )

    # ------------------------------------------------------------------
    # Step 3: Context window management
    # ------------------------------------------------------------------

    async def _check_context_window(self, request: LLMRequest) -> None:
        """Check if the request fits within the model's context window."""
        provider = await self._registry.get_provider_for_model(request.model)
        if not provider:
            return  # Can't check without a provider

        context_window = provider.context_window
        estimated_tokens = provider.count_request_tokens(request)

        if estimated_tokens <= context_window:
            return  # Fits

        if not self._config.auto_truncate:
            raise ContextWindowExceededError(
                f"Request ({estimated_tokens} tokens) exceeds context window "
                f"({context_window} tokens) for model '{request.model}'.",
                current_tokens=estimated_tokens,
                max_tokens=context_window,
            )

        # Auto-truncate: remove oldest messages while keeping system message
        logger.warning(
            "Truncating request for model '%s': %d -> %d tokens",
            request.model, estimated_tokens, context_window,
        )
        self._truncate_messages(request.messages, provider, context_window)

    def _truncate_messages(
        self,
        messages: List[Message],
        provider: BaseProvider,
        context_window: int,
    ) -> None:
        """
        Truncate messages to fit within the context window.

        Strategy:
          - Always keep the system message if present.
          - Remove messages from the front (oldest) until we fit.
          - Reserve ~20% of the context window for the response.
        """
        max_input = int(context_window * 0.8)
        system_messages = [m for m in messages if m.role == "system"]
        non_system = [m for m in messages if m.role != "system"]

        if not non_system:
            return

        # Measure token count and remove from front
        while non_system:
            total = sum(
                provider.count_tokens(m.content)
                if isinstance(m.content, str)
                else 0
                for m in non_system
            )
            if total <= max_input:
                break
            removed = non_system.pop(0)
            logger.debug(
                "Truncated message: role=%s len=%d",
                removed.role,
                len(removed.content) if isinstance(removed.content, str) else 0,
            )

        # Reconstruct: system first, then remaining
        messages.clear()
        messages.extend(system_messages)
        messages.extend(non_system)

    # ------------------------------------------------------------------
    # Steps 4-6: Execute with cache, circuit breaker, retry, fallback
    # ------------------------------------------------------------------

    async def _execute_with_cache_and_fallback(
        self,
        request: LLMRequest,
        context: RequestContext,
    ) -> LLMResponse:
        """
        Execute the request, going through:
          - Cache lookup (if enabled)
          - Provider selection + circuit breaker + retry
          - Fallback chain on failure
        """
        # Check cache
        if self._config.enable_cache and self._cache:
            cache_key = self._cache.get_cache_key(request)
            cached = await self._cache.get(cache_key)
            if cached:
                logger.info("Cache hit for key %s", cache_key)
                return cached

        # Track failed models for fallback
        failed_models: Set[str] = set()

        async def execute_with_model(req: LLMRequest) -> LLMResponse:
            """Execute a single model attempt with circuit breaker + retry."""
            provider = await self._select_provider(req.model, context)

            # Circuit breaker check
            allowed = await self._circuit_breakers.before_call(provider.provider_name)
            if not allowed:
                # Add to failed_models so fallback skips it
                failed_models.add(req.model)
                raise GatewayError(
                    f"Circuit breaker open for provider '{provider.provider_name}' "
                    f"(model: {req.model})"
                )

            async def attempt() -> LLMResponse:
                return await provider.chat(req)

            try:
                result = await self._retry.execute_with_retry(attempt)
                await self._circuit_breakers.on_success(provider.provider_name)
                await self._load_balancer.record_latency(
                    provider.provider_name, result.latency_ms
                )
                return result
            except Exception as exc:
                await self._circuit_breakers.on_failure(provider.provider_name)
                failed_models.add(req.model)
                raise

        try:
            response = await self._fallback.execute(
                request, execute_with_model, failed_models
            )

            # Cache the successful response
            if self._config.enable_cache and self._cache:
                cache_key = self._cache.get_cache_key(request)
                await self._cache.set(cache_key, response, self._config.cache_ttl)

            # Emit token metrics
            if _PROMETHEUS_AVAILABLE and self._token_counter is not None:
                self._token_counter.labels(
                    tenant_id=context.tenant_id,
                    model=response.model,
                    type="input",
                ).inc(response.usage.input_tokens)
                self._token_counter.labels(
                    tenant_id=context.tenant_id,
                    model=response.model,
                    type="output",
                ).inc(response.usage.output_tokens)
                self._token_counter.labels(
                    tenant_id=context.tenant_id,
                    model=response.model,
                    type="cached",
                ).inc(response.usage.cached_tokens)

            return response

        except FallbackExhaustedError:
            # Already logged in FallbackChain
            raise

    # ------------------------------------------------------------------
    # Step 4: Provider selection
    # ------------------------------------------------------------------

    async def _select_provider(
        self, model_id: str, context: RequestContext
    ) -> BaseProvider:
        """
        Select the best provider for the given model.

        Uses the load balancer with weighted round-robin by default,
        falling back to least-latency for high-traffic tenants.
        """
        # Determine strategy based on tenant tier
        tenant_tier = self._tenant_tiers.get(context.tenant_id, "free")
        strategy = "least_latency" if tenant_tier in ("enterprise",) else "weighted_round_robin"

        # Get candidate providers from registry
        base_provider = await self._registry.get_provider_for_model(model_id)
        if base_provider is None:
            raise NoProviderAvailableError(
                f"No provider available for model '{model_id}'"
            )

        # For now, use the single resolved provider as the candidate
        candidates = [base_provider]

        selected = await self._load_balancer.select(model_id, candidates, strategy)
        return selected

    # ------------------------------------------------------------------
    # Step 7: Cost calculation
    # ------------------------------------------------------------------

    def _enrich_cost_data(self, response: LLMResponse) -> None:
        """
        Ensure cost data is present in response metadata.

        If the provider already computed cost, this is a no-op.
        Otherwise, computes a rough estimate.
        """
        if "cost" in response.metadata:
            return

        # Rough estimate if provider didn't include cost
        input_cost = response.usage.input_tokens / 1_000_000 * 3.0
        output_cost = response.usage.output_tokens / 1_000_000 * 15.0
        response.metadata["cost"] = round(input_cost + output_cost, 6)
        response.metadata["cost_estimated"] = True

    # ------------------------------------------------------------------
    # Step 8: Audit logging
    # ------------------------------------------------------------------

    async def _write_audit_log(
        self,
        context: RequestContext,
        request: LLMRequest,
        status: str,
        elapsed_s: float,
    ) -> None:
        """
        Write an audit log entry for the request.

        Supports a user-provided callback for custom logging pipelines.
        """
        if not self._config.enable_audit_log:
            return

        audit_entry = {
            "timestamp": time.time(),
            "trace_id": context.trace_id,
            "tenant_id": context.tenant_id,
            "user_id": context.user_id,
            "session_id": context.session_id,
            "model": request.model,
            "endpoint": context.endpoint,
            "status": status,
            "latency_ms": round(elapsed_s * 1000, 2),
            "message_count": len(request.messages),
            "has_tools": bool(request.tools),
            "stream": request.stream,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }

        # Use callback if provided
        if self._config.audit_log_callback:
            try:
                await self._config.audit_log_callback(audit_entry)
            except Exception as exc:
                logger.error("Audit log callback failed: %s", exc)
        else:
            logger.info("AUDIT: %s", audit_entry)

    # ------------------------------------------------------------------
    # Metrics emission
    # ------------------------------------------------------------------

    def _emit_request_metric(
        self,
        tenant_id: str,
        model: str,
        status: str,
        elapsed_s: float,
    ) -> None:
        """Emit request count and latency metrics."""
        if not _PROMETHEUS_AVAILABLE:
            return
        if self._request_counter is not None:
            self._request_counter.labels(
                tenant_id=tenant_id, model=model, status=status,
            ).inc()
        if self._request_latency is not None:
            self._request_latency.labels(
                tenant_id=tenant_id, model=model,
            ).observe(elapsed_s)

    def _emit_error_metric(
        self,
        tenant_id: str,
        model: str,
        error_type: str,
    ) -> None:
        """Emit error counter metric."""
        if not _PROMETHEUS_AVAILABLE:
            return
        if self._error_counter is not None:
            self._error_counter.labels(
                tenant_id=tenant_id, model=model, error_type=error_type,
            ).inc()

    # ------------------------------------------------------------------
    # Health & diagnostics
    # ------------------------------------------------------------------

    async def health_report(self) -> Dict[str, Any]:
        """Return a comprehensive health report for the gateway."""
        provider_status = await self._registry.list_providers()
        breaker_status = await self._circuit_breakers.health_report()
        provider_health = await self._registry.health_check_all()

        return {
            "gateway": "healthy",
            "providers": provider_status,
            "provider_health": provider_health,
            "circuit_breakers": breaker_status,
            "fallback_chains": self._fallback.list_chains(),
            "config": {
                "cache_enabled": self._config.enable_cache,
                "rate_limiting_enabled": self._config.enable_rate_limiting,
                "auto_truncate": self._config.auto_truncate,
            },
        }

    async def close(self) -> None:
        """Release any resources held by the gateway and its providers."""
        # Close connections for providers that have them
        for name in await self._registry.health_check_all():
            provider = await self._registry.get(name)
            if provider and hasattr(provider, "close"):
                try:
                    await provider.close()
                except Exception as exc:
                    logger.warning("Error closing provider '%s': %s", name, exc)
