"""
Fallback Chain

Configurable fallback chains for model failover. When a primary model
fails, the fallback chain tries alternative models in sequence.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

from src.ai_gateway.providers.base import LLMRequest, LLMResponse

logger = logging.getLogger(__name__)


class FallbackExhaustedError(Exception):
    """Raised when all fallback models in a chain have been exhausted."""

    def __init__(
        self,
        original_model: str,
        tried_models: List[str],
        last_error: Optional[Exception] = None,
    ):
        self.original_model = original_model
        self.tried_models = tried_models
        self.last_error = last_error
        super().__init__(
            f"All fallback models exhausted for '{original_model}'. "
            f"Tried: {tried_models}. Last error: {last_error}"
        )


# ---------------------------------------------------------------------------
# Default fallback chains
# ---------------------------------------------------------------------------

DEFAULT_FALLBACK_CHAINS: Dict[str, List[str]] = {
    "gpt-4o": ["claude-sonnet-4", "gpt-4o-mini"],
    "gpt-4.1": ["claude-sonnet-4", "gpt-4o-mini"],
    "claude-opus-4": ["claude-sonnet-4", "gpt-4o"],
    "claude-sonnet-4": ["gpt-4o", "gpt-4o-mini"],
    "deepseek-chat": ["gpt-4o-mini", "claude-haiku-3.5"],
    "gpt-4o-mini": ["claude-haiku-3.5", "deepseek-chat"],
    "claude-haiku-3.5": ["gpt-4o-mini"],
}

# Models that can be tried as universal last resorts
_UNIVERSAL_FALLBACKS: List[str] = ["gpt-4o-mini"]


# ---------------------------------------------------------------------------
# Fallback Chain
# ---------------------------------------------------------------------------

class FallbackChain:
    """
    Manages model fallback chains. When a model fails, the chain tries
    each fallback model in order until one succeeds or all are exhausted.
    """

    def __init__(
        self,
        chains: Optional[Dict[str, List[str]]] = None,
        universal_fallbacks: Optional[List[str]] = None,
    ):
        """
        Args:
            chains: Mapping of model_id -> [fallback_model_ids].
                    Uses DEFAULT_FALLBACK_CHAINS if not provided.
            universal_fallbacks: Fallback models to try if no chain is defined
                                 for a model.
        """
        self._chains: Dict[str, List[str]] = {}
        # Merge with defaults (user config overrides)
        for model, fallbacks in (chains or DEFAULT_FALLBACK_CHAINS).items():
            self._chains[model] = list(fallbacks)

        self._universal_fallbacks = universal_fallbacks or _UNIVERSAL_FALLBACKS

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def set_chain(self, model_id: str, fallback_models: List[str]) -> None:
        """
        Define or update a fallback chain for a model.

        Args:
            model_id: The primary model identifier.
            fallback_models: Ordered list of fallback model IDs.
        """
        self._chains[model_id] = list(fallback_models)
        logger.info("Fallback chain for '%s' set to %s", model_id, fallback_models)

    def get_chain(self, model_id: str) -> List[str]:
        """
        Get the fallback chain for a model.

        If no explicit chain is defined, returns universal fallbacks.
        """
        chain = self._chains.get(model_id)
        if chain:
            return list(chain)

        # Try partial match on model family
        for known_model in self._chains:
            if model_id.startswith(known_model):
                return list(self._chains[known_model])

        return list(self._universal_fallbacks)

    def list_chains(self) -> Dict[str, List[str]]:
        """Return all configured fallback chains."""
        return {k: list(v) for k, v in self._chains.items()}

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def execute(
        self,
        request: LLMRequest,
        execute_fn: Any,  # async callable: (LLMRequest) -> LLMResponse
        failed_models: Optional[Set[str]] = None,
    ) -> LLMResponse:
        """
        Execute a request with fallback support.

        Calls execute_fn(request) with the original model. On failure, iterates
        through the fallback chain, retrying with each fallback model. On success,
        adds "fallback_from" to the response metadata.

        Args:
            request: The LLMRequest (will be mutated with fallback model names).
            execute_fn: An async callable that takes an LLMRequest and returns
                        an LLMResponse. Typically this is the provider's chat()
                        method or a gateway-level routing function.
            failed_models: Set of models that have already failed (e.g., from
                           circuit breaker state). These are skipped.

        Returns:
            LLMResponse from the first successful model.

        Raises:
            FallbackExhaustedError: If all fallback models fail.
        """
        tried_models: List[str] = []
        last_error: Optional[Exception] = None
        skipped_models = failed_models or set()

        # 1. Try the original model
        current_model = request.model
        if current_model not in skipped_models:
            tried_models.append(current_model)
            request.model = current_model
            try:
                result = await execute_fn(request)
                return result
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Primary model '%s' failed: %s", current_model, exc
                )
        elif current_model in skipped_models:
            logger.info("Primary model '%s' skipped (previously failed)", current_model)

        # 2. Try fallback chain
        fallback_models = self.get_chain(current_model)
        for fb_model in fallback_models:
            if fb_model in skipped_models:
                logger.info("Fallback model '%s' skipped (previously failed)", fb_model)
                continue

            tried_models.append(fb_model)
            request.model = fb_model

            try:
                logger.info("Trying fallback model '%s' for '%s'", fb_model, current_model)
                result = await execute_fn(request)

                # Tag response with fallback metadata
                result.metadata["fallback_from"] = current_model
                result.metadata["fallback_chain"] = tried_models

                return result

            except Exception as exc:
                last_error = exc
                logger.warning("Fallback model '%s' failed: %s", fb_model, exc)

        # 3. All exhausted
        raise FallbackExhaustedError(
            original_model=current_model,
            tried_models=tried_models,
            last_error=last_error,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def resolve_model(
        self,
        requested_model: str,
        failed_models: Optional[Set[str]] = None,
    ) -> Optional[str]:
        """
        Resolve the best available model without executing.

        Returns the first model in the chain (starting with the requested
        model) that is not in failed_models, or None if all are failed.

        Useful for pre-flight checks.
        """
        skipped = failed_models or set()

        if requested_model not in skipped:
            return requested_model

        for fb_model in self.get_chain(requested_model):
            if fb_model not in skipped:
                return fb_model

        return None
