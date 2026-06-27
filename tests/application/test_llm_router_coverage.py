"""Coverage tests for llm_router.py uncovered branches (M045 S01 T03)."""

from __future__ import annotations

import pytest

from active_skill_system.application.llm_router import LLMRouter
from active_skill_system.application.model_registry import ModelRegistry
from active_skill_system.application.model_selector import StageType
from active_skill_system.domain.model_genome import ModelCapability, ModelGenome
from active_skill_system.domain.provider_health import ProviderHealth


def _genome(mid, caps, provider, cost_in=1.0, cost_out=1.0):
    return ModelGenome(
        id=mid, capabilities=frozenset(caps), context_window=100000,
        cost_input_per_1m=cost_in, cost_output_per_1m=cost_out, provider_id=provider,
    )


def _registry(*genomes):
    reg = ModelRegistry()
    for g in genomes:
        reg.register(g)
    return reg


class _FakeProvider:
    def __init__(self, *, default_model="m1", fail=False):
        self.default_model = default_model
        self._fail = fail

    def complete(self, **kwargs):
        if self._fail:
            raise RuntimeError("down")
        return {"ok": True}


# ── Stage preference in _ordered_healthy_models ──────────────────────


def test_stage_preference_filters_to_preferred():
    """SYNTHESIZE prefers THINKING models."""
    thinker = _genome("t1", {ModelCapability.THINKING}, "p1")
    fast = _genome("f1", {ModelCapability.FAST}, "p1")
    reg = _registry(thinker, fast)
    router = LLMRouter(registry=reg, providers={"p1": _FakeProvider()})
    selected = router.select(StageType.SYNTHESIZE, frozenset({ModelCapability.THINKING}))
    assert selected is not None
    assert selected.id == "t1"


def test_select_returns_none_when_all_models_unhealthy():
    g = _genome("m1", {ModelCapability.THINKING}, "p1")
    reg = _registry(g)
    health = {"p1": ProviderHealth(provider_id="p1", consecutive_failures=10)}
    router = LLMRouter(registry=reg, providers={"p1": _FakeProvider()}, health=health)
    assert router.select(StageType.SYNTHESIZE, frozenset({ModelCapability.THINKING})) is None


# ── route_with_fallback edge cases ────────────────────────────────────


def test_route_returns_none_when_no_candidates():
    reg = _registry()  # empty
    router = LLMRouter(registry=reg, providers={"p1": _FakeProvider()})
    result = router.route_with_fallback(
        StageType.SYNTHESIZE, frozenset({ModelCapability.THINKING}),
        {"system": "s", "messages": [], "model": "m1", "max_tokens": 1,
         "temperature": 0, "top_p": 1, "output_schema": None, "timeout_seconds": 1},
    )
    assert result is None


def test_route_returns_none_when_no_required_caps_match():
    g = _genome("m1", {ModelCapability.FAST}, "p1")
    reg = _registry(g)
    router = LLMRouter(registry=reg, providers={"p1": _FakeProvider()})
    result = router.route_with_fallback(
        StageType.VISION_EXTRACTION, frozenset({ModelCapability.VISION}),
        {"system": "s", "messages": [], "model": "m1", "max_tokens": 1,
         "temperature": 0, "top_p": 1, "output_schema": None, "timeout_seconds": 1},
    )
    assert result is None


# ── health() KeyError ─────────────────────────────────────────────────


def test_health_raises_keyerror_on_unknown_provider():
    reg = _registry(_genome("m1", {ModelCapability.FAST}, "p1"))
    router = LLMRouter(registry=reg, providers={"p1": _FakeProvider()})
    with pytest.raises(KeyError):
        router.health("unknown-provider")


# ── _mark_success records timestamp ──────────────────────────────────


def test_route_marks_success_with_timestamp():
    g = _genome("m1", {ModelCapability.FAST}, "p1")
    reg = _registry(g)
    router = LLMRouter(
        registry=reg, providers={"p1": _FakeProvider()},
        max_retries=0, base_backoff=0.0,
    )
    router.route_with_fallback(
        StageType.PARSE, frozenset({ModelCapability.FAST}),
        {"system": "s", "messages": [], "model": "m1", "max_tokens": 1,
         "temperature": 0, "top_p": 1, "output_schema": None, "timeout_seconds": 1},
    )
    assert router.health("p1").last_success_at is not None
    assert router.health("p1").consecutive_failures == 0


# ─_route_with_fallback_or_raise ───────────────────────────────────────


def test_route_or_raise_returns_result_on_success():
    g = _genome("m1", {ModelCapability.FAST}, "p1")
    reg = _registry(g)
    router = LLMRouter(
        registry=reg, providers={"p1": _FakeProvider()},
        max_retries=0, base_backoff=0.0,
    )
    result = router.route_with_fallback_or_raise(
        StageType.PARSE, frozenset({ModelCapability.FAST}),
        {"system": "s", "messages": [], "model": "m1", "max_tokens": 1,
         "temperature": 0, "top_p": 1, "output_schema": None, "timeout_seconds": 1},
    )
    assert result is not None
    assert result.provider_id == "p1"


# ── max_failures threshold configuration ──────────────────────────────


def test_custom_max_failures_threshold():
    g = _genome("m1", {ModelCapability.FAST}, "p1")
    reg = _registry(g)
    health = {"p1": ProviderHealth(provider_id="p1", consecutive_failures=2)}
    # max_failures=5 → 2 < 5 → still healthy
    router = LLMRouter(registry=reg, providers={"p1": _FakeProvider()}, health=health, max_failures=5)
    assert router.select(StageType.PARSE, frozenset({ModelCapability.FAST})) is not None
    # max_failures=1 → 2 >= 1 → unhealthy
    router2 = LLMRouter(registry=reg, providers={"p1": _FakeProvider()}, health=health, max_failures=1)
    assert router2.select(StageType.PARSE, frozenset({ModelCapability.FAST})) is None
