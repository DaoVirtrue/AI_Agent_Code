"""
Circuit Breaker

Three-state circuit breaker (CLOSED / OPEN / HALF_OPEN) to protect
the system from cascading failures when a provider is degraded.

Exports Prometheus metrics for circuit breaker state and failures.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prometheus metrics (optional import)
# ---------------------------------------------------------------------------

try:
    from prometheus_client import Counter, Gauge

    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False
    Gauge = None  # type: ignore
    Counter = None  # type: ignore


class CircuitState(Enum):
    CLOSED = "closed"           # Normal operation
    OPEN = "open"                # Failing, rejecting requests
    HALF_OPEN = "half_open"     # Testing if the provider has recovered


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class CircuitConfig:
    """
    Configuration for a single circuit breaker.

    Attributes:
        failure_threshold: Number of failures in the window before opening.
        failure_window: Time window in seconds for counting failures.
        timeout: Base timeout in seconds before transitioning OPEN -> HALF_OPEN.
        half_open_max_requests: Max requests allowed in HALF_OPEN state.
        success_threshold: Consecutive successes in HALF_OPEN to close.
        max_timeout: Maximum timeout after exponential backoff.
    """

    failure_threshold: int = 5
    failure_window: float = 60.0
    timeout: float = 30.0
    half_open_max_requests: int = 3
    success_threshold: int = 2
    max_timeout: float = 300.0


# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------

class CircuitBreaker:
    """
    Three-state circuit breaker for a single provider/endpoint.

    State transitions:
        CLOSED --[failures >= threshold]--> OPEN
        OPEN   --[timeout expires]--------> HALF_OPEN
        HALF_OPEN --[successes >= threshold]--> CLOSED
        HALF_OPEN --[any failure]----------> OPEN
    """

    def __init__(
        self,
        name: str,
        config: Optional[CircuitConfig] = None,
    ):
        """
        Args:
            name: Unique identifier for this breaker (typically provider name).
            config: Breaker configuration; uses defaults if None.
        """
        self.name = name
        self.config = config or CircuitConfig()

        self._state: CircuitState = CircuitState.CLOSED
        self._failure_timestamps: List[float] = []
        self._success_count: int = 0
        self._open_count: int = 0
        self._last_state_change: float = time.monotonic()
        self._half_open_allowed: int = 0
        self._lock = asyncio.Lock()

        # Prometheus metrics
        if _PROMETHEUS_AVAILABLE:
            self._state_gauge = Gauge(
                "ai_gateway_circuit_breaker_state",
                "Current circuit breaker state (0=CLOSED, 1=OPEN, 2=HALF_OPEN)",
                ["breaker_name"],
            )
            self._failure_counter = Counter(
                "ai_gateway_circuit_breaker_failures_total",
                "Total number of failures that triggered the circuit breaker",
                ["breaker_name"],
            )
            self._transition_counter = Counter(
                "ai_gateway_circuit_breaker_transitions_total",
                "Total state transitions",
                ["breaker_name", "from_state", "to_state"],
            )
            self._export_metrics()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def before_call(self) -> bool:
        """
        Check if a request is allowed to proceed.

        Must be called before each request.

        Returns:
            True if the request can proceed, False if it should be rejected.
        """
        async with self._lock:
            self._prune_failures()

            if self._state == CircuitState.CLOSED:
                return True

            elif self._state == CircuitState.OPEN:
                if self._timeout_elapsed:
                    await self._transition_to(CircuitState.HALF_OPEN)
                    self._half_open_allowed = self.config.half_open_max_requests
                    return True
                return False

            elif self._state == CircuitState.HALF_OPEN:
                if self._half_open_allowed > 0:
                    self._half_open_allowed -= 1
                    return True
                return False

            return False

    async def on_success(self) -> None:
        """
        Report a successful request.

        In HALF_OPEN, this counts toward the success threshold.
        """
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.config.success_threshold:
                    await self._transition_to(CircuitState.CLOSED)
            elif self._state == CircuitState.CLOSED:
                # Reset failure window on clean success (optional optimistic behavior)
                if not self._failure_timestamps:
                    pass

    async def on_failure(self) -> None:
        """
        Report a failed request.

        In CLOSED, increments the failure counter. In HALF_OPEN, immediately
        transitions back to OPEN.
        """
        async with self._lock:
            now = time.monotonic()

            if self._state == CircuitState.CLOSED:
                self._failure_timestamps.append(now)
                self._prune_failures()

                if len(self._failure_timestamps) >= self.config.failure_threshold:
                    await self._transition_to(CircuitState.OPEN)
                    if _PROMETHEUS_AVAILABLE:
                        self._failure_counter.labels(breaker_name=self.name).inc()

            elif self._state == CircuitState.HALF_OPEN:
                await self._transition_to(CircuitState.OPEN)
                if _PROMETHEUS_AVAILABLE:
                    self._failure_counter.labels(breaker_name=self.name).inc()

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------

    async def _transition_to(self, new_state: CircuitState) -> None:
        """Transition the breaker to a new state and record the change."""
        if self._state == new_state:
            return

        old_state = self._state
        self._state = new_state
        self._last_state_change = time.monotonic()

        if new_state == CircuitState.CLOSED:
            self._failure_timestamps.clear()
            self._success_count = 0
            self._open_count = 0
            self._half_open_allowed = 0

        elif new_state == CircuitState.OPEN:
            self._open_count += 1
            self._success_count = 0
            self._half_open_allowed = 0

        elif new_state == CircuitState.HALF_OPEN:
            self._success_count = 0
            self._half_open_allowed = self.config.half_open_max_requests

        if _PROMETHEUS_AVAILABLE:
            self._transition_counter.labels(
                breaker_name=self.name,
                from_state=old_state.value,
                to_state=new_state.value,
            ).inc()
            self._export_metrics()

        logger.info(
            "Circuit breaker '%s': %s -> %s (open_count=%d)",
            self.name, old_state.value, new_state.value, self._open_count,
        )

    def _prune_failures(self) -> None:
        """Remove failure timestamps outside the configured window."""
        now = time.monotonic()
        cutoff = now - self.config.failure_window
        self._failure_timestamps = [
            ts for ts in self._failure_timestamps if ts >= cutoff
        ]

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def _timeout_elapsed(self) -> bool:
        """
        Check if the OPEN timeout has elapsed, accounting for exponential
        backoff based on the number of times the breaker has opened.
        """
        elapsed = time.monotonic() - self._last_state_change
        backoff_timeout = self._compute_backoff()
        return elapsed >= backoff_timeout

    def _compute_backoff(self) -> float:
        """
        Exponential backoff: timeout * 2^(open_count - 1), capped at max_timeout.
        """
        if self._open_count <= 1:
            return self.config.timeout

        backoff = self.config.timeout * (2 ** (self._open_count - 1))
        return min(backoff, self.config.max_timeout)

    @property
    def failure_count(self) -> int:
        """Number of failures in the current window."""
        self._prune_failures()
        return len(self._failure_timestamps)

    # ------------------------------------------------------------------
    # Prometheus export
    # ------------------------------------------------------------------

    def _export_metrics(self) -> None:
        """Export current state to Prometheus gauges."""
        if not _PROMETHEUS_AVAILABLE:
            return

        state_value = {
            CircuitState.CLOSED: 0,
            CircuitState.OPEN: 1,
            CircuitState.HALF_OPEN: 2,
        }.get(self._state, -1)

        self._state_gauge.labels(breaker_name=self.name).set(state_value)

    # ------------------------------------------------------------------
    # Status / diagnostics
    # ------------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        """Return a diagnostic snapshot of the circuit breaker."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "failure_threshold": self.config.failure_threshold,
            "open_count": self._open_count,
            "backoff_timeout_ms": round(self._compute_backoff() * 1000, 0),
            "last_state_change": self._last_state_change,
            "seconds_since_change": round(time.monotonic() - self._last_state_change, 2),
        }


# ---------------------------------------------------------------------------
# Circuit Breaker Manager
# ---------------------------------------------------------------------------

class CircuitBreakerManager:
    """
    Manages multiple circuit breakers, keyed by provider name.

    Provides:
      - get_or_create() for lazy instantiation
      - health_report() for monitoring
    """

    def __init__(self, default_config: Optional[CircuitConfig] = None):
        self._default_config = default_config or CircuitConfig()
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._lock = asyncio.Lock()

    async def get_or_create(
        self,
        name: str,
        config: Optional[CircuitConfig] = None,
    ) -> CircuitBreaker:
        """
        Get an existing circuit breaker or create a new one.

        Args:
            name: Unique breaker name (typically provider name).
            config: Optional per-breaker configuration override.

        Returns:
            The CircuitBreaker instance.
        """
        async with self._lock:
            if name not in self._breakers:
                self._breakers[name] = CircuitBreaker(
                    name=name, config=config or self._default_config
                )
            return self._breakers[name]

    async def before_call(self, name: str) -> bool:
        """Check if a request to the named provider is allowed."""
        breaker = await self.get_or_create(name)
        return await breaker.before_call()

    async def on_success(self, name: str) -> None:
        """Report a successful request to the named provider."""
        breaker = await self.get_or_create(name)
        await breaker.on_success()

    async def on_failure(self, name: str) -> None:
        """Report a failed request to the named provider."""
        breaker = await self.get_or_create(name)
        await breaker.on_failure()

    async def health_report(self) -> List[Dict[str, Any]]:
        """Get status reports for all managed circuit breakers."""
        async with self._lock:
            return [b.get_status() for b in self._breakers.values()]

    async def reset(self, name: str) -> None:
        """Force-reset a circuit breaker back to CLOSED state."""
        breaker = await self.get_or_create(name)
        async with breaker._lock:
            await breaker._transition_to(CircuitState.CLOSED)

    async def reset_all(self) -> None:
        """Force-reset all circuit breakers."""
        async with self._lock:
            for breaker in self._breakers.values():
                async with breaker._lock:
                    await breaker._transition_to(CircuitState.CLOSED)
