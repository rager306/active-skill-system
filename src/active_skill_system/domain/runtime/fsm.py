"""L1 Domain - Run FSM (Cognitive Runtime bounded context).

The Run FSM governs the lifecycle of a single request WITHOUT encoding every
reasoning concept as a state (concept.md §4.3). It answers "which phase is the
request in?" — distinct from the Task Graph ("what must be proven?") and the
Plan Graph ("what to execute?").

States + legal transitions follow concept.md §4.3 exactly. Terminal states
(completed / partial / failed / cancelled) accept no outgoing transitions.

Pure domain. NO I/O, NO infrastructure imports (R002). Frozen dataclass with
``__post_init__`` invariant validation. stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RunState(StrEnum):
    """Lifecycle state of a request (concept.md §4.3)."""

    RECEIVED = "received"
    CLASSIFYING = "classifying"
    DIRECT_PATH = "direct_path"
    MODELING = "modeling"
    VALIDATING_MODEL = "validating_model"
    REPAIRING = "repairing"
    WAITING_INPUT = "waiting_input"
    WAITING_APPROVAL = "waiting_approval"
    PLANNING = "planning"
    EXECUTING = "executing"
    SYNTHESIZING = "synthesizing"
    VALIDATING_OUTPUT = "validating_output"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


# States that accept no outgoing transitions.
TERMINAL_STATES = frozenset(
    {RunState.COMPLETED, RunState.PARTIAL, RunState.FAILED, RunState.CANCELLED}
)


def _legal() -> dict[RunState, frozenset[RunState]]:
    """Legal outgoing transitions per source state (concept.md §4.3 diagram)."""
    return {
        RunState.RECEIVED: frozenset({RunState.CLASSIFYING, RunState.CANCELLED}),
        RunState.CLASSIFYING: frozenset(
            {RunState.DIRECT_PATH, RunState.MODELING, RunState.CANCELLED}
        ),
        RunState.DIRECT_PATH: frozenset({RunState.SYNTHESIZING}),
        RunState.MODELING: frozenset(
            {RunState.VALIDATING_MODEL, RunState.CANCELLED}
        ),
        RunState.VALIDATING_MODEL: frozenset(
            {RunState.PLANNING, RunState.REPAIRING, RunState.PARTIAL, RunState.CANCELLED}
        ),
        RunState.REPAIRING: frozenset(
            {RunState.VALIDATING_MODEL, RunState.WAITING_INPUT, RunState.WAITING_APPROVAL}
        ),
        RunState.WAITING_INPUT: frozenset({RunState.MODELING}),
        RunState.WAITING_APPROVAL: frozenset({RunState.PLANNING, RunState.PARTIAL}),
        RunState.PLANNING: frozenset({RunState.EXECUTING}),
        RunState.EXECUTING: frozenset(
            {RunState.VALIDATING_MODEL, RunState.REPAIRING, RunState.SYNTHESIZING}
        ),
        RunState.SYNTHESIZING: frozenset({RunState.VALIDATING_OUTPUT}),
        RunState.VALIDATING_OUTPUT: frozenset(
            {RunState.COMPLETED, RunState.REPAIRING, RunState.PARTIAL, RunState.FAILED}
        ),
    }


LEGAL_TRANSITIONS: dict[RunState, frozenset[RunState]] = _legal()


def is_legal_transition(src: RunState, dst: RunState) -> bool:
    """True iff ``src`` may transition directly to ``dst`` (concept.md §4.3)."""
    return dst in LEGAL_TRANSITIONS.get(src, frozenset())


@dataclass(frozen=True)
class RunFSM:
    """A request's lifecycle state + transition history.

    Carries:
      - state: current RunState (RECEIVED by default).
      - history: tuple of states visited, starting with the initial state.

    ``transition(dst)`` returns a NEW RunFSM (immutability) and raises ValueError
    if ``dst`` is not a legal successor of the current state or the current state
    is terminal.
    """

    state: RunState = RunState.RECEIVED
    history: tuple[RunState, ...] = (RunState.RECEIVED,)

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.state, RunState):
            errors.append(f"state must be a RunState (got {type(self.state).__name__})")
        if not isinstance(self.history, tuple) or len(self.history) == 0:
            errors.append(f"history must be a non-empty tuple (got {self.history!r})")
        elif self.history[0] is not RunState.RECEIVED:
            errors.append(
                f"history must start with RECEIVED (got {self.history[0]})"
            )
        if errors:
            raise ValueError("RunFSM invariant violation: " + "; ".join(errors))

    def transition(self, dst: RunState) -> RunFSM:
        """Return a new RunFSM advanced to ``dst``.

        Raises:
            ValueError: if ``dst`` is not a legal successor of ``self.state``,
                or ``self.state`` is terminal.
        """
        if not isinstance(dst, RunState):
            raise ValueError(f"transition target must be a RunState (got {type(dst).__name__})")
        if self.state in TERMINAL_STATES:
            raise ValueError(
                f"RunFSM in terminal state {self.state} cannot transition (to {dst})"
            )
        if not is_legal_transition(self.state, dst):
            raise ValueError(
                f"illegal transition: {self.state} -> {dst} is not in the legal table"
            )
        return RunFSM(state=dst, history=self.history + (dst,))
