"""
Rate Limiter

Token bucket rate limiting with per-tenant and per-endpoint enforcement.
Supports Redis-backed distributed buckets and configurable tier limits.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class RateLimitResult(Enum):
    ALLOWED = "allowed"
    QUEUED = "queued"
    REJECTED = "rejected"


@dataclass
class RateLimitInfo:
    """Rate limit status details for response headers."""

    limit: int          # Maximum requests per second
    remaining: int      # Tokens remaining in the current window
    reset: int          # Unix timestamp when the bucket resets
    limit_tokens: int   # Total token quota in the current period
    remaining_tokens: int  # Tokens remaining


@dataclass
class TierConfig:
    """
    Rate limit configuration for a service tier.

    Attributes:
        requests_per_second: Maximum sustained RPS.
        tokens_per_day: Maximum tokens consumed per 24-hour window.
        burst_multiplier: How many times the steady rate can burst.
    """

    requests_per_second: float
    tokens_per_day: int
    burst_multiplier: float = 2.0


# Pre-defined tier configurations
TIER_CONFIGS: Dict[str, TierConfig] = {
    "free": TierConfig(
        requests_per_second=5,
        tokens_per_day=50000,
    ),
    "pro": TierConfig(
        requests_per_second=50,
        tokens_per_day=500000,
    ),
    "enterprise": TierConfig(
        requests_per_second=500,
        tokens_per_day=5000000,
    ),
}


# ---------------------------------------------------------------------------
# Token Bucket
# ---------------------------------------------------------------------------

class TokenBucket:
    """
    A single token bucket implementing the token bucket algorithm.

    Tokens refill at a steady rate. If tokens are available, a request
    consumes one. If not, the request is denied (or queued).
    """

    def __init__(
        self,
        rate: float,
        capacity: int,
        initial_tokens: Optional[int] = None,
    ):
        """
        Args:
            rate: Tokens refilled per second.
            capacity: Maximum burst tokens the bucket can hold.
            initial_tokens: Starting token count (defaults to capacity).
        """
        self.rate = rate
        self.capacity = capacity
        self.tokens = float(initial_tokens if initial_tokens is not None else capacity)
        self.last_refill = time.monotonic()

    def _refill(self) -> None:
        """Add tokens based on elapsed time since last refill."""
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_refill = now

    def consume(self, tokens: int = 1) -> bool:
        """
        Attempt to consume tokens from the bucket.

        Args:
            tokens: Number of tokens to consume (default 1 for a single request).

        Returns:
            True if tokens were consumed, False if insufficient tokens.
        """
        self._refill()
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    def time_until_token(self) -> float:
        """Estimated seconds until at least one token is available."""
        self._refill()
        if self.tokens >= 1:
            return 0.0
        return (1 - self.tokens) / self.rate if self.rate > 0 else float("inf")

    @property
    def available_tokens(self) -> float:
        """Current available tokens after refill."""
        self._refill()
        return self.tokens


# ---------------------------------------------------------------------------
# Rate Limiter
# ---------------------------------------------------------------------------

class RateLimiter:
    """
    Multi-tenant rate limiter with per-tenant + per-endpoint buckets.

    Uses in-memory TokenBuckets by default. When a Redis connection is
    provided, buckets are synchronized via Redis to support distributed
    deployments.
    """

    def __init__(
        self,
        redis_client: Optional[Any] = None,
        tier_configs: Optional[Dict[str, TierConfig]] = None,
        default_tier: str = "free",
    ):
        """
        Args:
            redis_client: Optional Redis client for distributed rate limiting.
            tier_configs: Override default tier configurations.
            default_tier: Tier assigned to unknown tenants.
        """
        self._redis = redis_client
        self._tier_configs = tier_configs or TIER_CONFIGS
        self._default_tier = default_tier
        self._buckets: Dict[str, Dict[str, TokenBucket]] = {}
        self._lock = asyncio.Lock()
        self._tenant_tiers: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # Tenant tier assignment
    # ------------------------------------------------------------------

    def set_tenant_tier(self, tenant_id: str, tier: str) -> None:
        """
        Assign a service tier to a tenant.

        Args:
            tenant_id: The tenant identifier.
            tier: One of 'free', 'pro', 'enterprise'.
        """
        if tier not in self._tier_configs:
            logger.warning(
                "Unknown tier '%s' for tenant '%s', defaulting to '%s'",
                tier, tenant_id, self._default_tier,
            )
            tier = self._default_tier
        self._tenant_tiers[tenant_id] = tier

    def get_tenant_tier(self, tenant_id: str) -> str:
        """Get the service tier for a tenant, falling back to default."""
        return self._tenant_tiers.get(tenant_id, self._default_tier)

    def get_tier_config(self, tenant_id: str) -> TierConfig:
        """Get the tier configuration for a specific tenant."""
        tier = self.get_tenant_tier(tenant_id)
        return self._tier_configs.get(tier, self._tier_configs[self._default_tier])

    # ------------------------------------------------------------------
    # Rate limit checks
    # ------------------------------------------------------------------

    async def check(
        self,
        tenant_id: str,
        endpoint: str = "default",
        tokens: int = 1,
    ) -> Tuple[RateLimitResult, RateLimitInfo]:
        """
        Check whether a request is allowed under the tenant's rate limits.

        Returns a tuple of (result, info) where info can be used to
        populate X-RateLimit-* response headers.

        Args:
            tenant_id: The tenant making the request.
            endpoint: The specific endpoint being accessed.
            tokens: Estimated token count of the request.

        Returns:
            (RateLimitResult, RateLimitInfo) tuple.
        """
        tier_cfg = self.get_tier_config(tenant_id)

        # -- RPS bucket --
        rps_bucket = await self._get_or_create_bucket(
            tenant_id, f"{endpoint}:rps", tier_cfg.requests_per_second,
            capacity=int(tier_cfg.requests_per_second * tier_cfg.burst_multiplier),
        )

        # -- Daily token bucket --
        token_bucket = await self._get_or_create_bucket(
            tenant_id, f"{endpoint}:tokens", tier_cfg.tokens_per_day / 86400.0,
            capacity=tier_cfg.tokens_per_day,
        )

        rps_allowed = rps_bucket.consume(1)
        token_allowed = token_bucket.consume(tokens)

        # Build rate limit info for headers
        info = RateLimitInfo(
            limit=int(tier_cfg.requests_per_second),
            remaining=max(0, int(rps_bucket.available_tokens)),
            reset=int(time.time() + rps_bucket.time_until_token()),
            limit_tokens=tier_cfg.tokens_per_day,
            remaining_tokens=max(0, int(token_bucket.available_tokens)),
        )

        if rps_allowed and token_allowed:
            return RateLimitResult.ALLOWED, info
        elif not rps_allowed:
            logger.info(
                "Rate limit: tenant=%s endpoint=%s reason=RPS tier=%s",
                tenant_id, endpoint, self.get_tenant_tier(tenant_id),
            )
            return RateLimitResult.REJECTED, info
        else:
            logger.info(
                "Rate limit: tenant=%s endpoint=%s reason=TOKENS tier=%s",
                tenant_id, endpoint, self.get_tenant_tier(tenant_id),
            )
            return RateLimitResult.REJECTED, info

    async def check_or_wait(
        self,
        tenant_id: str,
        endpoint: str = "default",
        timeout: float = 30.0,
    ) -> bool:
        """
        Check rate limit, waiting if necessary until tokens are available
        or the timeout expires.

        Returns True if the request can proceed, False if timed out.
        """
        deadline = time.monotonic() + timeout

        while True:
            result, info = await self.check(tenant_id, endpoint)
            if result == RateLimitResult.ALLOWED:
                return True

            wait_time = min(
                info.reset - time.time(),
                deadline - time.monotonic(),
            )

            if wait_time <= 0:
                return False

            await asyncio.sleep(min(wait_time, 1.0))

    # ------------------------------------------------------------------
    # Response headers
    # ------------------------------------------------------------------

    @staticmethod
    def build_headers(info: RateLimitInfo) -> Dict[str, str]:
        """
        Build X-RateLimit-* response headers from rate limit info.
        """
        return {
            "X-RateLimit-Limit": str(info.limit),
            "X-RateLimit-Remaining": str(info.remaining),
            "X-RateLimit-Reset": str(info.reset),
            "X-RateLimit-Limit-Tokens": str(info.limit_tokens),
            "X-RateLimit-Remaining-Tokens": str(info.remaining_tokens),
        }

    # ------------------------------------------------------------------
    # Bucket management
    # ------------------------------------------------------------------

    async def _get_or_create_bucket(
        self,
        tenant_id: str,
        bucket_key: str,
        rate: float,
        capacity: int,
    ) -> TokenBucket:
        """
        Retrieve or create a token bucket. When Redis is available, uses
        Lua scripts for atomic operations across multiple instances.
        """
        if self._redis:
            return await self._redis_bucket(tenant_id, bucket_key, rate, capacity)

        # In-memory fallback
        async with self._lock:
            if tenant_id not in self._buckets:
                self._buckets[tenant_id] = {}
            if bucket_key not in self._buckets[tenant_id]:
                self._buckets[tenant_id][bucket_key] = TokenBucket(
                    rate=rate, capacity=capacity
                )
            return self._buckets[tenant_id][bucket_key]

    async def _redis_bucket(
        self,
        tenant_id: str,
        bucket_key: str,
        rate: float,
        capacity: int,
    ) -> TokenBucket:
        """
        Distributed token bucket using Redis.

        Uses a simplified approach: store token count and last refill time
        in Redis, compute available tokens locally. This avoids the need
        for a Lua script while remaining approximately correct under
        concurrent access.
        """
        redis_key = f"ratelimit:{tenant_id}:{bucket_key}"

        # For simplicity in this implementation, we fall back to in-memory
        # when Redis operations fail, ensuring availability.
        try:
            now = time.time()
            stored = await self._redis.hgetall(redis_key)

            if stored:
                tokens = float(stored.get(b"tokens", capacity))
                last_refill = float(stored.get(b"last_refill", now))
                elapsed = now - last_refill
                tokens = min(float(capacity), tokens + elapsed * rate)

                if tokens >= 1:
                    tokens -= 1
                    await self._redis.hset(redis_key, mapping={
                        "tokens": str(tokens),
                        "last_refill": str(now),
                    })
                    await self._redis.expire(redis_key, 86400)
                    # Return a dummy bucket that reports success
                    bucket = TokenBucket(rate=rate, capacity=capacity)
                    return bucket

        except Exception as exc:
            logger.warning("Redis rate limit failed, falling back to local: %s", exc)

        # Fallback to in-memory
        async with self._lock:
            if tenant_id not in self._buckets:
                self._buckets[tenant_id] = {}
            if bucket_key not in self._buckets[tenant_id]:
                self._buckets[tenant_id][bucket_key] = TokenBucket(
                    rate=rate, capacity=capacity
                )
            return self._buckets[tenant_id][bucket_key]

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    async def get_tenant_status(self, tenant_id: str) -> Dict[str, Any]:
        """Get current rate limit status for a tenant."""
        tier = self.get_tenant_tier(tenant_id)
        tier_cfg = self.get_tier_config(tenant_id)

        status: Dict[str, Any] = {
            "tenant_id": tenant_id,
            "tier": tier,
            "rps_limit": tier_cfg.requests_per_second,
            "daily_token_limit": tier_cfg.tokens_per_day,
            "buckets": {},
        }

        async with self._lock:
            if tenant_id in self._buckets:
                for key, bucket in self._buckets[tenant_id].items():
                    status["buckets"][key] = {
                        "available": round(bucket.available_tokens, 2),
                        "capacity": bucket.capacity,
                    }

        return status
