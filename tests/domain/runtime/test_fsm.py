"""Unit tests for domain/runtime/fsm.py (Run FSM).

Verifies:
  - all states present (concept.md §4.3).
  - legal/illegal transitions per the diagram.
  - terminal states accept no transitions.
  - RunFSM history accumulates and starts with RECEIVED.
  - immutability of transition().
"""

from __future__ import annotations

import pytest

from active_skill_system.domain.runtime.fsm import (
    LEGAL_TRANSITIONS,
    TERMINAL_STATES,
    RunFSM,
    RunState,
    is_legal_transition,
)

# concept.md §4.3: 12 active + 4 terminal states.
_EXPECTED_STATES = {
    RunState.RECEIVED,
    RunState.CLASSIFYING,
    RunState.DIRECT_PATH,
    RunState.MODELING,
    RunState.VALIDATING_MODEL,
    RunState.REPAIRING,
    RunState.WAITING_INPUT,
    RunState.WAITING_APPROVAL,
    RunState.PLANNING,
    RunState.EXECUTING,
    RunState.SYNTHESIZING,
    RunState.VALIDATING_OUTPUT,
    RunState.COMPLETED,
    RunState.PARTIAL,
    RunState.FAILED,
    RunState.CANCELLED,
}


def test_all_states_present() -> None:
    assert set(RunState) == _EXPECTED_STATES
    assert {
        RunState.COMPLETED,
        RunState.PARTIAL,
        RunState.FAILED,
        RunState.CANCELLED,
    } == TERMINAL_STATES


def test_legal_transition_examples() -> None:
    assert is_legal_transition(RunState.RECEIVED, RunState.CLASSIFYING)
    assert is_legal_transition(RunState.CLASSIFYING, RunState.DIRECT_PATH)
    assert is_legal_transition(RunState.CLASSIFYING, RunState.MODELING)
    assert is_legal_transition(RunState.VALIDATING_MODEL, RunState.PLANNING)
    assert is_legal_transition(RunState.SYNTHESIZING, RunState.VALIDATING_OUTPUT)


def test_illegal_transition_examples() -> None:
    # no shortcut skips
    assert not is_legal_transition(RunState.RECEIVED, RunState.PLANNING)
    assert not is_legal_transition(RunState.RECEIVED, RunState.COMPLETED)
    assert not is_legal_transition(RunState.COMPLETED, RunState.PLANNING)
    assert not is_legal_transition(RunState.EXECUTING, RunState.COMPLETED)


def test_terminal_has_no_outgoing() -> None:
    for terminal in TERMINAL_STATES:
        assert LEGAL_TRANSITIONS.get(terminal, frozenset()) == frozenset()


def test_fsm_defaults_to_received() -> None:
    fsm = RunFSM()
    assert fsm.state is RunState.RECEIVED
    assert fsm.history == (RunState.RECEIVED,)


def test_fsm_transition_advances_and_records_history() -> None:
    fsm = (
        RunFSM()
        .transition(RunState.CLASSIFYING)
        .transition(RunState.DIRECT_PATH)
        .transition(RunState.SYNTHESIZING)
    )
    assert fsm.state is RunState.SYNTHESIZING
    assert fsm.history == (
        RunState.RECEIVED,
        RunState.CLASSIFYING,
        RunState.DIRECT_PATH,
        RunState.SYNTHESIZING,
    )


def test_fsm_illegal_transition_rejected() -> None:
    with pytest.raises(ValueError, match="illegal transition"):
        RunFSM().transition(RunState.PLANNING)  # RECEIVED -> PLANNING is not legal


def test_fsm_terminal_transition_rejected() -> None:
    completed = RunFSM().transition(RunState.CLASSIFYING).transition(RunState.MODELING)
    # drive to a terminal via a valid path: validating_model -> partial
    terminal = completed.transition(RunState.VALIDATING_MODEL).transition(RunState.PARTIAL)
    assert terminal.state is RunState.PARTIAL
    with pytest.raises(ValueError, match="terminal"):
        terminal.transition(RunState.PLANNING)


def test_fsm_transition_is_immutable() -> None:
    fsm = RunFSM()
    advanced = fsm.transition(RunState.CLASSIFYING)
    # original unchanged
    assert fsm.state is RunState.RECEIVED
    assert fsm.history == (RunState.RECEIVED,)
    assert advanced.state is RunState.CLASSIFYING


def test_fsm_history_must_start_with_received() -> None:
    with pytest.raises(ValueError, match="start with RECEIVED"):
        RunFSM(state=RunState.PLANNING, history=(RunState.PLANNING,))
