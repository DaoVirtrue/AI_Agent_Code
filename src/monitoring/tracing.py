"""OpenTelemetry distributed tracing setup for LLM call observability."""

import os
import time
import functools
from contextlib import contextmanager
from typing import Optional

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.trace import SpanKind, Status, StatusCode, Tracer

_tracer: Optional[Tracer] = None
_tracer_provider: Optional[TracerProvider] = None


def setup_tracing(
    service_name: str = "llm-platform",
    endpoint: Optional[str] = None,
    sample_rate: float = 1.0,
) -> None:
    """Initialize OpenTelemetry tracing.

    Configures the tracer provider with:
    - OTLP gRPC exporter (if endpoint provided)
    - Console exporter (for development)
    - Batch span processor for performance

    Args:
        service_name: Name of this service (used in trace metadata).
        endpoint: OTLP collector endpoint URL (e.g., "http://jaeger:4317").
        sample_rate: Fraction of traces to sample (0.0 to 1.0).
    """
    global _tracer, _tracer_provider

    resource = Resource.create({SERVICE_NAME: service_name})

    _tracer_provider = TracerProvider(resource=resource)

    # Always add console exporter for development visibility
    console_exporter = ConsoleSpanExporter()
    _tracer_provider.add_span_processor(
        BatchSpanProcessor(console_exporter)
    )

    # Add OTLP exporter if endpoint is configured
    if endpoint:
        try:
            otlp_exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
            _tracer_provider.add_span_processor(
                BatchSpanProcessor(otlp_exporter)
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                "Failed to configure OTLP exporter: %s", e
            )

    trace.set_tracer_provider(_tracer_provider)
    _tracer = _tracer_provider.get_tracer(service_name)


def get_tracer() -> Tracer:
    """Get the configured OpenTelemetry tracer.

    Returns:
        An OpenTelemetry Tracer instance. If tracing is not configured,
        returns the global default tracer.

    Raises:
        RuntimeError: If setup_tracing() has not been called.
    """
    global _tracer
    if _tracer is None:
        # Auto-initialize with defaults if not explicitly configured
        setup_tracing(
            service_name=os.getenv("OTEL_SERVICE_NAME", "llm-platform"),
            endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"),
        )
    return _tracer


@contextmanager
def trace_llm_call(
    provider: str,
    model: str,
    operation: str = "completion",
    tenant_id: Optional[str] = None,
):
    """Context manager to trace an LLM API call.

    Creates a span with LLM-specific attributes for observability.

    Usage:
        with trace_llm_call("openai", "gpt-4o", "completion") as span:
            result = await openai_client.chat.completions.create(...)
            span.set_attribute("llm.tokens.input", result.usage.prompt_tokens)
            span.set_attribute("llm.tokens.output", result.usage.completion_tokens)

    Args:
        provider: LLM provider name (e.g., "openai", "anthropic").
        model: Model identifier (e.g., "gpt-4o").
        operation: Type of operation (completion, embedding, etc.).
        tenant_id: Tenant identifier for attribution.

    Yields:
        An OpenTelemetry Span with pre-populated LLM attributes.
    """
    tracer = get_tracer()
    span_name = f"llm.{operation}"

    attributes = {
        "llm.provider": provider,
        "llm.model": model,
        "llm.operation": operation,
    }

    if tenant_id:
        attributes["tenant.id"] = tenant_id

    with tracer.start_as_current_span(
        span_name,
        kind=SpanKind.CLIENT,
        attributes=attributes,
    ) as span:
        start_time = time.monotonic()

        try:
            yield span
            span.set_status(Status(StatusCode.OK))
        except Exception as e:
            span.set_status(
                Status(StatusCode.ERROR, str(e))
            )
            span.record_exception(e)
            raise
        finally:
            elapsed_ms = (time.monotonic() - start_time) * 1000
            span.set_attribute("llm.latency_ms", elapsed_ms)


def trace_decorator(
    provider: str,
    model: str,
    operation: str = "completion",
):
    """Decorator version of trace_llm_call.

    Usage:
        @trace_decorator("openai", "gpt-4o", "completion")
        async def my_llm_function():
            ...
    """
    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            with trace_llm_call(provider, model, operation) as span:
                span.set_attribute("code.function", func.__name__)
                return await func(*args, **kwargs)

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            with trace_llm_call(provider, model, operation) as span:
                span.set_attribute("code.function", func.__name__)
                return func(*args, **kwargs)

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def add_span_event(name: str, attributes: Optional[dict] = None):
    """Add an event to the current active span.

    Args:
        name: Event name (e.g., "cache.hit", "failover.triggered").
        attributes: Optional key-value pairs for the event.
    """
    current_span = trace.get_current_span()
    if current_span and current_span.is_recording():
        current_span.add_event(name, attributes=attributes)


def set_span_attribute(key: str, value):
    """Set an attribute on the current active span.

    Args:
        key: Attribute name.
        value: Attribute value (str, int, float, bool).
    """
    current_span = trace.get_current_span()
    if current_span and current_span.is_recording():
        current_span.set_attribute(key, value)


class TraceContextManager:
    """Generic context manager for creating scoped spans.

    Usage:
        with TraceContextManager("rag.retrieval", top_k=10) as span:
            results = await retrieve(query)
            span.set_attribute("rag.chunks_found", len(results))
    """

    def __init__(self, span_name: str, **attributes):
        self.span_name = span_name
        self.attributes = attributes
        self._span = None

    def __enter__(self):
        tracer = get_tracer()
        self._span = tracer.start_span(
            self.span_name,
            kind=SpanKind.INTERNAL,
            attributes=self.attributes,
        )
        self._span.__enter__()
        return self._span

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._span:
            if exc_type:
                self._span.set_status(
                    Status(StatusCode.ERROR, str(exc_val))
                )
                self._span.record_exception(exc_val)
            else:
                self._span.set_status(Status(StatusCode.OK))
            self._span.__exit__(exc_type, exc_val, exc_tb)
        return False

    async def __aenter__(self):
        return self.__enter__()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return self.__exit__(exc_type, exc_val, exc_tb)
