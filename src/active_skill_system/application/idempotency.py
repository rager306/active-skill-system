"""L2 Application — IdempotencyStore (M014 S01, F-13).

Deduplicates requests by IdempotencyKey. When a request with the same key
is submitted twice, the second call returns the cached result instead of
re-executing. Simple dict-based; production could use Redis/DB.

Pure application. Depends on domain only (R002).
"""

from __future__ import annotations

from typing import Any


class IdempotencyStore:
    """Append-once key-value store for idempotent request deduplication.

    ``register(key, result)`` returns True if the key is new (stored),
    False if a duplicate (existing result preserved). ``get(key)`` returns
    the stored result or None.
    """

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}

    def register(self, key: str, result: Any) -> bool:
        """Store result under key. Returns True if new, False if duplicate."""
        if key in self._store:
            return False
        self._store[key] = result
        return True

    def get(self, key: str) -> Any | None:
        """Return the stored result for key, or None."""
        return self._store.get(key)

    def has(self, key: str) -> bool:
        """Check if key is registered."""
        return key in self._store

    def clear(self) -> None:
        """Clear all entries (for testing)."""
        self._store.clear()
