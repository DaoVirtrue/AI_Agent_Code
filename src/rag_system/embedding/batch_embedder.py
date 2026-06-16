"""Batch embedding with retry logic and async concurrency control."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .registry import BaseEmbedder

logger = logging.getLogger(__name__)


@dataclass
class BatchEmbeddingResult:
    """Result of a batch embedding operation."""
    embeddings: np.ndarray
    total_texts: int
    successful: int
    failed: int
    total_time_ms: float
    errors: list[str] = field(default_factory=list)


class BatchEmbedder:
    """Batch embedding with retries, rate limiting, and progress tracking.

    Features:
    - Automatic batching of large text lists
    - Exponential backoff retry on failure
    - Rate limiting via semaphore
    - Progress callbacks
    - Graceful error handling
    """

    def __init__(
        self,
        embedder: BaseEmbedder,
        batch_size: int = 32,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        max_concurrent: int = 5,
        rate_limit_per_second: Optional[float] = None,
    ):
        """Initialize batch embedder.

        Args:
            embedder: BaseEmbedder instance
            batch_size: Texts per embedding API call
            max_retries: Max retry attempts on failure
            retry_delay: Base delay between retries (exponential backoff)
            max_concurrent: Max concurrent embedding calls
            rate_limit_per_second: Optional rate limit
        """
        self.embedder = embedder
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._rate_limit = rate_limit_per_second
        self._last_call_time = 0.0
        logger.info(
            "BatchEmbedder: model=%s, batch=%d, retries=%d, concurrent=%d",
            embedder.name, batch_size, max_retries, max_concurrent
        )

    async def embed(self, texts: list[str], progress_callback=None) -> BatchEmbeddingResult:
        """Embed a list of texts with batching and retry.

        Args:
            texts: List of texts to embed
            progress_callback: Optional async callback(completed, total)

        Returns:
            BatchEmbeddingResult with embeddings and stats
        """
        if not texts:
            return BatchEmbeddingResult(
                embeddings=np.array([]),
                total_texts=0,
                successful=0,
                failed=0,
                total_time_ms=0.0,
            )

        start_time = time.time()
        total = len(texts)
        successful = 0
        failed = 0
        errors: list[str] = []
        all_embeddings: list[np.ndarray] = []

        # Split into batches
        batches = [
            texts[i:i + self.batch_size]
            for i in range(0, total, self.batch_size)
        ]

        # Process batches with concurrency control
        tasks = []
        for i, batch in enumerate(batches):
            task = self._embed_batch_with_retry(batch, i)
            tasks.append(task)

        # Gather results with progress tracking
        results = []
        for i, coro in enumerate(asyncio.as_completed(tasks)):
            batch_result = await coro
            results.append(batch_result)
            if progress_callback:
                await progress_callback(i + 1, len(tasks))

        # Sort results by batch index to maintain order
        results.sort(key=lambda x: x[0])

        for _, embedding, err in results:
            if embedding is not None:
                all_embeddings.append(embedding)
                successful += embedding.shape[0]
            else:
                failed += len(batches[len(all_embeddings)])
                if err:
                    errors.append(err)

        # Concatenate all embeddings
        if all_embeddings:
            final_embeddings = np.concatenate(all_embeddings, axis=0)
        else:
            final_embeddings = np.array([])

        total_time_ms = (time.time() - start_time) * 1000

        result = BatchEmbeddingResult(
            embeddings=final_embeddings,
            total_texts=total,
            successful=successful,
            failed=failed,
            total_time_ms=total_time_ms,
            errors=errors,
        )

        logger.info(
            "Batch embedding completed: %d/%d texts, %.0fms, %d errors",
            successful, total, total_time_ms, failed
        )

        return result

    async def _embed_batch_with_retry(self, batch: list[str], batch_idx: int) -> tuple[int, Optional[np.ndarray], Optional[str]]:
        """Embed a single batch with retry logic."""
        last_error = None

        for attempt in range(self.max_retries + 1):
            try:
                # Rate limiting
                if self._rate_limit:
                    await self._rate_limit_wait()

                async with self._semaphore:
                    embeddings = await self.embedder.embed(batch)

                return (batch_idx, embeddings, None)

            except Exception as e:
                last_error = str(e)
                if attempt < self.max_retries:
                    delay = self.retry_delay * (2 ** attempt)
                    logger.warning(
                        "Batch %d attempt %d/%d failed: %s. Retrying in %.1fs...",
                        batch_idx, attempt + 1, self.max_retries + 1, e, delay
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "Batch %d failed after %d attempts: %s",
                        batch_idx, self.max_retries + 1, e
                    )

        return (batch_idx, None, last_error)

    async def _rate_limit_wait(self):
        """Implement rate limiting with token bucket approach."""
        if self._rate_limit is None:
            return

        now = time.time()
        elapsed = now - self._last_call_time
        min_interval = 1.0 / self._rate_limit

        if elapsed < min_interval:
            await asyncio.sleep(min_interval - elapsed)

        self._last_call_time = time.time()

    async def embed_single(self, text: str) -> np.ndarray:
        """Embed a single text (convenience method)."""
        result = await self.embed([text])
        if result.successful == 1 and result.embeddings.shape[0] > 0:
            return result.embeddings[0]
        raise RuntimeError(f"Failed to embed text: {result.errors}")

    def estimate_cost(self, num_tokens: int, price_per_1k: float = 0.0001) -> float:
        """Estimate embedding cost."""
        return (num_tokens / 1000) * price_per_1k
