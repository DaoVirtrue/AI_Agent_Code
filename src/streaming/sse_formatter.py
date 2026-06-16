"""Server-Sent Events (SSE) formatter for streaming responses.

Formats events according to the SSE specification with support for
token streaming, completion signaling, error reporting, and heartbeat
keep-alive events.
"""

from __future__ import annotations

import json
import time


class SSEFormatter:
    """Server-Sent Events (SSE) formatter.

    Produces SSE-compliant event strings for streaming token output,
    completion events, error events, and heartbeat keep-alive pings.

    SSE wire format:
        event: <event_type>\\n
        id: <event_id>\\n
        retry: <retry_ms>\\n
        data: <json_data>\\n
        \\n
    """

    def __init__(self) -> None:
        self._event_counter: int = 0

    def format_event(self, event_type: str, data: dict,
                     id: str | None = None, retry: int | None = None) -> str:
        """Format a complete SSE event.

        Args:
            event_type: The event name (e.g., "token", "done", "error").
            data: Dictionary payload for the data field.
            id: Optional event ID.
            retry: Optional reconnection time in milliseconds.

        Returns:
            A fully formatted SSE string ready to send over HTTP.
        """
        lines: list[str] = []

        if event_type:
            lines.append(f"event: {event_type}")

        if id is not None:
            lines.append(f"id: {id}")
        else:
            self._event_counter += 1
            lines.append(f"id: {self._event_counter}")

        if retry is not None:
            lines.append(f"retry: {retry}")

        # Serialize the data payload
        data_str = json.dumps(data, ensure_ascii=False)
        lines.append(f"data: {data_str}")

        # Empty line signals end of event
        lines.append("")

        return "\n".join(lines)

    def token_event(self, token: str) -> str:
        """Format a streaming token event.

        Args:
            token: The text token being streamed.

        Returns:
            SSE-formatted token event string.
        """
        return self.format_event("token", {
            "token": token,
            "timestamp": time.time(),
        })

    def done_event(self, metadata: dict | None = None) -> str:
        """Format a stream completion [DONE] event.

        Args:
            metadata: Optional metadata to include (token count, latency, etc.).

        Returns:
            SSE-formatted done event string.
        """
        data: dict = {"status": "done", "timestamp": time.time()}
        if metadata:
            data.update(metadata)
        return self.format_event("done", data)

    def error_event(self, error: str, code: str = "unknown") -> str:
        """Format a stream error event.

        Args:
            error: Human-readable error description.
            code: Machine-readable error code.

        Returns:
            SSE-formatted error event string.
        """
        return self.format_event("error", {
            "error": error,
            "code": code,
            "timestamp": time.time(),
        })

    def heartbeat_event(self) -> str:
        """Format a heartbeat/keep-alive event.

        Returns:
            SSE-formatted heartbeat event with a comment style line
            that keeps the HTTP connection alive without triggering
            client-side event handlers.
        """
        return ": heartbeat\n\n"

    def format_sse(self, event_str: str) -> str:
        """Add SSE framing to an event string.

        Ensures the event string ends with the required double newline.

        Args:
            event_str: An event string to frame.

        Returns:
            Properly framed SSE string.
        """
        if not event_str.endswith("\n\n"):
            if event_str.endswith("\n"):
                event_str += "\n"
            else:
                event_str += "\n\n"
        return event_str

    def metadata_event(self, metadata: dict) -> str:
        """Format a metadata event (sent before stream starts).

        Args:
            metadata: Dictionary with stream metadata (model, request_id, etc.).

        Returns:
            SSE-formatted metadata event string.
        """
        return self.format_event("metadata", {
            **metadata,
            "timestamp": time.time(),
        })

    def stream_start_event(self, request_id: str, model: str = "") -> str:
        """Format a stream start event.

        Args:
            request_id: Unique request identifier.
            model: Model name being used.

        Returns:
            SSE-formatted stream_start event.
        """
        data: dict = {"request_id": request_id, "status": "streaming"}
        if model:
            data["model"] = model
        return self.format_event("stream_start", data)

    def stream_end_event(self, request_id: str, total_tokens: int = 0,
                         finish_reason: str = "stop") -> str:
        """Format a stream end event with summary.

        Args:
            request_id: Unique request identifier.
            total_tokens: Total tokens streamed.
            finish_reason: Why the stream ended ("stop", "length", "interrupted", "error").

        Returns:
            SSE-formatted stream_end event.
        """
        return self.format_event("stream_end", {
            "request_id": request_id,
            "total_tokens": total_tokens,
            "finish_reason": finish_reason,
            "timestamp": time.time(),
        })

    def reset_counter(self) -> None:
        """Reset the event counter to zero."""
        self._event_counter = 0
