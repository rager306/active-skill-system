"""L2 Application — LLMCache port (M052 S04).

Cache for LLM responses keyed by (model + prompt + params). Makes fork-and-diff
cheap: shared prefix events replay from cache without new LLM calls.

Adapters:
  - InMemoryLLMCache — tests, default.
  - SQLiteLLMCache — disk persistence (S05).

The cache key is a deterministic hash of (model, system, prompt, max_tokens,
temperature). Same inputs → same key → cache hit.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LLMCache(Protocol):
    """LLM response cache. Implementations MUST be deterministic on key."""

    def get(self, key: str) -> Any | None:
        """Return cached response for key, or None if not in cache."""
        ...

    def has(self, key: str) -> bool:
        """True if key is in the cache."""
        ...

    def record(self, key: str, response: Any) -> None:
        """Store a response for key. Idempotent on key."""
        ...

    def count(self) -> int:
        """Number of cached entries."""
        ...


def cache_key(
    *,
    model: str,
    system: str,
    prompt: str,
    max_tokens: int = 524_288,
    temperature: float = 0.0,
) -> str:
    """Deterministic cache key from LLM request parameters.

    Same inputs → same key. Used by PlainLLMStrategy to check cache before
    calling the provider.
    """
    import hashlib

    raw = f"{model}|{system}|{prompt}|{max_tokens}|{temperature}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
