"""
Provider Registry

Central registry for all LLM providers. Maps provider IDs to provider
instances and provides model-to-provider resolution.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from ai_gateway.providers.base import BaseProvider

logger = logging.getLogger(__name__)


class ProviderRegistry:
    """
    Thread-safe registry of provider instances.

    Supports:
      - Registering named providers
      - Looking up providers by ID or by model name
      - Listing all registered providers with status
      - Bulk health checks
    """

    def __init__(self):
        self._providers: Dict[str, BaseProvider] = {}
        self._model_to_provider: Dict[str, str] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    async def register(self, provider_id: str, provider: BaseProvider) -> None:
        """
        Register a provider instance under a unique ID.

        Args:
            provider_id: Unique identifier (e.g., 'openai', 'anthropic').
            provider: An initialized BaseProvider subclass instance.
        """
        async with self._lock:
            if provider_id in self._providers:
                logger.warning(
                    "Provider '%s' already registered; overwriting.", provider_id
                )
            self._providers[provider_id] = provider
            logger.info("Registered provider: %s (%s)", provider_id, type(provider).__name__)

    async def register_model_mapping(
        self, model_id: str, provider_id: str
    ) -> None:
        """
        Map a model identifier to a specific provider.

        Args:
            model_id: The model name (e.g., 'gpt-4o', 'claude-sonnet-4').
            provider_id: The registered provider ID.
        """
        async with self._lock:
            self._model_to_provider[model_id] = provider_id

    async def register_model_mappings(
        self, mappings: Dict[str, str]
    ) -> None:
        """
        Bulk-register model-to-provider mappings.

        Args:
            mappings: Dict of {model_id: provider_id}.
        """
        async with self._lock:
            self._model_to_provider.update(mappings)

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    async def get(self, provider_id: str) -> Optional[BaseProvider]:
        """
        Retrieve a provider by its registered ID.

        Args:
            provider_id: The provider's unique ID.

        Returns:
            The BaseProvider instance, or None if not found.
        """
        async with self._lock:
            return self._providers.get(provider_id)

    async def get_provider_for_model(self, model_id: str) -> Optional[BaseProvider]:
        """
        Resolve the correct provider for a given model name.

        First checks the explicit model-to-provider mapping, then falls
        back to heuristic-based matching (prefix matching on provider IDs
        and known model families).

        Args:
            model_id: The model identifier (e.g., 'gpt-4o').

        Returns:
            The BaseProvider instance or None if no provider can handle this model.
        """
        async with self._lock:
            # 1. Explicit mapping
            if model_id in self._model_to_provider:
                provider_id = self._model_to_provider[model_id]
                return self._providers.get(provider_id)

            # 2. Heuristic matching based on model name prefixes
            provider = self._heuristic_match(model_id)
            if provider:
                return provider

            # 3. Return the first available provider as a fallback
            if self._providers:
                return next(iter(self._providers.values()))

            return None

    def _heuristic_match(self, model_id: str) -> Optional[BaseProvider]:
        """
        Match a model name to a provider using naming conventions.

        gpt-*, o1, o3 -> openai
        claude-* -> anthropic
        deepseek-* -> deepseek
        """
        lower = model_id.lower()
        if lower.startswith(("gpt-", "o1", "o3")):
            return self._providers.get("openai")
        if lower.startswith("claude"):
            return self._providers.get("anthropic")
        if lower.startswith("deepseek"):
            return self._providers.get("deepseek")
        return None

    # ------------------------------------------------------------------
    # Listing & Health
    # ------------------------------------------------------------------

    async def list_providers(self) -> List[Dict[str, Any]]:
        """
        List all registered providers with status information.

        Returns:
            A list of dicts with keys: id, provider_name, type, avg_latency_ms,
            failure_rate, supports_tools, context_window.
        """
        async with self._lock:
            result = []
            for pid, prov in self._providers.items():
                result.append({
                    "id": pid,
                    "provider_name": prov.provider_name,
                    "type": type(prov).__name__,
                    "avg_latency_ms": round(prov.average_latency_ms, 2),
                    "failure_rate": round(prov.failure_rate, 4),
                    "supports_tools": prov.supports_tools,
                    "context_window": prov.context_window,
                })
            return result

    async def health_check_all(self) -> Dict[str, bool]:
        """
        Run health checks against all registered providers concurrently.

        Returns:
            Dict mapping provider_id -> healthy (bool).
        """
        provider_ids: List[str] = []
        async with self._lock:
            provider_ids = list(self._providers.keys())

        async def check_one(pid: str) -> tuple[str, bool]:
            prov = await self.get(pid)
            if prov is None:
                return (pid, False)
            try:
                healthy = await prov.health_check()
                return (pid, healthy)
            except Exception:
                return (pid, False)

        tasks = [check_one(pid) for pid in provider_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        status: Dict[str, bool] = {}
        for result in results:
            if isinstance(result, Exception):
                logger.error("Health check task failed: %s", result)
                continue
            pid, healthy = result
            status[pid] = healthy

        return status

    # ------------------------------------------------------------------
    # Management
    # ------------------------------------------------------------------

    async def unregister(self, provider_id: str) -> bool:
        """
        Remove a provider from the registry.

        Returns True if the provider existed and was removed.
        """
        async with self._lock:
            if provider_id in self._providers:
                del self._providers[provider_id]
                # Clean up model mappings pointing to this provider
                self._model_to_provider = {
                    m: p
                    for m, p in self._model_to_provider.items()
                    if p != provider_id
                }
                logger.info("Unregistered provider: %s", provider_id)
                return True
            return False

    @property
    def provider_count(self) -> int:
        """Number of registered providers (non-async for convenience)."""
        return len(self._providers)
