"""The IDs that name cache entries, derived from a key."""

import hashlib
import re

_ID_LENGTH = 12
_ID_PATTERN = re.compile(f"[0-9a-f]{{{_ID_LENGTH}}}")


def cache_id(key: str) -> str:
    """Return the ID for `key`: the first 12 hex characters of the SHA-256 of its UTF-8 bytes."""
    return hashlib.sha256(key.encode()).hexdigest()[:_ID_LENGTH]


def is_cache_id(text: str) -> bool:
    """Return whether `text` has the shape `cache_id` returns, 12 lower-case hex characters."""
    return _ID_PATTERN.fullmatch(text) is not None
