"""Backpressure controller for streaming token pipelines.

When the consumer is slower than the producer, the bounded queue
blocks the producer to prevent unbounded memory growth. Tracks
production and consumption statistics including dropped tokens.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque


class BackpressureController:
    """Bounded-queue backpressure for producer-consumer token streams.

    The producer calls `produce()` to add tokens; if the queue is full,
    it blocks (asyncio) until the consumer frees space. The consumer
    calls `consume()` to retrieve tokens; if the queue is empty, it
    waits until a producer adds a token.

    Tracks:
    - Total tokens produced
    - Total tokens consumed
    - Dropped tokens (when queue overflows with drop strategy)
    - High-water mark (maximum queue depth observed)

    Usage:
        bp = BackpressureController(max_size=100)
        # Producer (in one task):
        await bp.produce("Hello")
        # Consumer (in another task):
        token = await bp.consume()
    """

    def __init__(self, max_size: int = 100) -> None:
        """Initialize the backpressure controller.

        Args:
            max_size: Maximum queue size before producer blocks.
        """
        if max_size < 1:
            raise ValueError("max_size must be >= 1")
        self._max_size = max_size
        self._queue: deque[str] = deque()
        self._not_full = asyncio.Condition()
        self._not_empty = asyncio.Condition()
        self._produced_count: int = 0
        self._consumed_count: int = 0
        self._dropped_count: int = 0
        self._high_water_mark: int = 0
        self._closed: bool = False
        self._start_time: float = time.time()
        self._total_wait_producer: float = 0.0
        self._total_wait_consumer: float = 0.0

    async def produce(self, token: str) -> None:
        """Add a token to the queue. Blocks if the queue is full.

        Args:
            token: The token string to enqueue.
        """
        async with self._not_full:
            while len(self._queue) >= self._max_size and not self._closed:
                wait_start = time.time()
                await self._not_full.wait()
                self._total_wait_producer += time.time() - wait_start

            if self._closed:
                return

            self._queue.append(token)
            self._produced_count += 1

            # Update high-water mark
            qlen = len(self._queue)
            if qlen > self._high_water_mark:
                self._high_water_mark = qlen

        # Notify waiting consumers
        async with self._not_empty:
            self._not_empty.notify(1)

    async def consume(self) -> str:
        """Retrieve a token from the queue. Blocks if the queue is empty.

        Returns:
            The next token string.

        Raises:
            asyncio.QueueEmpty: If the stream is closed and the queue is empty.
        """
        async with self._not_empty:
            while len(self._queue) == 0:
                if self._closed:
                    raise asyncio.QueueEmpty("Stream is closed and queue is empty")
                wait_start = time.time()
                await self._not_empty.wait()
                self._total_wait_consumer += time.time() - wait_start

            token = self._queue.popleft()
            self._consumed_count += 1

        # Notify waiting producers that space is available
        async with self._not_full:
            self._not_full.notify(1)

        return token

    async def try_produce(self, token: str) -> bool:
        """Non-blocking produce. Returns False if the queue is full.

        Args:
            token: The token string to enqueue.

        Returns:
            True if the token was enqueued, False if the queue was full.
        """
        if len(self._queue) >= self._max_size:
            return False
        await self.produce(token)
        return True

    async def try_consume(self) -> str | None:
        """Non-blocking consume. Returns None if the queue is empty.

        Returns:
            The next token, or None if the queue is empty.
        """
        async with self._not_empty:
            if len(self._queue) == 0:
                return None
            token = self._queue.popleft()
            self._consumed_count += 1
        async with self._not_full:
            self._not_full.notify(1)
        return token

    async def close(self) -> None:
        """Close the stream. Wakes up any waiting consumers."""
        self._closed = True
        async with self._not_empty:
            self._not_empty.notify_all()
        async with self._not_full:
            self._not_full.notify_all()

    @property
    def produced(self) -> int:
        """Total tokens produced."""
        return self._produced_count

    @property
    def consumed(self) -> int:
        """Total tokens consumed."""
        return self._consumed_count

    @property
    def dropped(self) -> int:
        """Total tokens dropped."""
        return self._dropped_count

    @property
    def high_water_mark(self) -> int:
        """Maximum queue depth observed."""
        return self._high_water_mark

    @property
    def queue_size(self) -> int:
        """Current queue depth."""
        return len(self._queue)

    @property
    def is_closed(self) -> bool:
        """Whether the stream has been closed."""
        return self._closed

    def stats(self) -> dict:
        """Get comprehensive backpressure statistics.

        Returns:
            Dictionary with produced, consumed, dropped, high_water_mark,
            current_size, max_size, elapsed_seconds, throughput_produce,
            throughput_consume, queue_utilization_pct.
        """
        elapsed = time.time() - self._start_time
        return {
            "produced": self._produced_count,
            "consumed": self._consumed_count,
            "dropped": self._dropped_count,
            "high_water_mark": self._high_water_mark,
            "current_size": len(self._queue),
            "max_size": self._max_size,
            "elapsed_seconds": round(elapsed, 3),
            "throughput_produce_per_sec": round(self._produced_count / elapsed, 2) if elapsed > 0 else 0,
            "throughput_consume_per_sec": round(self._consumed_count / elapsed, 2) if elapsed > 0 else 0,
            "queue_utilization_pct": round(len(self._queue) / self._max_size * 100, 1),
            "producer_wait_sec": round(self._total_wait_producer, 3),
            "consumer_wait_sec": round(self._total_wait_consumer, 3),
        }
