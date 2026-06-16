"""JSON stream buffer: accumulate streaming tokens until valid JSON.

Useful for streaming scenarios where structured JSON output is built
token by token (e.g., function calling, structured extraction). The
buffer accumulates tokens and attempts to parse them into a dict
once a complete JSON structure is detected.
"""

from __future__ import annotations

import json
import re


class JSONStreamBuffer:
    """Accumulate streaming tokens and parse valid JSON incrementally.

    The buffer tracks brace/bracket depth to determine when a complete
    JSON value (object or array) has been assembled. On each `feed()`
    call, it appends the token and attempts to parse. Returns the
    parsed dict/list once complete, or None if still incomplete.

    Usage:
        buf = JSONStreamBuffer()
        result = buf.feed('{"')      # None (incomplete)
        result = buf.feed('name')    # None (incomplete)
        result = buf.feed('": "')    # None (incomplete)
        result = buf.feed('Alice"}') # {"name": "Alice"} (complete)
    """

    def __init__(self) -> None:
        self._buffer: str = ""
        self._depth: int = 0
        self._in_string: bool = False
        self._escape_next: bool = False
        self._parse_attempts: int = 0
        self._last_successful_index: int = 0

    def feed(self, token: str) -> dict | list | None:
        """Feed a token into the buffer and attempt to parse complete JSON.

        Args:
            token: The next token to append.

        Returns:
            Parsed dict or list if complete JSON was assembled, None otherwise.
        """
        self._buffer += token
        self._track_depth(token)

        # Only attempt to parse if the buffer looks like it might be complete
        # (depth is back to 0)
        if self._depth == 0 and len(self._buffer.strip()) > 0:
            self._parse_attempts += 1
            return self._try_parse()

        return None

    def _track_depth(self, token: str) -> None:
        """Track brace/bracket depth and string state as tokens arrive."""
        for char in token:
            if self._escape_next:
                self._escape_next = False
                continue

            if char == '\\' and self._in_string:
                self._escape_next = True
                continue

            if char == '"' and not self._escape_next:
                self._in_string = not self._in_string
                continue

            if self._in_string:
                continue

            if char in ('{', '['):
                self._depth += 1
            elif char in ('}', ']'):
                self._depth = max(0, self._depth - 1)

    def _try_parse(self) -> dict | list | None:
        """Attempt to parse the buffer content as JSON.

        Tries the full buffer first, then attempts to extract and parse
        the first complete JSON value using regex.

        Returns:
            Parsed dict/list or None if parsing fails.
        """
        stripped = self._buffer.strip()
        if not stripped:
            return None

        # Try direct parse first
        try:
            result = json.loads(stripped)
            self._last_successful_index = len(self._buffer)
            return result
        except json.JSONDecodeError:
            pass

        # Try to extract the first complete JSON value
        # Match a top-level object
        obj_result = self._extract_json_object(stripped)
        if obj_result is not None:
            return obj_result

        # Match a top-level array
        arr_result = self._extract_json_array(stripped)
        if arr_result is not None:
            return arr_result

        return None

    def _extract_json_object(self, text: str) -> dict | None:
        """Extract and parse the first complete JSON object from text."""
        if not text.startswith('{'):
            return None

        depth = 0
        in_string = False
        escape_next = False

        for i, char in enumerate(text):
            if escape_next:
                escape_next = False
                continue

            if char == '\\' and in_string:
                escape_next = True
                continue

            if char == '"':
                in_string = not in_string
                continue

            if in_string:
                continue

            if char == '{':
                depth += 1
            elif char == '}':
                depth -= 1
                if depth == 0:
                    candidate = text[:i + 1]
                    try:
                        result = json.loads(candidate)
                        self._last_successful_index = i + 1
                        return result
                    except json.JSONDecodeError:
                        return None

        return None

    def _extract_json_array(self, text: str) -> list | None:
        """Extract and parse the first complete JSON array from text."""
        if not text.startswith('['):
            return None

        depth = 0
        in_string = False
        escape_next = False

        for i, char in enumerate(text):
            if escape_next:
                escape_next = False
                continue

            if char == '\\' and in_string:
                escape_next = True
                continue

            if char == '"':
                in_string = not in_string
                continue

            if in_string:
                continue

            if char == '[':
                depth += 1
            elif char == ']':
                depth -= 1
                if depth == 0:
                    candidate = text[:i + 1]
                    try:
                        result = json.loads(candidate)
                        self._last_successful_index = i + 1
                        return result
                    except json.JSONDecodeError:
                        return None

        return None

    def reset(self) -> None:
        """Reset the buffer to empty state."""
        self._buffer = ""
        self._depth = 0
        self._in_string = False
        self._escape_next = False
        self._parse_attempts = 0
        self._last_successful_index = 0

    @property
    def buffer(self) -> str:
        """Current accumulated buffer content."""
        return self._buffer

    @property
    def parse_attempts(self) -> int:
        """Number of parse attempts made."""
        return self._parse_attempts

    @property
    def is_in_string(self) -> bool:
        """Whether we are currently inside a JSON string."""
        return self._in_string

    @property
    def depth(self) -> int:
        """Current nesting depth (brace/bracket count)."""
        return self._depth

    def get_remaining(self) -> str:
        """Get any buffer content after the last successful parse."""
        if self._last_successful_index > 0 and self._last_successful_index < len(self._buffer):
            return self._buffer[self._last_successful_index:]
        return ""
