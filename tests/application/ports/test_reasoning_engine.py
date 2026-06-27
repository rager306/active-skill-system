"""Tests for ReasoningEnginePort (M043 S01 T01)."""

from __future__ import annotations

from active_skill_system.application.ports.reasoning_engine import (
    ReasoningEnginePort,
    ReasoningRequest,
    ReasoningResult,
)


def test_reasoning_request_defaults():
    req = ReasoningRequest(system="s", prompt="p", model="m")
    assert req.max_tokens == 524_288
    assert req.temperature == 0.0
    assert req.timeout_seconds == 120.0


def test_reasoning_result_ok_property():
    ok = ReasoningResult(text="code", model="m", finish_reason="end_turn")
    assert ok.ok is True

    empty = ReasoningResult(text="", model="m")
    assert empty.ok is False

    errored = ReasoningResult(text="code", model="m", error="boom")
    assert errored.ok is False


def test_reasoning_result_is_frozen():
    from dataclasses import FrozenInstanceError

    import pytest

    r = ReasoningResult(text="x", model="m")
    with pytest.raises(FrozenInstanceError):
        r.text = "y"  # type: ignore[misc]


def test_reasoning_engine_port_is_protocol():
    """A minimal class with forward() satisfies the Protocol."""

    class _Fake:
        def forward(self, request: ReasoningRequest) -> ReasoningResult:
            return ReasoningResult(text="ok", model="fake")

    assert isinstance(_Fake(), ReasoningEnginePort)


def test_reasoning_request_is_frozen():
    from dataclasses import FrozenInstanceError

    import pytest

    req = ReasoningRequest(system="s", prompt="p", model="m")
    with pytest.raises(FrozenInstanceError):
        req.prompt = "x"  # type: ignore[misc]
