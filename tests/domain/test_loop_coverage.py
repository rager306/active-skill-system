"""Coverage tests for loop.py uncovered branches (M045 S01 T01)."""

from __future__ import annotations

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

# ── Budget.deadline_iso path ──────────────────────────────────────────


def test_budget_exhausted_by_deadline_past():
    b = Budget(deadline_iso="2026-01-01T00:00:00+00:00")
    assert b.exhausted(now_iso="2026-06-28T00:00:00+00:00")


def test_budget_not_exhausted_by_deadline_future():
    b = Budget(deadline_iso="2026-12-31T23:59:59+00:00")
    assert not b.exhausted(now_iso="2026-06-28T00:00:00+00:00")


def test_budget_exhausted_by_deadline_exact():
    b = Budget(deadline_iso="2026-06-28T00:00:00+00:00")
    assert b.exhausted(now_iso="2026-06-28T00:00:00+00:00")


def test_budget_not_exhausted_no_deadline():
    b = Budget(max_iterations=10)
    assert not b.exhausted(now_iso="2026-06-28T00:00:00+00:00")


# ── Budget with multiple bounds ──────────────────────────────────────


def test_budget_multiple_bounds_one_exhausted():
    b = Budget(max_iterations=5, max_cost=1.0, max_llm_calls=3)
    assert b.exhausted(iterations_used=5, cost_used=0.5, llm_calls_used=2)
    assert b.exhausted(iterations_used=3, cost_used=1.0, llm_calls_used=2)
    assert b.exhausted(iterations_used=3, cost_used=0.5, llm_calls_used=3)
    assert not b.exhausted(iterations_used=3, cost_used=0.5, llm_calls_used=2)


# ── VERIFYING → RUNNING (retry after verification) ───────────────────


def test_loop_verifying_to_running_retry():
    loop = Loop.start("loop-retry", "x", Budget(max_iterations=5))
    loop = loop.advance(LoopEvent.now(LoopEventKind.VERIFIED, LoopState.VERIFYING))
    # VERIFYING → RUNNING is legal (retry after verification)
    loop = loop.advance(LoopEvent.now(LoopEventKind.STATE_CHANGED, LoopState.RUNNING))
    assert loop.state is LoopState.RUNNING
    assert len(loop.lifecycle) == 3


# ── Terminal states cannot advance ───────────────────────────────────


@pytest.mark.parametrize("terminal", list(TERMINAL_LOOP_STATES))
def test_terminal_state_cannot_advance(terminal):
    loop = Loop(id="t", intent="x", budget=Budget(max_iterations=1), lifecycle=(), state=LoopState.PENDING)
    # Start then advance to terminal
    started = Loop.start("t2", "x", Budget(max_iterations=1))
    # Get to the terminal via start→RUNNING→terminal
    if terminal is LoopState.DONE:
        term = started.advance(LoopEvent.now(LoopEventKind.FINISHED, LoopState.DONE))
    elif terminal is LoopState.FAILED:
        term = started.advance(LoopEvent.now(LoopEventKind.FAILED, LoopState.FAILED))
    else:  # RETAINED
        term = started.advance(LoopEvent.now(LoopEventKind.RETAINED, LoopState.RETAINED))
    with pytest.raises(ValueError, match="terminal state"):
        term.advance(LoopEvent.now(LoopEventKind.STATE_CHANGED, LoopState.RUNNING))


# ── LoopEvent.now factory ─────────────────────────────────────────────


def test_loop_event_now_sets_nonempty_timestamp():
    ev = LoopEvent.now(LoopEventKind.STARTED, LoopState.RUNNING)
    assert ev.timestamp != ""
    assert ev.kind is LoopEventKind.STARTED


def test_loop_event_now_with_payload():
    ev = LoopEvent.now(LoopEventKind.VERIFIED, LoopState.VERIFYING, {"verifier": "v1"})
    assert ev.payload == {"verifier": "v1"}


# ── Loop.start with skills ────────────────────────────────────────────


def test_loop_start_with_multiple_skills():
    loop = Loop.start("multi", "intent", Budget(max_iterations=1), skills=("a", "b", "c"))
    assert loop.skills == ("a", "b", "c")
    assert loop.state is LoopState.RUNNING


def test_loop_start_minimal():
    loop = Loop.start("min", "x", Budget(max_iterations=1))
    assert loop.skills == ()
    assert loop.state is LoopState.RUNNING


# ── FSM table completeness ────────────────────────────────────────────


def test_all_non_terminal_states_have_transitions():
    non_terminal = set(LoopState) - TERMINAL_LOOP_STATES
    for state in non_terminal:
        assert state in LEGAL_LOOP_TRANSITIONS, f"{state} missing from transitions table"


def test_is_legal_transition_helper_completeness():
    # PENDING can go to RUNNING, FAILED, RETAINED
    assert is_legal_loop_transition(LoopState.PENDING, LoopState.RUNNING)
    assert is_legal_loop_transition(LoopState.PENDING, LoopState.FAILED)
    assert is_legal_loop_transition(LoopState.PENDING, LoopState.RETAINED)
    # VERIFYING can go back to RUNNING (retry)
    assert is_legal_loop_transition(LoopState.VERIFYING, LoopState.RUNNING)


# ── advance with validate_transition=False ───────────────────────────


def test_advance_skips_validation_when_disabled():
    loop = Loop(id="skip", intent="x", budget=Budget(max_iterations=1))
    # PENDING → DONE is illegal, but with validate=False it should work
    loop = loop.advance(
        LoopEvent.now(LoopEventKind.FINISHED, LoopState.DONE),
        validate_transition=False,
    )
    assert loop.state is LoopState.DONE


# ── Budget edge values ────────────────────────────────────────────────


def test_budget_rejects_bool_for_iterations():
    with pytest.raises(ValueError):
        Budget(max_iterations=True)  # type: ignore[arg-type]


def test_budget_accepts_zero_cost():
    b = Budget(max_cost=0.0)
    assert b.exhausted(cost_used=0.0)
