"""Monitoring module - Prometheus metrics, OpenTelemetry tracing, logging, and alerts."""

from src.observability.metrics import (
    gateway_requests,
    gateway_latency,
    rag_cache_hits,
    rag_retrieval_latency,
    agent_steps,
    agent_loop_detections,
    token_usage,
    cost_total,
    circuit_breaker_state,
    circuit_breaker_failures,
    ttft_histogram,
    itl_histogram,
    injection_attempts,
    pii_detections,
    get_metrics,
)
from src.observability.logging_setup import setup_logging, get_logger
from src.observability.tracing import setup_tracing, get_tracer, trace_llm_call
from src.observability.health import HealthChecker
from src.observability.audit import AuditLogger

__all__ = [
    # Metrics
    "gateway_requests",
    "gateway_latency",
    "rag_cache_hits",
    "rag_retrieval_latency",
    "agent_steps",
    "agent_loop_detections",
    "token_usage",
    "cost_total",
    "circuit_breaker_state",
    "circuit_breaker_failures",
    "ttft_histogram",
    "itl_histogram",
    "injection_attempts",
    "pii_detections",
    "get_metrics",
    # Logging
    "setup_logging",
    "get_logger",
    # Tracing
    "setup_tracing",
    "get_tracer",
    "trace_llm_call",
    # Health
    "HealthChecker",
    # Audit
    "AuditLogger",
]
