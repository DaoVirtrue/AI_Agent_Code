"""Latency tracker for streaming token generation.

Tracks Time-To-First-Token (TTFT) and Inter-Token Latency (ITL)
with P50, P90, P95, and P99 percentile calculations over a
configurable rolling window.
"""

from __future__ import annotations

import time
from collections import deque


class LatencyTracker:
    """Track streaming latency metrics: TTFT and ITL with percentiles.

    Maintains a rolling window of recent samples for both Time-To-First-Token
    (the delay from request start to first token) and Inter-Token Latency
    (the delay between consecutive tokens). Computes P50, P90, P95, and P99
    percentiles on demand.

    Usage:
        tracker = LatencyTracker(window_size=500)
        tracker.start_request()
        # ... time passes ...
        tracker.on_first_token()    # Records TTFT
        tracker.on_token()           # Records ITL for each subsequent token
        tracker.on_token()
        stats = tracker.stats()
        # {'ttft': {'p50': ..., 'p90': ..., 'p95': ..., 'p99': ..., 'avg': ..., 'count': N},
        #  'itl':  {'p50': ..., ...},
        #  'total_tokens': ...}
    """

    def __init__(self, window_size: int = 1000) -> None:
        """Initialize the latency tracker.

        Args:
            window_size: Maximum number of samples to retain per metric.
        """
        self._window_size = max(1, window_size)
        self._ttft_samples: deque[float] = deque(maxlen=self._window_size)
        self._itl_samples: deque[float] = deque(maxlen=self._window_size)
        self._request_start: float | None = None
        self._last_token_time: float | None = None
        self._total_tokens: int = 0
        self._total_requests: int = 0
        self._active_streams: int = 0

    def start_request(self) -> None:
        """Mark the start of a new streaming request.

        Records the current time as the request start. Should be called
        once per streaming request before the first token.
        """
        self._request_start = time.time()
        self._last_token_time = None
        self._total_requests += 1
        self._active_streams += 1

    def on_first_token(self) -> None:
        """Record Time-To-First-Token (TTFT).

        Should be called exactly once per request when the first token
        arrives. Computes the delta from start_request().
        """
        if self._request_start is None:
            return

        now = time.time()
        ttft = now - self._request_start
        self._ttft_samples.append(ttft)
        self._last_token_time = now
        self._total_tokens += 1

    def on_token(self) -> None:
        """Record Inter-Token Latency (ITL).

        Should be called for every token after the first. Computes the
        delta from the previous token (or first token if no ITL recorded yet).
        """
        now = time.time()
        if self._last_token_time is not None:
            itl = now - self._last_token_time
            self._itl_samples.append(itl)

        self._last_token_time = now
        self._total_tokens += 1

    def end_request(self) -> None:
        """Mark the end of a streaming request."""
        self._request_start = None
        self._last_token_time = None
        self._active_streams = max(0, self._active_streams - 1)

    def percentile(self, samples: list[float], p: float) -> float:
        """Calculate the p-th percentile from a list of samples.

        Uses linear interpolation between closest ranks.

        Args:
            samples: Sorted list of sample values.
            p: Percentile as a float (e.g., 50, 90, 95, 99).

        Returns:
            The value at the p-th percentile, or 0.0 if no samples.
        """
        if not samples:
            return 0.0

        sorted_samples = sorted(samples)
        n = len(sorted_samples)

        if p <= 0:
            return sorted_samples[0]
        if p >= 100:
            return sorted_samples[-1]

        # Linear interpolation between closest ranks
        rank = (p / 100.0) * (n - 1)
        lower = int(rank)
        upper = min(lower + 1, n - 1)
        frac = rank - lower

        if lower == upper:
            return sorted_samples[lower]

        return sorted_samples[lower] + frac * (sorted_samples[upper] - sorted_samples[lower])

    def stats(self) -> dict:
        """Get comprehensive latency statistics.

        Returns:
            Dictionary with:
            - ttft: {p50, p90, p95, p99, avg, min, max, count}
            - itl: {p50, p90, p95, p99, avg, min, max, count}
            - total_tokens: total token count
            - total_requests: total request count
            - active_streams: currently active stream count
        """
        ttft_list = list(self._ttft_samples)
        itl_list = list(self._itl_samples)

        sorted_ttft = sorted(ttft_list)
        sorted_itl = sorted(itl_list)

        return {
            "ttft": {
                "p50": round(self.percentile(sorted_ttft, 50), 6),
                "p90": round(self.percentile(sorted_ttft, 90), 6),
                "p95": round(self.percentile(sorted_ttft, 95), 6),
                "p99": round(self.percentile(sorted_ttft, 99), 6),
                "avg": round(sum(ttft_list) / len(ttft_list), 6) if ttft_list else 0.0,
                "min": round(sorted_ttft[0], 6) if sorted_ttft else 0.0,
                "max": round(sorted_ttft[-1], 6) if sorted_ttft else 0.0,
                "count": len(ttft_list),
            },
            "itl": {
                "p50": round(self.percentile(sorted_itl, 50), 6),
                "p90": round(self.percentile(sorted_itl, 90), 6),
                "p95": round(self.percentile(sorted_itl, 95), 6),
                "p99": round(self.percentile(sorted_itl, 99), 6),
                "avg": round(sum(itl_list) / len(itl_list), 6) if itl_list else 0.0,
                "min": round(sorted_itl[0], 6) if sorted_itl else 0.0,
                "max": round(sorted_itl[-1], 6) if sorted_itl else 0.0,
                "count": len(itl_list),
            },
            "total_tokens": self._total_tokens,
            "total_requests": self._total_requests,
            "active_streams": self._active_streams,
        }

    def reset(self) -> None:
        """Reset all metrics to zero."""
        self._ttft_samples.clear()
        self._itl_samples.clear()
        self._request_start = None
        self._last_token_time = None
        self._total_tokens = 0
        self._total_requests = 0
        self._active_streams = 0

    @property
    def ttft_count(self) -> int:
        """Number of TTFT samples collected."""
        return len(self._ttft_samples)

    @property
    def itl_count(self) -> int:
        """Number of ITL samples collected."""
        return len(self._itl_samples)
