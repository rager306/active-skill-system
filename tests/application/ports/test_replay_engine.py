"""Tests for M054 S01 — ReplayEngine port + ReplayResult."""

from __future__ import annotations

import pytest

from active_skill_system.application.ports.replay_engine import ReplayEngine
from active_skill_system.domain.replay import ReplayMode, ReplayResult

# ── ReplayResult ──────────────────────────────────────────────────────────


def test_replay_result_creation_defaults() -> None:
    r = ReplayResult(run_id="run-1", mode=ReplayMode.STRICT)
    assert r.run_id == "run-1"
    assert r.mode == "strict"
    assert r.events_replayed == 0
    assert r.vertices_reconstructed == 0
    assert r.behaviors_fired == 0
    assert r.graph_snapshot == {}


def test_replay_result_creation_full() -> None:
    r = ReplayResult(
        run_id="run-1", mode=ReplayMode.PERMISSIVE,
        events_replayed=10, vertices_reconstructed=5, edges_reconstructed=3,
        behaviors_fired=2, duration_ns=1500,
        graph_snapshot={"v1": {"type": "claim"}},
    )
    assert r.events_replayed == 10
    assert r.vertices_reconstructed == 5
    assert r.behaviors_fired == 2


def test_replay_result_rejects_empty_run_id() -> None:
    with pytest.raises(ValueError, match="run_id must be non-empty"):
        ReplayResult(run_id="", mode="strict")


def test_replay_result_rejects_bad_mode() -> None:
    with pytest.raises(ValueError, match="mode must be strict/permissive"):
        ReplayResult(run_id="r", mode="invalid")


def test_replay_result_rejects_negative_events() -> None:
    with pytest.raises(ValueError, match="events_replayed must be non-negative"):
        ReplayResult(run_id="r", mode="strict", events_replayed=-1)


def test_replay_result_summary() -> None:
    r = ReplayResult(
        run_id="run-1", mode="permissive",
        events_replayed=5, vertices_reconstructed=3, edges_reconstructed=1,
        behaviors_fired=2,
    )
    s = r.summary()
    assert "run-1" in s
    assert "permissive" in s
    assert "5 events" in s
    assert "3 vertices" in s
    assert "2 behaviors fired" in s


def test_replay_mode_constants() -> None:
    assert ReplayMode.STRICT == "strict"
    assert ReplayMode.PERMISSIVE == "permissive"


# ── ReplayEngine Protocol ─────────────────────────────────────────────────


def test_replay_engine_is_protocol() -> None:
    assert hasattr(ReplayEngine, "_is_protocol")
    assert hasattr(ReplayEngine, "replay")


def test_replay_engine_protocol_conformance() -> None:
    """A minimal implementation should satisfy the Protocol."""

    class _FakeReplayEngine:
        def replay(self, run_id: str, mode: str = "strict") -> ReplayResult:
            return ReplayResult(run_id=run_id, mode=mode)

    fake = _FakeReplayEngine()
    assert isinstance(fake, ReplayEngine)
