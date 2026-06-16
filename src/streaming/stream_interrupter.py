"""Stream interruption handler: manage stream lifecycle with interruption/recovery.

Tracks active streams, supports interruption with reason codes,
partial text accumulation, and resumption with replay of
previously generated content.
"""

from __future__ import annotations

import asyncio
import time
from enum import Enum
from typing import Any


class InterruptionReason(Enum):
    """Reasons for stream interruption."""
    USER_CANCELLED = "user_cancelled"
    SECURITY_BLOCKED = "security_blocked"
    TIMEOUT = "timeout"
    ERROR = "error"
    RATE_LIMIT = "rate_limit"
    SYSTEM_SHUTDOWN = "system_shutdown"


class StreamInterruptionHandler:
    """Handle stream interruption and recovery.

    Manages the lifecycle of streaming connections, including:
    - Starting and tracking streams by ID
    - Interrupting streams with specific reasons
    - Accumulating partial text during streaming
    - Resuming streams with replay of partial content
    - Token counting per stream

    Usage:
        handler = StreamInterruptionHandler()
        await handler.start_stream("req-001")
        # ... streaming tokens ...
        await handler.interrupt("req-001", "user_cancelled")
        partial = handler.get_partial_text("req-001")
        # If can_resume:
        await handler.resume_stream("req-001")
    """

    def __init__(self) -> None:
        self._streams: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def start_stream(self, stream_id: str) -> None:
        """Register a new streaming session.

        Args:
            stream_id: Unique identifier for the stream.

        Raises:
            ValueError: If the stream_id is already in use.
        """
        async with self._lock:
            if stream_id in self._streams:
                raise ValueError(f"Stream '{stream_id}' already exists")
            self._streams[stream_id] = {
                "partial_text": "",
                "token_count": 0,
                "is_active": True,
                "interrupted": False,
                "interruption_reason": None,
                "interruption_time": None,
                "started_at": time.time(),
                "events": [],
            }

    async def interrupt(self, stream_id: str, reason: str) -> bool:
        """Interrupt an active stream.

        Args:
            stream_id: The stream to interrupt.
            reason: Reason string (see InterruptionReason enum).

        Returns:
            True if the stream was interrupted, False if not found
            or already interrupted.
        """
        async with self._lock:
            if stream_id not in self._streams:
                return False

            stream = self._streams[stream_id]
            if not stream["is_active"]:
                return False

            stream["is_active"] = False
            stream["interrupted"] = True
            stream["interruption_reason"] = reason
            stream["interruption_time"] = time.time()
            stream["events"].append({
                "event": "interrupted",
                "reason": reason,
                "timestamp": stream["interruption_time"],
                "token_count": stream["token_count"],
            })

            return True

    async def add_token(self, stream_id: str, token: str) -> bool:
        """Add a token to the stream's partial text accumulator.

        Args:
            stream_id: The stream receiving the token.
            token: The token text.

        Returns:
            True if added, False if the stream is not active.
        """
        async with self._lock:
            if stream_id not in self._streams:
                return False
            stream = self._streams[stream_id]
            if not stream["is_active"]:
                return False

            stream["partial_text"] += token
            stream["token_count"] += 1
            return True

    async def can_resume(self, stream_id: str) -> bool:
        """Check whether a stream can be resumed.

        A stream can be resumed if it was interrupted for a recoverable
        reason (user_cancelled, timeout, rate_limit) but NOT for
        security_blocked or system_shutdown.

        Args:
            stream_id: The stream to check.

        Returns:
            True if the stream can be resumed.
        """
        async with self._lock:
            if stream_id not in self._streams:
                return False
            stream = self._streams[stream_id]

            if not stream["interrupted"]:
                return False

            # These reasons are non-resumable
            non_resumable = {
                InterruptionReason.SECURITY_BLOCKED.value,
                InterruptionReason.SYSTEM_SHUTDOWN.value,
            }
            if stream["interruption_reason"] in non_resumable:
                return False

            return True

    async def resume_stream(self, stream_id: str) -> str:
        """Resume a previously interrupted stream.

        Re-activates the stream and returns the partial text that was
        generated before interruption, which can be replayed to the client.

        Args:
            stream_id: The stream to resume.

        Returns:
            The partial text generated before interruption.

        Raises:
            ValueError: If the stream cannot be resumed.
        """
        async with self._lock:
            if stream_id not in self._streams:
                raise ValueError(f"Stream '{stream_id}' not found")

            if not await self.can_resume(stream_id):
                stream = self._streams[stream_id]
                reason = stream.get("interruption_reason", "unknown")
                raise ValueError(f"Stream '{stream_id}' cannot be resumed (reason: {reason})")

            stream = self._streams[stream_id]
            stream["is_active"] = True
            stream["interrupted"] = False
            stream["interruption_reason"] = None
            stream["interruption_time"] = None
            stream["events"].append({
                "event": "resumed",
                "timestamp": time.time(),
                "token_count": stream["token_count"],
            })

            return stream["partial_text"]

    def get_partial_text(self, stream_id: str) -> str:
        """Get the partial text accumulated for a stream.

        Args:
            stream_id: The stream to query.

        Returns:
            The partial text string, or empty string if not found.
        """
        if stream_id not in self._streams:
            return ""
        return self._streams[stream_id]["partial_text"]

    def get_token_count(self, stream_id: str) -> int:
        """Get the token count for a stream.

        Args:
            stream_id: The stream to query.

        Returns:
            Token count, or 0 if not found.
        """
        if stream_id not in self._streams:
            return 0
        return self._streams[stream_id]["token_count"]

    def get_stream_info(self, stream_id: str) -> dict | None:
        """Get full stream metadata.

        Args:
            stream_id: The stream to query.

        Returns:
            Dictionary with stream metadata, or None if not found.
        """
        if stream_id not in self._streams:
            return None
        s = self._streams[stream_id]
        return {
            "stream_id": stream_id,
            "is_active": s["is_active"],
            "interrupted": s["interrupted"],
            "interruption_reason": s["interruption_reason"],
            "token_count": s["token_count"],
            "partial_text_length": len(s["partial_text"]),
            "started_at": s["started_at"],
            "interruption_time": s.get("interruption_time"),
            "event_count": len(s["events"]),
        }

    async def cleanup_stream(self, stream_id: str) -> bool:
        """Remove a completed stream from tracking.

        Args:
            stream_id: The stream to clean up.

        Returns:
            True if the stream was removed, False if not found.
        """
        async with self._lock:
            if stream_id in self._streams:
                del self._streams[stream_id]
                return True
            return False

    async def cleanup_inactive_streams(self, max_age_seconds: float = 3600) -> int:
        """Clean up inactive streams older than max_age_seconds.

        Args:
            max_age_seconds: Maximum age before cleanup.

        Returns:
            Number of streams cleaned up.
        """
        now = time.time()
        to_remove: list[str] = []

        async with self._lock:
            for sid, stream in self._streams.items():
                if not stream["is_active"]:
                    age = now - stream.get("interruption_time", stream["started_at"])
                    if age > max_age_seconds:
                        to_remove.append(sid)

            for sid in to_remove:
                del self._streams[sid]

        return len(to_remove)

    @property
    def active_stream_count(self) -> int:
        """Number of currently active streams."""
        return sum(1 for s in self._streams.values() if s["is_active"])

    @property
    def total_stream_count(self) -> int:
        """Total number of tracked streams."""
        return len(self._streams)
