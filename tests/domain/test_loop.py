"""Tests for Loop domain entity (RGLA, D009)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from active_skill_system.domain.loop import (
    LEGAL_LOOP_TRANSITIONS,
    TERMINAL_LOOP_STATES,
    Budget,
    Loop,
    LoopEvent,
    LoopEventKind,
    LoopState,
    is_legal_loop_transition,
)

# ── Budget ────────────────────────────────────────────────────────────


def test_budget_requires_at_least_one_bound():
    with pytest.raises(ValueError, match="at least one bound"):
        Budget()


def test_budget_accepts_iterations_bound():
    b = Budget(max_iterations=5)
    assert b.max_iterations == 5
    assert not b.exhausted(iterations_used=4)
    assert b.exhausted(iterations_used=5)
    assert b.exhausted(iterations_used=6)


def test_budget_accepts_cost_bound():
    b = Budget(max_cost=1.0)
    assert not b.exhausted(cost_used=0.5)
    assert b.exhausted(cost_used=1.0)


def test_budget_accepts_llm_calls_bound():
    b = Budget(max_llm_calls=3)
    assert not b.exhausted(llm_calls_used=2)
    assert b.exhausted(llm_calls_used=3)


def test_budget_accepts_deadline_bound():
    b = Budget(deadline_iso="2026-12-31T23:59:59+00:00")
    assert not b.exhausted(now_iso="2026-06-01T00:00:00+00:00")
    assert b.exhausted(now_iso="2027-01-01T00:00:00+00:00")


def test_budget_rejects_non_positive_int_bounds():
    with pytest.raises(ValueError):
        Budget(max_iterations=0)
    with pytest.raises(ValueError):
        Budget(max_llm_calls=-1)


def test_budget_rejects_negative_cost():
    with pytest.raises(ValueError):
        Budget(max_cost=-0.5)


def test_budget_rejects_empty_deadline():
    with pytest.raises(ValueError):
        Budget(deadline_iso="  ")


def test_budget_multiple_bounds():
    b = Budget(max_iterations=5, max_cost=1.0, max_llm_calls=10)
    assert not b.exhausted(iterations_used=4, cost_used=0.5, llm_calls_used=3)
    assert b.exhausted(iterations_used=5, cost_used=0.5, llm_calls_used=3)


# ── LoopEvent ─────────────────────────────────────────────────────────


def test_loop_event_factory_sets_timestamp():
    ev = LoopEvent.now(LoopEventKind.STARTED, LoopState.RUNNING)
    assert ev.kind is LoopEventKind.STARTED
    assert ev.state is LoopState.RUNNING
    assert ev.timestamp != ""


def test_loop_event_rejects_invalid_kinds():
    with pytest.raises(ValueError):
        LoopEvent(kind="not-a-kind", state=LoopState.RUNNING)  # type: ignore[arg-type]


# ── Loop lifecycle ────────────────────────────────────────────────────


def _budget() -> Budget:
    return Budget(max_iterations=10)


def test_loop_start_emits_started_and_running():
    loop = Loop.start("loop-1", "optimize sql", _budget(), skills=("sql-plan-opt",))
    assert loop.id == "loop-1"
    assert loop.intent == "optimize sql"
    assert loop.state is LoopState.RUNNING
    assert len(loop.lifecycle) == 1
    assert loop.lifecycle[0].kind is LoopEventKind.STARTED
    assert loop.skills == ("sql-plan-opt",)


def test_loop_empty_lifecycle_is_pending():
    loop = Loop(id="loop-2", intent="x", budget=_budget())
    assert loop.state is LoopState.PENDING
    assert loop.lifecycle == ()


def test_loop_advance_appends_event_and_projects_state():
    loop = Loop.start("loop-3", "x", _budget())
    verify = LoopEvent.now(LoopEventKind.VERIFIED, LoopState.VERIFYING)
    advanced = loop.advance(verify)
    assert advanced.state is LoopState.VERIFYING
    assert len(advanced.lifecycle) == 2
    # Original is unchanged (immutability).
    assert loop.state is LoopState.RUNNING
    assert len(loop.lifecycle) == 1


def test_loop_advance_rejects_illegal_transition():
    loop = Loop.start("loop-4", "x", _budget())  # RUNNING
    # RUNNING -> PENDING is illegal.
    bad = LoopEvent.now(LoopEventKind.STATE_CHANGED, LoopState.PENDING)
    with pytest.raises(ValueError, match="illegal loop transition"):
        loop.advance(bad)


def test_loop_advance_rejects_terminal_state():
    loop = Loop.start("loop-5", "x", _budget())
    done = LoopEvent.now(LoopEventKind.FINISHED, LoopState.DONE)
    finished = loop.advance(done)
    with pytest.raises(ValueError, match="terminal state"):
        finished.advance(LoopEvent.now(LoopEventKind.STATE_CHANGED, LoopState.RUNNING))


def test_loop_is_frozen():
    loop = Loop.start("loop-6", "x", _budget())
    with pytest.raises(FrozenInstanceError):
        loop.state = LoopState.DONE  # type: ignore[misc]


def test_loop_rejects_empty_id_and_intent():
    with pytest.raises(ValueError):
        Loop(id="", intent="x", budget=_budget())
    with pytest.raises(ValueError):
        Loop(id="loop-7", intent="", budget=_budget())


def test_loop_rejects_missing_budget():
    with pytest.raises(ValueError):
        Loop(id="loop-8", intent="x", budget=None)  # type: ignore[arg-type]


def test_loop_state_consistency_enforced():
    """state must equal the last lifecycle event's state."""
    inconsistent = LoopEvent.now(LoopEventKind.STARTED, LoopState.RUNNING)
    with pytest.raises(ValueError, match="must equal last lifecycle event state"):
        Loop(
            id="loop-9",
            intent="x",
            budget=_budget(),
            lifecycle=(inconsistent,),
            state=LoopState.PENDING,  # contradicts the RUNNING event
        )


def test_loop_full_lifecycle_pending_to_done():
    loop = Loop.start("loop-10", "x", _budget())
    loop = loop.advance(LoopEvent.now(LoopEventKind.VERIFIED, LoopState.VERIFYING))
    loop = loop.advance(LoopEvent.now(LoopEventKind.FINISHED, LoopState.DONE))
    assert loop.state is LoopState.DONE
    assert loop in TERMINAL_LOOP_STATES.__iter__() or loop.state in TERMINAL_LOOP_STATES
    assert len(loop.lifecycle) == 3


# ── Transition table ──────────────────────────────────────────────────


def test_legal_transitions_table_covers_non_terminal_states():
    covered = set(LEGAL_LOOP_TRANSITIONS.keys())
    non_terminal = set(LoopState) - TERMINAL_LOOP_STATES
    assert non_terminal == covered


def test_is_legal_loop_transition_helper():
    assert is_legal_loop_transition(LoopState.PENDING, LoopState.RUNNING)
    assert not is_legal_loop_transition(LoopState.DONE, LoopState.RUNNING)
    assert not is_legal_loop_transition(LoopState.RUNNING, LoopState.PENDING)
