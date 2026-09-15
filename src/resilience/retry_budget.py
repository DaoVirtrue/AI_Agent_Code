"""Retry budget + retry storm detection（文档第 11.2 节）.

Prevents retry storms: a service under pressure must not amplify load by
retrying without bounds. Two mechanisms:

1. **Retry budget** — a share of requests per time window that may be retried
   (e.g. 10%/min globally, 5%/min for writes). Exceeding the budget turns
   retries into fast-fail.
2. **Storm detection** — flag when the retry rate spikes above a threshold,
   which usually means the downstream is down and retries are futile.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class RetryBudgetConfig:
    """Configuration for the retry budget.

    Attributes:
        window_seconds: Rolling window size (default 60s).
        max_retry_rate: Max fraction of requests that may be retries (0.10 = 10%).
        storm_threshold: Retry rate above which a storm is declared (0.5 = 50%).
    """

    window_seconds: float = 60.0
    max_retry_rate: float = 0.10
    storm_threshold: float = 0.50


class RetryBudget:
    """Tracks the rolling retry rate and enforces the budget.

    Usage::

        budget = RetryBudget()
        if budget.allow_retry():
            ... retry ...
    """

    def __init__(self, config: RetryBudgetConfig | None = None):
        self.config = config or RetryBudgetConfig()
        self._requests: deque[tuple[float, bool]] = deque()  # (timestamp, was_retry)
        self._total_retries = 0
        self._storm_count = 0

    def record_request(self, *, is_retry: bool) -> None:
        """Record a request (retry or fresh)."""
        now = time.monotonic()
        self._requests.append((now, is_retry))
        if is_retry:
            self._total_retries += 1
        self._prune(now)

    def allow_retry(self) -> bool:
        """Return True if a retry is allowed under the current budget."""
        now = time.monotonic()
        self._prune(now)

        if not self._requests:
            return True

        retries = sum(1 for _, r in self._requests if r)
        rate = retries / len(self._requests)
        return rate < self.config.max_retry_rate

    def is_storm(self) -> bool:
        """Return True if the retry rate indicates a retry storm."""
        now = time.monotonic()
        self._prune(now)
        if not self._requests:
            return False

        retries = sum(1 for _, r in self._requests if r)
        rate = retries / len(self._requests)
        if rate >= self.config.storm_threshold:
            self._storm_count += 1
            return True
        return False

    @property
    def retry_rate(self) -> float:
        """Current retry rate (0.0 to 1.0)."""
        self._prune(time.monotonic())
        if not self._requests:
            return 0.0
        retries = sum(1 for _, r in self._requests if r)
        return retries / len(self._requests)

    @property
    def total_retries(self) -> int:
        return self._total_retries

    @property
    def storms_detected(self) -> int:
        return self._storm_count

    def _prune(self, now: float) -> None:
        cutoff = now - self.config.window_seconds
        while self._requests and self._requests[0][0] < cutoff:
            self._requests.popleft()


def exponential_backoff(attempt: int, base: float = 0.1, cap: float = 5.0) -> float:
    """Exponential backoff with jitter: ``base * 2^n``, capped at ``cap``.

    The architecture doc recommends base 100ms and a single-retry cap of 5s.
    """
    delay = min(base * (2 ** attempt), cap)
    return delay
