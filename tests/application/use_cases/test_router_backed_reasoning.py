"""Tests for M054 S08 — RouterBackedReasoningEngine (M038 gap closure)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from active_skill_system.application.ports.reasoning_engine import ReasoningRequest
from active_skill_system.application.use_cases.router_backed_reasoning import (
    RouterBackedReasoningEngine,
)


def _mock_routing_result(provider_id: str = "minimax", model_id: str = "MiniMax-M3") -> MagicMock:
    """Create a mock RoutingResult."""
    result = MagicMock()
    result.provider_id = provider_id
    result.used_fallback = False
    result.genome = MagicMock()
    result.genome.model_id = model_id
    return result


def _mock_router(routing_result=None, fail: bool = False) -> MagicMock:
    """Create a mock LLMRouter."""
    router = MagicMock()
    if fail:
        router.route_with_fallback.side_effect = RuntimeError("all providers failed")
    elif routing_result is None:
        router.route_with_fallback.return_value = None
    else:
        router.route_with_fallback.return_value = routing_result
    return router


def _make_request(model: str = "minimax/MiniMax-M3") -> ReasoningRequest:
    return ReasoningRequest(
        system="You are a code generator.",
        prompt="Generate code.",
        model=model,
        max_tokens=1000,
        temperature=0.0,
    )


# ── Construction ──────────────────────────────────────────────────────────


def test_router_engine_rejects_none_router() -> None:
    with pytest.raises(TypeError, match="router must be a non-None"):
        RouterBackedReasoningEngine(router=None)  # type: ignore[arg-type]


def test_router_engine_default_model() -> None:
    engine = RouterBackedReasoningEngine(router=_mock_router(_mock_routing_result()))
    assert engine.default_model == "minimax/MiniMax-M3"


# ── Forward ───────────────────────────────────────────────────────────────


def test_forward_returns_reasoning_result() -> None:
    """forward() routes through LLMRouter and returns ReasoningResult."""
    routing = _mock_routing_result(provider_id="minimax", model_id="MiniMax-M3")
    router = _mock_router(routing)
    engine = RouterBackedReasoningEngine(router=router)

    result = engine.forward(_make_request())

    assert result.model == "MiniMax-M3"
    assert result.finish_reason == "ok"
    assert "minimax" in result.text


def test_forward_calls_router_route_with_fallback() -> None:
    """forward() calls router.route_with_fallback."""
    router = _mock_router(_mock_routing_result())
    engine = RouterBackedReasoningEngine(router=router)

    engine.forward(_make_request())

    router.route_with_fallback.assert_called_once()


def test_forward_routing_none_returns_error_result() -> None:
    """When router returns None (all exhausted), forward() returns error."""
    router = _mock_router(routing_result=None)  # returns None
    engine = RouterBackedReasoningEngine(router=router)

    result = engine.forward(_make_request())

    assert "exhausted" in (result.error or "")
    assert result.finish_reason == "error"


def test_forward_routing_exception_returns_error_result() -> None:
    """When routing raises, forward() returns error result (graceful)."""
    router = _mock_router(fail=True)
    engine = RouterBackedReasoningEngine(router=router)

    result = engine.forward(_make_request())

    assert "routing failed" in (result.error or "")
    assert result.finish_reason == "error"


def test_forward_fallback_indicated_in_finish_reason() -> None:
    """When used_fallback=True, finish_reason is 'fallback'."""
    routing = _mock_routing_result()
    routing.used_fallback = True
    router = _mock_router(routing)
    engine = RouterBackedReasoningEngine(router=router)

    result = engine.forward(_make_request())

    assert result.finish_reason == "fallback"
