"""L3 Adapter — InMemoryLLMCache (M052 S04).

Dict-based LLM response cache for tests and ephemeral runs.
"""

from __future__ import annotations

from typing import Any

from active_skill_system.application.ports.llm_cache import LLMCache


class InMemoryLLMCache:
    """LLMCache backed by a Python dict. For tests."""

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}

    def get(self, key: str) -> Any | None:
        return self._store.get(key)

    def has(self, key: str) -> bool:
        return key in self._store

    def record(self, key: str, response: Any) -> None:
        self._store[key] = response

    def count(self) -> int:
        return len(self._store)


# InMemoryLLMCache structurally satisfies LLMCache.
_: LLMCache = InMemoryLLMCache()  # type: ignore[assignment]
