"""Unit tests for F-13 Cancellation + Idempotency (M014 S01)."""

from __future__ import annotations

import pytest

from active_skill_system.application.idempotency import IdempotencyStore
from active_skill_system.domain.runtime import RunFSM, RunState
from active_skill_system.domain.runtime.cancellation import (
    IdempotencyKey,
    RunCancellation,
)

# ── RunCancellation ───────────────────────────────────────────────────────


def test_cancellation_constructs() -> None:
    c = RunCancellation(run_id="r1", reason="user request")
    assert c.run_id == "r1"
    assert c.reason == "user request"


def test_cancellation_rejects_empty_run_id() -> None:
    with pytest.raises(ValueError, match="run_id"):
        RunCancellation(run_id="", reason="x")


def test_cancellation_rejects_empty_reason() -> None:
    with pytest.raises(ValueError, match="reason"):
        RunCancellation(run_id="r1", reason="")


# ── IdempotencyKey ────────────────────────────────────────────────────────


def test_idempotency_key_constructs() -> None:
    k = IdempotencyKey(key="idem-1")
    assert k.key == "idem-1"
    assert str(k) == "idem-1"


def test_idempotency_key_rejects_empty() -> None:
    with pytest.raises(ValueError, match="key"):
        IdempotencyKey(key="")


# ── RunFSM.cancel() ───────────────────────────────────────────────────────


def test_cancel_from_classifying() -> None:
    fsm = RunFSM().transition(RunState.CLASSIFYING)
    cancelled = fsm.cancel()
    assert cancelled.state is RunState.CANCELLED
    assert RunState.CANCELLED in cancelled.history


def test_cancel_from_modeling() -> None:
    fsm = RunFSM(state=RunState.MODELING, history=(RunState.RECEIVED, RunState.MODELING))
    cancelled = fsm.cancel()
    assert cancelled.state is RunState.CANCELLED


def test_cancel_from_repairing() -> None:
    fsm = RunFSM(state=RunState.REPAIRING, history=(RunState.RECEIVED, RunState.REPAIRING))
    cancelled = fsm.cancel()
    assert cancelled.state is RunState.CANCELLED


def test_cancel_from_terminal_raises() -> None:
    fsm = RunFSM(state=RunState.COMPLETED, history=(RunState.RECEIVED, RunState.COMPLETED))
    with pytest.raises(ValueError, match="terminal"):
        fsm.cancel()


def test_cancel_from_cancelled_raises() -> None:
    fsm = RunFSM(state=RunState.CANCELLED, history=(RunState.RECEIVED, RunState.CANCELLED))
    with pytest.raises(ValueError, match="terminal"):
        fsm.cancel()


# ── IdempotencyStore ──────────────────────────────────────────────────────


def test_store_register_new_returns_true() -> None:
    s = IdempotencyStore()
    assert s.register("k1", "result1") is True
    assert s.get("k1") == "result1"


def test_store_register_duplicate_returns_false() -> None:
    s = IdempotencyStore()
    s.register("k1", "result1")
    assert s.register("k1", "result2") is False
    assert s.get("k1") == "result1"  # original preserved


def test_store_get_nonexistent_returns_none() -> None:
    s = IdempotencyStore()
    assert s.get("nope") is None


def test_store_has() -> None:
    s = IdempotencyStore()
    s.register("k1", "x")
    assert s.has("k1") is True
    assert s.has("k2") is False


def test_store_clear() -> None:
    s = IdempotencyStore()
    s.register("k1", "x")
    s.clear()
    assert s.has("k1") is False
