"""
Retry Handler

Exponential backoff with jitter for transient failures. Uses the tenacity
library for reliable retry logic.
"""

from __future__ import annotations

import logging
import random
from typing import Any, Callable, Coroutine, List, Optional, Set

import tenacity
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception,
    before_sleep,
    after_log,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Retryable exception detection
# ---------------------------------------------------------------------------

_RETRYABLE_STATUS_CODES: Set[int] = {429, 500, 502, 503, 504}

_RETRYABLE_EXCEPTION_TYPES: Set[str] = {
    "RateLimitError",
    "APITimeoutError",
    "APIConnectionError",
    "InternalServerError",
    "ServiceUnavailableError",
    "Timeout",
    "ConnectionError",
    "ReadTimeout",
    "ConnectTimeout",
}


def is_retryable(exception: BaseException) -> bool:
    """
    Determine if an exception should trigger a retry.

    Retryable conditions:
      - HTTP 429 (rate limit)
      - HTTP 5xx (server errors)
      - Timeout errors
      - Connection errors
      - Specific known error types from openai/anthropic SDKs
    """
    # Check for HTTP status code on the exception
    status_code = getattr(exception, "status_code", None)
    if status_code is not None and status_code in _RETRYABLE_STATUS_CODES:
        return True

    # Check for HTTP status from response attribute
    if hasattr(exception, "response"):
        response = getattr(exception, "response", None)
        if response is not None:
            resp_status = getattr(response, "status_code", None)
            if resp_status in _RETRYABLE_STATUS_CODES:
                return True

    # Check HTTP status from body (Anthropic sometimes wraps it)
    if hasattr(exception, "body"):
        import json
        body = getattr(exception, "body", None)
        if isinstance(body, dict):
            body_status = body.get("status_code") or body.get("status")
            if isinstance(body_status, int) and body_status in _RETRYABLE_STATUS_CODES:
                return True

    # Check for standard error types
    exc_type = type(exception).__name__
    if exc_type in _RETRYABLE_EXCEPTION_TYPES:
        return True

    # Check module path for known SDK exceptions
    module = getattr(type(exception), "__module__", "")
    qualified = f"{module}.{exc_type}"
    for retryable in _RETRYABLE_EXCEPTION_TYPES:
        if retryable in qualified:
            return True

    # Generic timeout / connection checks
    if isinstance(exception, (TimeoutError, ConnectionError)):
        return True

    # Check message for common transient error patterns
    message = str(exception).lower()
    transient_keywords = [
        "timeout",
        "rate limit",
        "too many requests",
        "service unavailable",
        "server error",
        "internal error",
        "connection",
        "capacity",
        "overloaded",
        "throttle",
    ]
    for keyword in transient_keywords:
        if keyword in message:
            return True

    return False


# ---------------------------------------------------------------------------
# Retry Handler
# ---------------------------------------------------------------------------

class RetryHandler:
    """
    Handles retries with exponential backoff and jitter.

    Configured with sensible defaults for LLM API calls:
      - Base delay: 1 second
      - Max delay: 60 seconds
      - Max retries: 3
      - Jitter: enabled

    Uses the tenacity library internally.
    """

    def __init__(
        self,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        max_retries: int = 3,
        jitter: bool = True,
    ):
        """
        Args:
            base_delay: Starting delay in seconds.
            max_delay: Maximum delay cap in seconds.
            max_retries: Maximum number of retry attempts.
            jitter: Whether to add random jitter to backoff delays.
        """
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._max_retries = max_retries
        self._jitter = jitter

    # ------------------------------------------------------------------
    # Core execute method
    # ------------------------------------------------------------------

    async def execute_with_retry(
        self,
        func: Callable[..., Coroutine[Any, Any, Any]],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """
        Execute an async function with retry on transient failures.

        Args:
            func: An async callable to execute.
            *args: Positional arguments forwarded to func.
            **kwargs: Keyword arguments forwarded to func.

        Returns:
            The return value of func.

        Raises:
            The last exception if all retries are exhausted.
        """
        last_exception: Optional[BaseException] = None

        for attempt in range(self._max_retries + 1):
            try:
                result = await func(*args, **kwargs)
                # Record successful retry if it wasn't the first attempt
                if attempt > 0:
                    logger.info(
                        "Retry succeeded on attempt %d/%d",
                        attempt, self._max_retries,
                    )
                return result

            except Exception as exc:
                last_exception = exc

                if not is_retryable(exc):
                    logger.warning(
                        "Non-retryable error (attempt %d): %s",
                        attempt + 1, exc,
                    )
                    raise

                if attempt >= self._max_retries:
                    logger.error(
                        "All %d retries exhausted. Last error: %s",
                        self._max_retries, exc,
                    )
                    raise

                delay = self._compute_delay(attempt)
                logger.warning(
                    "Retryable error (attempt %d/%d), retrying in %.2fs: %s",
                    attempt + 1, self._max_retries, delay, exc,
                )

                import asyncio
                await asyncio.sleep(delay)

        # Should not reach here, but just in case
        if last_exception:
            raise last_exception
        raise RuntimeError("Retry loop exited without result or exception")

    # ------------------------------------------------------------------
    # Decorator factory (for use with tenacity)
    # ------------------------------------------------------------------

    def get_retry_decorator(self) -> Any:
        """
        Return a tenacity retry decorator configured with this handler's settings.

        Can be used as:
            @retry_handler.get_retry_decorator()
            async def my_function(): ...
        """
        return retry(
            stop=stop_after_attempt(self._max_retries + 1),
            wait=wait_exponential(
                multiplier=self._base_delay,
                max=self._max_delay,
                exp_base=2,
            ),
            retry=retry_if_exception(is_retryable),
            before_sleep=before_sleep(logger, logging.WARNING),
            after=after_log(logger, logging.DEBUG),
            reraise=True,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _compute_delay(self, attempt: int) -> float:
        """
        Compute backoff delay with optional jitter.

        Uses the formula: min(max_delay, base_delay * 2^attempt)
        Jitter: adds +/- 25% randomness.
        """
        delay = min(self._max_delay, self._base_delay * (2 ** attempt))

        if self._jitter:
            # Jitter range: 75% to 125% of computed delay
            jitter_factor = random.uniform(0.75, 1.25)
            delay *= jitter_factor

        return round(delay, 3)

    @property
    def max_retries(self) -> int:
        return self._max_retries

    @property
    def base_delay(self) -> float:
        return self._base_delay

    @property
    def max_delay(self) -> float:
        return self._max_delay
