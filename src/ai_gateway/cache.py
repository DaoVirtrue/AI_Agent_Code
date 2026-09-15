"""
Gateway Response Cache

Redis-backed response cache with SHA-256 content-addressed keys.
Caches LLM responses based on request fingerprint (model + messages +
temperature + max_tokens). Emits Prometheus metrics for hit/miss tracking.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Any, Dict, Optional

from src.ai_gateway.providers.base import LLMRequest, LLMResponse, ToolCall, TokenUsage

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prometheus metrics (optional import)
# ---------------------------------------------------------------------------

try:
    from prometheus_client import Counter

    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False
    Counter = None  # type: ignore


class ResponseCache:
    """
    Content-addressed cache for LLM responses.

    Uses SHA-256 to generate a deterministic key from the request:
      (model + canonicalized messages + temperature + max_tokens)

    Keys include a semantic version prefix to allow cache invalidation
    when the gateway logic changes.
    """

    CACHE_NAMESPACE = "gateway:cache"
    CACHE_VERSION = "v1"

    def __init__(
        self,
        redis_client: Optional[Any] = None,
        default_ttl: int = 3600,
        max_entry_size_kb: int = 512,
    ):
        """
        Args:
            redis_client: Redis client instance (redis.asyncio or equivalent).
            default_ttl: Default cache TTL in seconds (1 hour).
            max_entry_size_kb: Maximum cache entry size in KB to prevent
                               oversized entries from consuming too much memory.
        """
        self._redis = redis_client
        self._default_ttl = default_ttl
        self._max_entry_size_kb = max_entry_size_kb

        # In-memory fallback cache when Redis is unavailable
        self._memory_cache: Dict[str, bytes] = {}
        self._memory_expiry: Dict[str, float] = {}
        self._memory_lock = asyncio.Lock()

        # Prometheus counters
        if _PROMETHEUS_AVAILABLE:
            self._cache_hits = Counter(
                "ai_gateway_cache_hits_total",
                "Total number of cache hits",
                ["namespace"],
            )
            self._cache_misses = Counter(
                "ai_gateway_cache_misses_total",
                "Total number of cache misses",
                ["namespace"],
            )
            self._cache_errors = Counter(
                "ai_gateway_cache_errors_total",
                "Total number of cache errors",
                ["namespace", "error_type"],
            )
        else:
            self._cache_hits = None
            self._cache_misses = None
            self._cache_errors = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_cache_key(self, request: LLMRequest) -> str:
        """
        Generate a deterministic SHA-256 cache key for a request.

        The key is derived from: (model + canonical serialization of messages +
        temperature + max_tokens). This ensures semantically identical
        requests map to the same key regardless of streaming preference
        or metadata differences.

        Args:
            request: The LLMRequest to generate a key for.

        Returns:
            A cache key string of the form "gateway:cache:v1:<sha256>".
        """
        components: Dict[str, Any] = {
            "model": request.model,
            "messages": self._canonicalize_messages(request.messages),
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        # Include tools if present (affects response content)
        if request.tools:
            components["tools"] = self._canonicalize_tools(request.tools)
        if request.tool_choice:
            components["tool_choice"] = request.tool_choice

        serialized = json.dumps(components, sort_keys=True, ensure_ascii=False)
        digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()

        return f"{self.CACHE_NAMESPACE}:{self.CACHE_VERSION}:{digest}"

    async def get(self, key: str) -> Optional[LLMResponse]:
        """
        Retrieve a cached LLMResponse by key.

        Args:
            key: The cache key from get_cache_key().

        Returns:
            The cached LLMResponse, or None if not found or expired.
        """
        try:
            if self._redis:
                cached = await self._redis.get(key)
                if cached:
                    response = self._deserialize(cached)
                    if _PROMETHEUS_AVAILABLE and self._cache_hits is not None:
                        self._cache_hits.labels(namespace="gateway").inc()
                    logger.debug("Cache hit: %s", key)
                    return response

            else:
                async with self._memory_lock:
                    if key in self._memory_cache:
                        import time
                        expiry = self._memory_expiry.get(key, 0)
                        if time.time() < expiry:
                            response = self._deserialize(self._memory_cache[key])
                            if _PROMETHEUS_AVAILABLE and self._cache_hits is not None:
                                self._cache_hits.labels(namespace="gateway").inc()
                            logger.debug("Cache hit (memory): %s", key)
                            return response
                        else:
                            # Expired
                            del self._memory_cache[key]
                            self._memory_expiry.pop(key, None)

            if _PROMETHEUS_AVAILABLE and self._cache_misses is not None:
                self._cache_misses.labels(namespace="gateway").inc()

        except Exception as exc:
            logger.error("Cache get error for key %s: %s", key, exc)
            if _PROMETHEUS_AVAILABLE and self._cache_errors is not None:
                self._cache_errors.labels(
                    namespace="gateway", error_type=type(exc).__name__
                ).inc()

        return None

    async def set(
        self,
        key: str,
        response: LLMResponse,
        ttl: Optional[int] = None,
    ) -> bool:
        """
        Store an LLMResponse in the cache.

        Args:
            key: The cache key.
            response: The LLMResponse to cache.
            ttl: Optional TTL override in seconds.

        Returns:
            True if stored successfully, False otherwise.
        """
        try:
            serialized = self._serialize(response)

            # Skip entries that exceed the maximum size
            if len(serialized) > self._max_entry_size_kb * 1024:
                logger.debug("Cache entry too large for key %s (%d bytes), skipping",
                             key, len(serialized))
                return False

            effective_ttl = ttl if ttl is not None else self._default_ttl

            if self._redis:
                await self._redis.setex(key, effective_ttl, serialized)
            else:
                import time
                async with self._memory_lock:
                    self._memory_cache[key] = serialized
                    self._memory_expiry[key] = time.time() + effective_ttl

            logger.debug("Cache set: %s (TTL=%ds)", key, effective_ttl)
            return True

        except Exception as exc:
            logger.error("Cache set error for key %s: %s", key, exc)
            if _PROMETHEUS_AVAILABLE and self._cache_errors is not None:
                self._cache_errors.labels(
                    namespace="gateway", error_type=type(exc).__name__
                ).inc()
            return False

    async def invalidate(self, key: str) -> bool:
        """
        Remove a specific entry from the cache.

        Returns True if the key existed and was removed.
        """
        try:
            if self._redis:
                deleted = await self._redis.delete(key)
                return deleted > 0
            else:
                async with self._memory_lock:
                    existed = key in self._memory_cache
                    self._memory_cache.pop(key, None)
                    self._memory_expiry.pop(key, None)
                    return existed
        except Exception as exc:
            logger.error("Cache invalidate error: %s", exc)
            return False

    async def flush_namespace(self) -> int:
        """
        Remove all cache entries in the gateway namespace.

        Returns the number of keys deleted.
        """
        pattern = f"{self.CACHE_NAMESPACE}:{self.CACHE_VERSION}:*"
        try:
            if self._redis:
                keys = []
                cursor = 0
                while True:
                    cursor, batch = await self._redis.scan(
                        cursor=cursor, match=pattern, count=100
                    )
                    keys.extend(batch)
                    if cursor == 0:
                        break
                if keys:
                    return await self._redis.delete(*keys)
                return 0
            else:
                async with self._memory_lock:
                    count = len(self._memory_cache)
                    self._memory_cache.clear()
                    self._memory_expiry.clear()
                    return count
        except Exception as exc:
            logger.error("Cache flush error: %s", exc)
            return 0

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def _serialize(self, response: LLMResponse) -> bytes:
        """Serialize an LLMResponse to bytes for storage."""
        data = response.to_dict()
        return json.dumps(data, ensure_ascii=False).encode("utf-8")

    def _deserialize(self, raw: bytes) -> LLMResponse:
        """Deserialize bytes back to an LLMResponse."""
        data = json.loads(raw.decode("utf-8"))

        tool_calls = None
        if data.get("tool_calls"):
            tool_calls = [ToolCall.from_dict(tc) for tc in data["tool_calls"]]

        usage_data = data.get("usage", {})
        usage = TokenUsage(
            input_tokens=usage_data.get("input_tokens", 0),
            output_tokens=usage_data.get("output_tokens", 0),
            cached_tokens=usage_data.get("cached_tokens", 0),
        )

        return LLMResponse(
            id=data.get("id", ""),
            model=data.get("model", ""),
            content=data.get("content"),
            tool_calls=tool_calls,
            finish_reason=data.get("finish_reason", "stop"),
            usage=usage,
            latency_ms=data.get("latency_ms", 0.0),
            metadata=data.get("metadata", {}),
        )

    # ------------------------------------------------------------------
    # Cache key helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _canonicalize_messages(messages: list) -> list:
        """Create a canonical representation of messages for hashing."""
        canonical = []
        for msg in messages:
            entry: Dict[str, Any] = {
                "role": msg.role,
                "content": msg.content,
            }
            if msg.name:
                entry["name"] = msg.name
            if msg.tool_calls:
                entry["tool_calls"] = [
                    {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                    for tc in msg.tool_calls
                ]
            if msg.tool_call_id:
                entry["tool_call_id"] = msg.tool_call_id
            canonical.append(entry)
        return canonical

    @staticmethod
    def _canonicalize_tools(tools: list) -> list:
        """Create a canonical representation of tool definitions."""
        canonical = []
        for tool in tools:
            if isinstance(tool, dict):
                canonical.append(json.dumps(tool, sort_keys=True))
            else:
                canonical.append(str(tool))
        return sorted(canonical)

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return cache statistics."""
        if self._redis:
            return {
                "backend": "redis",
                "namespace": self.CACHE_NAMESPACE,
                "version": self.CACHE_VERSION,
                "default_ttl": self._default_ttl,
            }
        else:
            return {
                "backend": "memory",
                "namespace": self.CACHE_NAMESPACE,
                "version": self.CACHE_VERSION,
                "default_ttl": self._default_ttl,
                "entries": len(self._memory_cache),
            }
