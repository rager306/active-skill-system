"""Tests for LLMRouter (M038 S01 T04).

Verifies cost-aware multi-provider selection, fallback on failure, health
skipping, and the required-constructor contract (layering gotcha from M016).
Uses fake providers (no real adapter imports) so the application layer stays
infra-free.
"""

from __future__ import annotations

import pytest

from active_skill_system.application.llm_router import LLMRouter, RoutingResult
from active_skill_system.application.model_registry import ModelRegistry
from active_skill_system.application.model_selector import StageType
from active_skill_system.domain.model_genome import ModelCapability, ModelGenome
from active_skill_system.domain.provider_health import ProviderHealth


class _FakeProvider:
    """Minimal LLMProviderPort stand-in for tests."""

    def __init__(self, *, default_model: str = "m1", fail: bool = False):
        self.default_model = default_model
        self._fail = fail

    def complete(self, **kwargs):  # noqa: ANN003
        if self._fail:
            raise RuntimeError("provider down")
        return {"ok": True, "model": self.default_model}


def _genome(mid, caps, provider, cost_in=1.0, cost_out=1.0):
    return ModelGenome(
        id=mid,
        capabilities=frozenset(caps),
        context_window=100000,
        cost_input_per_1m=cost_in,
        cost_output_per_1m=cost_out,
        provider_id=provider,
    )


def _registry_with(*genomes):
    reg = ModelRegistry()
    for g in genomes:
        reg.register(g)
    return reg


# ── Constructor contract (layering gotcha) ────────────────────────────


def test_init_rejects_missing_registry():
    with pytest.raises(TypeError):
        LLMRouter(registry=None, providers={"p": _FakeProvider()})  # type: ignore[arg-type]


def test_init_rejects_empty_providers():
    with pytest.raises(ValueError):
        LLMRouter(registry=ModelRegistry(), providers={})


def test_init_rejects_non_provider_values():
    with pytest.raises(TypeError):
        LLMRouter(registry=ModelRegistry(), providers={"p": "not a provider"})  # type: ignore[arg-type]


# ── Selection ─────────────────────────────────────────────────────────


def test_select_picks_cheapest_matching_model_across_providers():
    cheap = _genome("m1", {ModelCapability.THINKING}, "router", cost_in=1.0, cost_out=1.0)
    pricy = _genome("m2", {ModelCapability.THINKING}, "router", cost_in=5.0, cost_out=5.0)
    reg = _registry_with(pricy, cheap)
    router = LLMRouter(registry=reg, providers={"router": _FakeProvider()})
    selected = router.select(StageType.SYNTHESIZE, frozenset({ModelCapability.THINKING}))
    assert selected is not None
    assert selected.id == "m1"


def test_select_skips_unhealthy_provider():
    cheap_unhealthy = _genome("m1", {ModelCapability.THINKING}, "router", cost_in=1.0, cost_out=1.0)
    healthy = _genome("m2", {ModelCapability.THINKING}, "fallback", cost_in=3.0, cost_out=3.0)
    reg = _registry_with(cheap_unhealthy, healthy)
    health = {"router": ProviderHealth(provider_id="router", consecutive_failures=3)}
    router = LLMRouter(registry=reg, providers={"router": _FakeProvider(), "fallback": _FakeProvider()}, health=health)
    selected = router.select(StageType.SYNTHESIZE, frozenset({ModelCapability.THINKING}))
    assert selected is not None
    assert selected.id == "m2"


def test_select_returns_none_when_no_match():
    reg = _registry_with(_genome("m1", {ModelCapability.FAST}, "router"))
    router = LLMRouter(registry=reg, providers={"router": _FakeProvider()})
    assert router.select(StageType.VISION_EXTRACTION, frozenset({ModelCapability.VISION})) is None


def test_select_returns_none_when_all_unhealthy():
    g = _genome("m1", {ModelCapability.THINKING}, "router")
    reg = _registry_with(g)
    health = {"router": ProviderHealth(provider_id="router", consecutive_failures=5)}
    router = LLMRouter(registry=reg, providers={"router": _FakeProvider()}, health=health)
    assert router.select(StageType.SYNTHESIZE, frozenset({ModelCapability.THINKING})) is None


# ── route_with_fallback ───────────────────────────────────────────────


def test_route_serves_via_primary_without_fallback():
    g = _genome("m1", {ModelCapability.THINKING}, "router")
    reg = _registry_with(g)
    provider = _FakeProvider()
    router = LLMRouter(registry=reg, providers={"router": provider})
    result = router.route_with_fallback(
        StageType.SYNTHESIZE, frozenset({ModelCapability.THINKING}), {"system": "s", "messages": [], "model": "m1", "max_tokens": 10, "temperature": 0, "top_p": 1, "output_schema": None, "timeout_seconds": 5}
    )
    assert result is not None
    assert result.used_fallback is False
    assert result.provider_id == "router"
    assert router.health("router").consecutive_failures == 0


def test_route_falls_back_when_primary_fails():
    primary = _genome("m1", {ModelCapability.THINKING}, "router", cost_in=1.0, cost_out=1.0)
    secondary = _genome("m2", {ModelCapability.THINKING}, "fallback", cost_in=2.0, cost_out=2.0)
    reg = _registry_with(primary, secondary)
    providers = {"router": _FakeProvider(fail=True), "fallback": _FakeProvider()}
    router = LLMRouter(registry=reg, providers=providers)
    result = router.route_with_fallback(
        StageType.SYNTHESIZE, frozenset({ModelCapability.THINKING}), {"system": "s", "messages": [], "model": "m1", "max_tokens": 10, "temperature": 0, "top_p": 1, "output_schema": None, "timeout_seconds": 5}
    )
    assert result is not None
    assert result.used_fallback is True
    assert result.provider_id == "fallback"
    # Primary was marked unhealthy.
    assert router.health("router").consecutive_failures == 1
    assert router.health("router").last_error is not None
    assert ("router", False) in result.attempts
    assert ("fallback", True) in result.attempts


def test_route_returns_none_when_all_providers_fail():
    g1 = _genome("m1", {ModelCapability.THINKING}, "router", cost_in=1.0, cost_out=1.0)
    g2 = _genome("m2", {ModelCapability.THINKING}, "fallback", cost_in=2.0, cost_out=2.0)
    reg = _registry_with(g1, g2)
    providers = {"router": _FakeProvider(fail=True), "fallback": _FakeProvider(fail=True)}
    router = LLMRouter(registry=reg, providers=providers)
    result = router.route_with_fallback(
        StageType.SYNTHESIZE, frozenset({ModelCapability.THINKING}), {"system": "s", "messages": [], "model": "m1", "max_tokens": 10, "temperature": 0, "top_p": 1, "output_schema": None, "timeout_seconds": 5}
    )
    assert result is None
    assert router.health("router").consecutive_failures == 1
    assert router.health("fallback").consecutive_failures == 1


def test_route_marks_success_on_serving():
    g = _genome("m1", {ModelCapability.THINKING}, "router")
    reg = _registry_with(g)
    router = LLMRouter(registry=reg, providers={"router": _FakeProvider()})
    router.route_with_fallback(
        StageType.SYNTHESIZE, frozenset({ModelCapability.THINKING}), {"system": "s", "messages": [], "model": "m1", "max_tokens": 10, "temperature": 0, "top_p": 1, "output_schema": None, "timeout_seconds": 5}
    )
    assert router.health("router").last_success_at is not None


def test_routing_result_is_frozen():
    from dataclasses import FrozenInstanceError

    r = RoutingResult(provider_id="router", genome=_genome("m1", {ModelCapability.FAST}, "router"), used_fallback=False)
    with pytest.raises(FrozenInstanceError):
        r.provider_id = "x"  # type: ignore[misc]


# ── M040 S03: retry + backoff + fallback + LLMUnavailable ─────────────


class _FlakyProvider:
    """Provider that fails N times then succeeds (or always fails)."""

    def __init__(self, *, default_model: str = "m1", fail_n: int = 0):
        self.default_model = default_model
        self._fail_n = fail_n
        self._calls = 0

    def complete(self, **kwargs):  # noqa: ANN003
        self._calls += 1
        if self._calls <= self._fail_n:
            raise RuntimeError(f"transient fail #{self._calls}")
        return {"ok": True, "model": self.default_model}

    @property
    def calls(self) -> int:
        return self._calls


def test_retry_then_success_no_fallback(monkeypatch):
    """Provider fails twice then succeeds on 3rd attempt: no fallback, served."""
    delays: list[float] = []
    g = _genome("m1", {ModelCapability.THINKING}, "router")
    reg = _registry_with(g)
    provider = _FlakyProvider(fail_n=2)
    router = LLMRouter(
        registry=reg, providers={"router": provider},
        max_retries=3, base_backoff=0.01, sleep_fn=delays.append,
    )
    result = router.route_with_fallback(
        StageType.SYNTHESIZE, frozenset({ModelCapability.THINKING}),
        {"system": "s", "messages": [], "model": "m1", "max_tokens": 1, "temperature": 0, "top_p": 1, "output_schema": None, "timeout_seconds": 1},
    )
    assert result is not None
    assert result.used_fallback is False
    assert provider.calls == 3
    # Backoff applied between the 2 failed attempts before success.
    assert len(delays) == 2


def test_retry_exhaustion_then_fallback(monkeypatch):
    """Primary exhausts all retries → falls back to secondary provider."""
    delays: list[float] = []
    primary = _genome("m1", {ModelCapability.THINKING}, "router", cost_in=1.0, cost_out=1.0)
    secondary = _genome("m2", {ModelCapability.THINKING}, "fallback", cost_in=2.0, cost_out=2.0)
    reg = _registry_with(primary, secondary)
    primary_provider = _FlakyProvider(fail_n=99)  # always fails
    fallback_provider = _FlakyProvider(fail_n=0)
    router = LLMRouter(
        registry=reg,
        providers={"router": primary_provider, "fallback": fallback_provider},
        max_retries=2, base_backoff=0.001, sleep_fn=delays.append,
    )
    result = router.route_with_fallback(
        StageType.SYNTHESIZE, frozenset({ModelCapability.THINKING}),
        {"system": "s", "messages": [], "model": "m1", "max_tokens": 1, "temperature": 0, "top_p": 1, "output_schema": None, "timeout_seconds": 1},
    )
    assert result is not None
    assert result.used_fallback is True
    assert result.provider_id == "fallback"
    # Primary was retried max_retries+1 times total.
    assert primary_provider.calls == 3
    # Primary marked unhealthy after exhaustion.
    assert router.health("router").consecutive_failures == 1


def test_all_providers_exhausted_raises_llm_unavailable():
    from active_skill_system.domain.errors import LLMUnavailable

    g1 = _genome("m1", {ModelCapability.THINKING}, "router", cost_in=1.0, cost_out=1.0)
    g2 = _genome("m2", {ModelCapability.THINKING}, "fallback", cost_in=2.0, cost_out=2.0)
    reg = _registry_with(g1, g2)
    providers = {"router": _FlakyProvider(fail_n=99), "fallback": _FlakyProvider(fail_n=99)}
    router = LLMRouter(
        registry=reg, providers=providers, max_retries=1, base_backoff=0.001, sleep_fn=lambda _d: None,
    )
    with pytest.raises(LLMUnavailable):
        router.route_with_fallback_or_raise(
            StageType.SYNTHESIZE, frozenset({ModelCapability.THINKING}),
            {"system": "s", "messages": [], "model": "m1", "max_tokens": 1, "temperature": 0, "top_p": 1, "output_schema": None, "timeout_seconds": 1},
        )


def test_backoff_is_exponential():
    """Backoff delays grow exponentially across attempts."""
    delays: list[float] = []
    g = _genome("m1", {ModelCapability.THINKING}, "router")
    reg = _registry_with(g)
    router = LLMRouter(
        registry=reg, providers={"router": _FlakyProvider(fail_n=99)},
        max_retries=3, base_backoff=0.1, sleep_fn=delays.append,
    )
    router.route_with_fallback(
        StageType.SYNTHESIZE, frozenset({ModelCapability.THINKING}),
        {"system": "s", "messages": [], "model": "m1", "max_tokens": 1, "temperature": 0, "top_p": 1, "output_schema": None, "timeout_seconds": 1},
    )
    # 3 retries → 3 delays: 0.1, 0.2, 0.4.
    assert len(delays) == 3
    assert delays[0] < delays[1] < delays[2]
    assert delays == [0.1, 0.2, 0.4]
