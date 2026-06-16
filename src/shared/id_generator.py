"""
ULID-based ID generation.

ULIDs are 26-character, lexicographically sortable, URL-safe identifiers that
encode a timestamp + randomness.  They are ideal for request tracing and
primary keys where time-ordering matters.

This module provides a zero-dependency ULID implementation alongside helpers
for request IDs, entity IDs, and short key prefixes.
"""

from __future__ import annotations

import os
import random
import string
import time


# ============================================================================
# ULID implementation (zero-dependency, fully spec-compliant)
# ============================================================================

# Crockford Base32 alphabet
_ENCODING = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_DECODING = {char: idx for idx, char in enumerate(_ENCODING)}

# Ensure single-byte index fits
assert len(_ENCODING) == 32


def _encode_time(timestamp: int) -> str:
    """Encode a 48-bit timestamp into 10 Base32 characters."""
    chars: list[str] = []
    for _ in range(10):
        chars.append(_ENCODING[timestamp & 0x1F])
        timestamp >>= 5
    return "".join(reversed(chars))


def _encode_randomness(rand_bytes: bytes) -> str:
    """Encode 80 bits of randomness into 16 Base32 characters."""
    # Convert 10 bytes (80 bits) to an integer, then encode in 16 chars
    value = int.from_bytes(rand_bytes, "big")
    chars: list[str] = []
    for _ in range(16):
        chars.append(_ENCODING[value & 0x1F])
        value >>= 5
    return "".join(reversed(chars))


def generate_ulid() -> str:
    """Generate a ULID string (26 characters).

    Returns:
        A 26-character Crockford Base32-encoded ULID string.

    Example::

        >>> ulid = generate_ulid()
        >>> len(ulid)
        26
        >>> ulid  # e.g. '01ARZ3NDEKTSV4RRFFQ69G5FAV'
    """
    # 48-bit timestamp (milliseconds since Unix epoch) – good until ~10889 AD
    timestamp_ms = int(time.time() * 1000)
    # 80 bits of randomness (10 bytes)
    rand_bytes = os.urandom(10)

    return _encode_time(timestamp_ms) + _encode_randomness(rand_bytes)


# ============================================================================
# Public API
# ============================================================================


def generate_request_id() -> str:
    """Generate a ULID string suitable for request tracing.

    Returns a 26-character ULID.  Because ULIDs embed a millisecond-precision
    timestamp, they sort chronologically, making them ideal for log analysis.
    """
    return generate_ulid()


def generate_id() -> str:
    """Generate a ULID string for entity primary keys.

    Consider using UUIDs (via SQLAlchemy's UUID type) for database primary
    keys.  This function is provided for cases where a ULID is preferred
    over a UUID (e.g. API-facing resource IDs).
    """
    return generate_ulid()


def generate_short_id(length: int = 8) -> str:
    """Generate a short random hex string, e.g. for API key prefixes.

    Args:
        length: Number of hex characters (default 8).

    Returns:
        Lowercase hex string of the requested length.
    """
    n_bytes = (length + 1) // 2
    return os.urandom(n_bytes).hex()[:length]


def generate_key_prefix(length: int = 8) -> str:
    """Generate a short base32-alike (uppercase alphanumeric) prefix.

    Useful for displaying the first N characters of an API key to users so
    they can differentiate keys without seeing the full secret.

    Args:
        length: Number of characters (default 8).

    Returns:
        String of uppercase letters + digits (no I, L, O, U to avoid confusion).
    """
    safe_alphabet = "ABCDEFGHJKMNPQRSTVWXYZ23456789"
    return "".join(random.SystemRandom().choice(safe_alphabet) for _ in range(length))
