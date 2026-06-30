"""Tests for M052 S04 — LLMCache port + InMemoryLLMCache."""

from __future__ import annotations

from active_skill_system.adapters.inmemory_llm_cache import InMemoryLLMCache
from active_skill_system.application.ports.llm_cache import LLMCache, cache_key


def test_inmemory_llm_cache_satisfies_protocol() -> None:
    assert isinstance(InMemoryLLMCache(), LLMCache)


def test_cache_key_deterministic() -> None:
    k1 = cache_key(model="m", system="s", prompt="p")
    k2 = cache_key(model="m", system="s", prompt="p")
    assert k1 == k2


def test_cache_key_different_inputs_different_keys() -> None:
    k1 = cache_key(model="m1", system="s", prompt="p")
    k2 = cache_key(model="m2", system="s", prompt="p")
    assert k1 != k2


def test_cache_key_includes_temperature() -> None:
    k1 = cache_key(model="m", system="s", prompt="p", temperature=0.0)
    k2 = cache_key(model="m", system="s", prompt="p", temperature=0.7)
    assert k1 != k2


def test_cache_key_includes_max_tokens() -> None:
    k1 = cache_key(model="m", system="s", prompt="p", max_tokens=100)
    k2 = cache_key(model="m", system="s", prompt="p", max_tokens=200)
    assert k1 != k2


def test_inmemory_get_miss_returns_none() -> None:
    c = InMemoryLLMCache()
    assert c.get("nonexistent") is None


def test_inmemory_record_and_get() -> None:
    c = InMemoryLLMCache()
    c.record("key1", {"response": "hello"})
    assert c.get("key1") == {"response": "hello"}


def test_inmemory_has() -> None:
    c = InMemoryLLMCache()
    c.record("key1", "val")
    assert c.has("key1") is True
    assert c.has("key2") is False


def test_inmemory_record_overwrites() -> None:
    c = InMemoryLLMCache()
    c.record("key1", "old")
    c.record("key1", "new")
    assert c.get("key1") == "new"


def test_inmemory_count() -> None:
    c = InMemoryLLMCache()
    c.record("k1", "v1")
    c.record("k2", "v2")
    assert c.count() == 2


def test_cache_key_length_32() -> None:
    k = cache_key(model="m", system="s", prompt="p")
    assert len(k) == 32
