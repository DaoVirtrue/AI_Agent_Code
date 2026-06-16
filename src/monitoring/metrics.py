"""Prometheus metrics definitions for LLM Platform observability."""

from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    CollectorRegistry,
    REGISTRY,
)

# --- Gateway Metrics ---

gateway_requests = Counter(
    "gateway_requests_total",
    "Total number of gateway requests processed",
    ["tenant_id", "provider", "model", "status"],
)

gateway_latency = Histogram(
    "gateway_latency_seconds",
    "Gateway request latency in seconds",
    ["provider", "model"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
)

# --- RAG Metrics ---

rag_cache_hits = Counter(
    "rag_cache_hits_total",
    "Total number of RAG cache hits",
    ["level"],  # level: exact, semantic, none
)

rag_retrieval_latency = Histogram(
    "rag_retrieval_latency_seconds",
    "RAG retrieval latency in seconds",
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0],
)

rag_chunks_retrieved = Histogram(
    "rag_chunks_retrieved",
    "Number of chunks retrieved per query",
    buckets=[1, 3, 5, 10, 20, 50, 100],
)

rag_index_latency = Histogram(
    "rag_index_latency_seconds",
    "Document indexing latency in seconds",
    buckets=[0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 120.0],
)

# --- Agent Metrics ---

agent_steps = Histogram(
    "agent_steps",
    "Number of steps taken per agent execution",
    ["agent_type"],
    buckets=[1, 3, 5, 10, 15, 20, 30],
)

agent_loop_detections = Counter(
    "agent_loop_detections_total",
    "Total number of agent loop detections",
    ["agent_type"],
)

agent_execution_time = Histogram(
    "agent_execution_seconds",
    "Total agent execution time in seconds",
    ["agent_type"],
    buckets=[1, 5, 10, 30, 60, 120, 300, 600],
)

agent_tool_calls = Counter(
    "agent_tool_calls_total",
    "Total number of tool calls made by agents",
    ["agent_type", "tool_name"],
)

# --- Token/Cost Metrics ---

token_usage = Counter(
    "token_usage_total",
    "Total tokens consumed",
    ["tenant_id", "provider", "model", "type"],  # type: input, output, cached
)

cost_total = Counter(
    "cost_total_usd",
    "Total cost in USD",
    ["tenant_id", "provider", "model"],
)

# --- Circuit Breaker Metrics ---

circuit_breaker_state = Gauge(
    "circuit_breaker_state",
    "Circuit breaker state: 0=CLOSED, 1=OPEN, 2=HALF_OPEN",
    ["name"],
)

circuit_breaker_failures = Counter(
    "circuit_breaker_failures_total",
    "Total number of circuit breaker failure events",
    ["name"],
)

circuit_breaker_transitions = Counter(
    "circuit_breaker_transitions_total",
    "Total number of circuit breaker state transitions",
    ["name", "from_state", "to_state"],
)

# --- Streaming Metrics ---

ttft_histogram = Histogram(
    "ttft_seconds",
    "Time to first token in seconds",
    buckets=[0.01, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0],
)

itl_histogram = Histogram(
    "itl_seconds",
    "Inter-token latency in seconds",
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5],
)

streaming_chunks = Counter(
    "streaming_chunks_total",
    "Total number of streaming chunks sent",
    ["provider", "model"],
)

# --- Rate Limiter Metrics ---

rate_limit_hits = Counter(
    "rate_limit_hits_total",
    "Total number of rate limit rejections",
    ["tenant_id", "limit_type"],  # limit_type: rpm, tpm, concurrent
)

rate_limit_current = Gauge(
    "rate_limit_current",
    "Current rate limit usage",
    ["tenant_id", "limit_type"],
)

# --- Security Metrics ---

injection_attempts = Counter(
    "injection_attempts_total",
    "Total number of injection attempts detected",
    ["severity"],  # severity: low, medium, high, critical
)

pii_detections = Counter(
    "pii_detections_total",
    "Total number of PII patterns detected",
    ["type"],  # type: email, phone, ssn, credit_card, ip, address
)

content_safety_blocks = Counter(
    "content_safety_blocks_total",
    "Total number of content safety blocks",
    ["category"],  # category: hate, harassment, violence, self-harm, sexual
)

# --- API Server Metrics ---

http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
)

http_request_duration = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

http_requests_in_progress = Gauge(
    "http_requests_in_progress",
    "Number of HTTP requests currently being processed",
    ["method"],
)

# --- System Metrics ---

db_connection_pool_size = Gauge(
    "db_connection_pool_size",
    "Current database connection pool size",
)

redis_connection_pool_size = Gauge(
    "redis_connection_pool_size",
    "Current Redis connection pool size",
)

active_websocket_connections = Gauge(
    "active_websocket_connections",
    "Number of active WebSocket connections",
)


class PrometheusMiddleware:
    """FastAPI middleware to automatically record HTTP request metrics.

    Records:
    - Request count per method/endpoint/status
    - Request duration histogram
    - In-progress request gauge
    """

    async def __call__(self, request, call_next):
        from starlette.requests import Request

        method = request.method
        # Simplify endpoint path for cardinality control
        endpoint = self._normalize_path(request.url.path)

        http_requests_in_progress.labels(method=method).inc()

        import time
        start_time = time.monotonic()

        try:
            response = await call_next(request)
            status_code = str(response.status_code)
        except Exception:
            status_code = "500"
            from starlette.responses import Response
            response = Response(status_code=500)

        duration = time.monotonic() - start_time

        http_requests_total.labels(
            method=method,
            endpoint=endpoint,
            status_code=status_code,
        ).inc()

        http_request_duration.labels(
            method=method,
            endpoint=endpoint,
        ).observe(duration)

        http_requests_in_progress.labels(method=method).dec()

        return response

    @staticmethod
    def _normalize_path(path: str) -> str:
        """Normalize URL path to reduce metric cardinality.

        Replaces UUIDs, numeric IDs, and hex strings with placeholders.
        """
        import re

        # Replace UUIDs: 8-4-4-4-12
        path = re.sub(
            r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
            '{id}',
            path,
        )
        # Replace hex IDs
        path = re.sub(r'[0-9a-f]{12,}', '{id}', path)
        # Replace numeric IDs
        path = re.sub(r'/\d+/', '/{id}/', path)
        # Match tenant/doc IDs in path
        path = re.sub(r'/(tenant|doc|run|conv|experiment)-\w+', r'/\1-{id}', path)

        return path


def get_metrics() -> str:
    """Generate the latest Prometheus metrics in text format.

    Returns:
        String containing all registered metrics in Prometheus exposition format.
    """
    return generate_latest(REGISTRY).decode("utf-8")


def reset_metrics():
    """Reset all metrics collectors. Useful for testing."""
    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        try:
            REGISTRY.unregister(collector)
        except KeyError:
            pass
