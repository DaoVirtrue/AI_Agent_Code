"""
Async Redis client – connection pool, FastAPI dependency, and helper functions.

Uses ``redis.asyncio`` for full async support.
"""

from __future__ import annotations

import json
from typing import Any, AsyncGenerator, Optional

import redis.asyncio as aioredis
from redis.asyncio import Redis

from .config import Settings, get_settings

# ---------------------------------------------------------------------------
# Globals
# ---------------------------------------------------------------------------

_pool: aioredis.ConnectionPool | None = None
_client: Redis | None = None


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def create_redis_pool(settings: Settings | None = None) -> aioredis.ConnectionPool:
    """Create (or return existing) async Redis connection pool."""
    global _pool

    if _pool is not None:
        return _pool

    if settings is None:
        settings = get_settings()

    _pool = aioredis.ConnectionPool.from_url(
        settings.redis.url,
        max_connections=settings.redis.max_connections,
        socket_timeout=settings.redis.socket_timeout,
        decode_responses=settings.redis.decode_responses,
    )
    return _pool


def _get_client() -> Redis:
    """Return the shared Redis client (lazy-init)."""
    global _client
    if _client is None:
        pool = create_redis_pool()
        _client = Redis(connection_pool=pool)
    return _client


async def close_redis() -> None:
    """Gracefully close the Redis pool (call on shutdown)."""
    global _client, _pool
    if _client is not None:
        await _client.close()
        _client = None
    if _pool is not None:
        await _pool.disconnect()
        _pool = None


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


async def get_redis() -> AsyncGenerator[Redis, None]:
    """FastAPI dependency yielding a Redis client from the shared pool.

    Usage::

        from fastapi import Depends
        from shared.redis import get_redis

        @router.get("/cache/{key}")
        async def get_value(key: str, r: Redis = Depends(get_redis)):
            return await r.get(key)
    """
    client = _get_client()
    yield client
    # No close – the pool is shared across requests.


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------


async def cache_get(key: str) -> Optional[Any]:
    """Read a JSON value from the cache.  Returns None on miss."""
    client = _get_client()
    raw = await client.get(key)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw


async def cache_set(
    key: str,
    value: Any,
    ttl: int | None = 300,
) -> None:
    """Write a JSON-serialisable value to the cache with an optional TTL (seconds)."""
    client = _get_client()
    payload = json.dumps(value, default=str)
    if ttl is not None:
        await client.setex(key, ttl, payload)
    else:
        await client.set(key, payload)


async def cache_delete(*keys: str) -> int:
    """Delete one or more cache keys. Returns the number of keys removed."""
    if not keys:
        return 0
    client = _get_client()
    return await client.delete(*keys)


# ---------------------------------------------------------------------------
# Rate limiting (token-bucket via Redis)
# ---------------------------------------------------------------------------


_RATE_LIMIT_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

local bucket = redis.call("HMGET", key, "tokens", "last_refill")
local tokens = tonumber(bucket[1]) or capacity
local last_refill = tonumber(bucket[2]) or now

local elapsed = math.max(now - last_refill, 0)
local refill = elapsed * refill_rate
tokens = math.min(tokens + refill, capacity)

if tokens >= 1 then
    redis.call("HMSET", key, "tokens", tokens - 1, "last_refill", now)
    redis.call("EXPIRE", key, math.ceil(capacity / refill_rate) + 10)
    return {1, math.floor(tokens - 1)}
else
    redis.call("HMSET", key, "tokens", tokens, "last_refill", now)
    redis.call("EXPIRE", key, math.ceil(capacity / refill_rate) + 10)
    return {0, math.floor(tokens)}
end
"""


async def rate_limit_check(
    key: str,
    capacity: int = 100,
    refill_rate: float = 10.0,
) -> tuple[bool, int]:
    """Token-bucket rate limiter.

    Args:
        key: Redis key (e.g. ``rate_limit:{tenant_id}:{operation}``).
        capacity: Max burst size (tokens).
        refill_rate: Tokens added per second.

    Returns:
        (allowed, remaining_tokens)
    """
    import time

    client = _get_client()
    now = time.time()
    result = await client.eval(
        _RATE_LIMIT_LUA,
        1,
        key,
        capacity,
        refill_rate,
        now,
    )
    allowed = bool(result[0])
    remaining = int(result[1])
    return allowed, remaining


# ---------------------------------------------------------------------------
# Pub / Sub
# ---------------------------------------------------------------------------


async def publish(channel: str, message: dict[str, Any]) -> int:
    """Publish a JSON-serialised message to a Redis channel."""
    client = _get_client()
    payload = json.dumps(message, default=str)
    return await client.publish(channel, payload)


async def subscribe(channel: str) -> AsyncGenerator[dict[str, Any], None]:
    """Async generator that yields messages from a Redis Pub/Sub channel.

    Usage::

        async for msg in subscribe("agent:events"):
            handle(msg)
    """
    client = _get_client()
    pubsub = client.pubsub()
    await pubsub.subscribe(channel)
    try:
        async for raw in pubsub.listen():
            if raw["type"] == "message":
                data = raw["data"]
                if isinstance(data, (str, bytes)):
                    yield json.loads(data)
                else:
                    yield data
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()
