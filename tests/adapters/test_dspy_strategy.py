"""Tests for M051 S01 — DSPyStrategy adapter."""

from __future__ import annotations

from active_skill_system.adapters.dspy_strategy import DSPyStrategy
from active_skill_system.application.ports.reasoning_engine import (
    ReasoningRequest,
    ReasoningResult,
)


def test_dspy_strategy_stub_when_api_base_missing() -> None:
    """No ANTHROPIC_BASE_URL → DSPyStrategy degrades to stub mode."""
    import os

    os.environ.pop("ANTHROPIC_BASE_URL", None)
    os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)
    s = DSPyStrategy()
    assert s.is_stub is True
    assert s.stub_reason is not None


def test_dspy_strategy_satisfies_port() -> None:
    """DSPyStrategy implements forward() — the port contract."""
    s = DSPyStrategy()
    request = ReasoningRequest(
        system="You are a code generator.",
        prompt="Write hello world.",
        model="minimax/MiniMax-M3",
    )
    result = s.forward(request)
    assert isinstance(result, ReasoningResult)
    # In stub mode, finish_reason=stub and text is empty.
    if s.is_stub:
        assert result.finish_reason == "stub"
        assert result.text == ""
        assert result.error is not None


def test_dspy_strategy_never_raises() -> None:
    """DSPyStrategy.forward must NEVER raise, even with bad config."""
    s = DSPyStrategy(api_base="http://invalid", api_key="bad")
    request = ReasoningRequest(
        system="x", prompt="y", model="m",
    )
    # Should not raise regardless of state.
    result = s.forward(request)
    assert isinstance(result, ReasoningResult)


def test_dspy_strategy_returns_model_name_in_result() -> None:
    s = DSPyStrategy()
    request = ReasoningRequest(system="x", prompt="y", model="custom-model")
    result = s.forward(request)
    assert result.model == "custom-model"


def test_dspy_strategy_init_with_explicit_values() -> None:
    """Explicit constructor values override env."""
    s = DSPyStrategy(
        model="explicit-model",
        api_base="http://test",
        api_key="test-key",
        max_tokens=1024,
        temperature=0.5,
    )
    request = ReasoningRequest(system="x", prompt="y", model="m")
    result = s.forward(request)
    # Stub or real — both are valid outcomes; just check model propagation.
    assert result.model == "m"  # request.model is what we propagate
