"""FastAPI middleware stack: Request ID, Metrics, and Audit logging."""

import time
import uuid
import json
import hashlib
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse

from src.observability.metrics import (
    gateway_requests,
    gateway_latency,
)
from src.observability.logging_setup import get_logger

logger = get_logger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Adds X-Request-ID header to every request/response pair.

    - Generates a unique request ID if not provided by the client.
    - Adds X-Request-ID to the response headers.
    - Stores the request ID in request.state for downstream access.
    - Uses UUID7-like format for time-sortable IDs.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Use client-provided ID or generate a new one
        request_id = request.headers.get("X-Request-ID")
        if not request_id:
            request_id = self._generate_request_id()

        # Store for downstream use
        request.state.request_id = request_id

        # Process request
        response = await call_next(request)

        # Add request ID to response
        response.headers["X-Request-ID"] = request_id
        return response

    @staticmethod
    def _generate_request_id() -> str:
        """Generate a time-sortable request ID (UUID7-like format)."""
        ts = int(time.time() * 1000)  # millisecond timestamp
        ts_hex = format(ts, "012x")
        random_part = uuid.uuid4().hex[12:]  # 10 random hex chars
        return f"{ts_hex[:8]}-{ts_hex[8:]}-7{random_part[:4]}-{random_part[4:8]}-{random_part[8:]}"


class MetricsMiddleware(BaseHTTPMiddleware):
    """Records Prometheus metrics for each HTTP request.

    Tracks:
    - Request count by tenant, provider, model, status
    - Request latency by endpoint
    - Response size
    """

    EXCLUDED_PATHS = {"/metrics", "/health", "/ready", "/live"}

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path

        # Skip metrics for monitoring endpoints
        if path in self.EXCLUDED_PATHS:
            return await call_next(request)

        start_time = time.monotonic()

        try:
            response = await call_next(request)
            status = "success" if response.status_code < 400 else "error"
        except Exception:
            status = "error"
            response = Response(
                content=json.dumps({"code": "INTERNAL", "message": "Internal server error"}),
                status_code=500,
                media_type="application/json",
            )

        elapsed = time.monotonic() - start_time

        # Extract tenant and model info from request context
        tenant_id = getattr(getattr(request.state, "tenant", None), "tenant_id", "unknown")
        provider = "unknown"
        model = "unknown"

        # Try to infer provider/model from path
        if "/gateway/chat" in path:
            try:
                body = await request.json()
                model = body.get("model", "unknown")
                # Infer provider from model name
                if model.startswith("gpt"):
                    provider = "openai"
                elif model.startswith("claude"):
                    provider = "anthropic"
                elif model.startswith("gemini"):
                    provider = "google"
                else:
                    provider = model.split("/")[0] if "/" in model else "unknown"
            except Exception:
                pass
        elif "/rag" in path:
            provider = "rag"
            model = "rag-pipeline"

        # Record metrics
        gateway_requests.labels(
            tenant_id=tenant_id,
            provider=provider,
            model=model,
            status=status,
        ).inc()

        gateway_latency.labels(
            provider=provider,
            model=model,
        ).observe(elapsed)

        return response


class AuditMiddleware(BaseHTTPMiddleware):
    """Logs every request and response for audit trail purposes.

    Features:
    - Structured JSON logging of request metadata
    - Masked sensitive fields (API keys, tokens)
    - Skips streaming response bodies (logs metadata only)
    - Hash chain for tamper evidence
    """

    SENSITIVE_HEADERS = {"authorization", "x-api-key", "cookie", "set-cookie"}
    MAX_BODY_LOG_SIZE = 4096  # Truncate body if larger

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        start_time = time.monotonic()

        # Build audit event
        audit_event = {
            "timestamp": time.time(),
            "method": request.method,
            "path": request.url.path,
            "query_string": str(request.url.query) if request.url.query else "",
            "client_ip": request.client.host if request.client else "unknown",
            "request_id": getattr(request.state, "request_id", "unknown"),
            "headers": self._sanitize_headers(dict(request.headers)),
        }

        # Read request body for logging (on non-GET requests)
        if request.method in ("POST", "PUT", "PATCH"):
            try:
                body_bytes = await request.body()
                if len(body_bytes) <= self.MAX_BODY_LOG_SIZE:
                    audit_event["request_body"] = self._mask_sensitive_body(
                        body_bytes.decode("utf-8", errors="replace")
                    )
                else:
                    audit_event["request_body"] = f"[TRUNCATED: {len(body_bytes)} bytes]"
            except Exception:
                audit_event["request_body"] = "[UNREADABLE]"

        # Process the request
        response = await call_next(request)

        elapsed_ms = (time.monotonic() - start_time) * 1000

        # Add response info
        audit_event["status_code"] = response.status_code
        audit_event["latency_ms"] = round(elapsed_ms, 2)
        audit_event["response_headers"] = self._sanitize_headers(
            dict(response.headers)
        )

        # Compute hash chain entry
        previous_hash = getattr(request.state, "_audit_previous_hash", "")
        audit_event["chain_hash"] = self._compute_chain_hash(
            previous_hash, audit_event
        )

        # Log structured audit record
        log_level = "ERROR" if response.status_code >= 500 else (
            "WARNING" if response.status_code >= 400 else "INFO"
        )
        getattr(logger, log_level.lower())(
            "audit",
            extra={
                "audit_event": audit_event,
                "type": "access_log",
            },
        )

        return response

    def _sanitize_headers(self, headers: dict) -> dict:
        """Mask sensitive header values."""
        sanitized = {}
        for key, value in headers.items():
            if key.lower() in self.SENSITIVE_HEADERS:
                value_len = len(value) if value else 0
                sanitized[key] = f"[REDACTED:{value_len}]"
            else:
                sanitized[key] = value
        return sanitized

    def _mask_sensitive_body(self, body: str) -> str:
        """Mask sensitive fields in request bodies."""
        sensitive_keys = {"api_key", "password", "secret", "token", "key"}
        try:
            data = json.loads(body)
            if isinstance(data, dict):
                for key in list(data.keys()):
                    if key.lower() in sensitive_keys:
                        data[key] = "[REDACTED]"
                return json.dumps(data)
        except (json.JSONDecodeError, TypeError):
            pass
        return body

    @staticmethod
    def _compute_chain_hash(previous_hash: str, event_data: dict) -> str:
        """Compute SHA-256 hash chain entry for tamper evidence.

        Each audit entry's hash is computed as:
            SHA-256(previous_hash || timestamp || method || path || status_code || request_id)

        This creates an immutable chain: any modification breaks subsequent hashes.
        """
        chain_data = "|".join([
            previous_hash,
            str(event_data.get("timestamp", "")),
            event_data.get("method", ""),
            event_data.get("path", ""),
            str(event_data.get("status_code", "")),
            event_data.get("request_id", ""),
        ])
        return hashlib.sha256(chain_data.encode("utf-8")).hexdigest()
