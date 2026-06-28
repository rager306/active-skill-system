"""Tests for M052 S01 — FastRLMStrategy adapter."""

from __future__ import annotations

import pytest

from active_skill_system.adapters.fast_rlm_strategy import FastRLMStrategy
from active_skill_system.application.ports.reasoning_engine import (
    ReasoningRequest,
    ReasoningResult,
)


def test_fast_rlm_stub_when_api_base_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    s = FastRLMStrategy()
    assert s.is_stub is True
    assert s.stub_reason is not None


def test_fast_rlm_satisfies_port() -> None:
    s = FastRLMStrategy()
    request = ReasoningRequest(system="x", prompt="y", model="m")
    result = s.forward(request)
    assert isinstance(result, ReasoningResult)
    if s.is_stub:
        assert result.finish_reason == "stub"
        assert result.text == ""
        assert result.error is not None


def test_fast_rlm_never_raises() -> None:
    s = FastRLMStrategy(api_base="http://invalid", api_key="bad")
    request = ReasoningRequest(system="x", prompt="y", model="m")
    result = s.forward(request)
    assert isinstance(result, ReasoningResult)


def test_fast_rlm_returns_request_model() -> None:
    s = FastRLMStrategy()
    request = ReasoningRequest(system="x", prompt="y", model="custom-model")
    result = s.forward(request)
    assert result.model == "custom-model"


def test_fast_rlm_init_with_explicit_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    s = FastRLMStrategy(
        primary_agent="custom-primary",
        sub_agent="custom-sub",
        max_depth=3,
        api_base="http://test",
        api_key="test-key",
    )
    assert s._max_depth == 3
    # With Deno available the strategy is configured; without Deno (CI/dev)
    # it is stub. Either way the requested config values are recorded when
    # not stubbed.
    if not s.is_stub:
        assert s._resolved_primary == "custom-primary"
        assert s._resolved_sub == "custom-sub"
    else:
        # Stub reason should mention Deno (the gating dependency).
        assert "deno" in (s.stub_reason or "").lower()
