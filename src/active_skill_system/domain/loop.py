"""L1 Domain — Loop entity and lifecycle (RGLA, D009).

A ``Loop`` is the primary unit of work in Recursive Graph Loop Architecture
(D009): an event-sourced, budget-bounded unit carrying an Intent, a state, a
lifecycle journal, and a REQUIRED Budget. This is the domain abstraction over an
ActiveGraph run (D009 §8) — it is NOT the runtime, only a typed model of one.

Design invariants (D009, enforced structurally):
  - **REQUIRED Budget.** Every Loop carries a non-null Budget with at least one
    bound (max_iterations / max_cost / deadline / max_llm_calls). A Loop with no
    termination bound is a contract violation — "loop never ends" is forbidden,
    not a feature. (Reinforced by RLM research: fast-rlm ships exactly these
    bounds as --max-depth/--max-calls — D011 §10.6.)
  - **Append-only lifecycle.** ``lifecycle`` is a tuple of ``LoopEvent`` records;
    ``state`` is a projection of the last event, never mutated independently.
  - **Typed transitions.** Only legal state transitions advance the Loop.

Pure domain. NO I/O, NO infrastructure imports (R002/R003). stdlib only.
Mirrors the shape of ``domain/runtime/fsm.py`` (frozen dataclass + StrEnum +
``__post_init__`` invariants) so the two FSMs are consistent siblings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class LoopState(StrEnum):
    """Lifecycle state of a Loop (D009 §4.1)."""

    PENDING = "pending"
    RUNNING = "running"
    VERIFYING = "verifying"
    DONE = "done"
    FAILED = "failed"
    RETAINED = "retained"


TERMINAL_LOOP_STATES = frozenset({LoopState.DONE, LoopState.FAILED, LoopState.RETAINED})


def _legal_loop_transitions() -> dict[LoopState, frozenset[LoopState]]:
    return {
        LoopState.PENDING: frozenset({LoopState.RUNNING, LoopState.FAILED, LoopState.RETAINED}),
        LoopState.RUNNING: frozenset(
            {LoopState.VERIFYING, LoopState.FAILED, LoopState.RETAINED, LoopState.DONE}
        ),
        LoopState.VERIFYING: frozenset(
            {LoopState.DONE, LoopState.FAILED, LoopState.RETAINED, LoopState.RUNNING}
        ),
    }


LEGAL_LOOP_TRANSITIONS: dict[LoopState, frozenset[LoopState]] = _legal_loop_transitions()


def is_legal_loop_transition(src: LoopState, dst: LoopState) -> bool:
    """True iff ``src`` may transition directly to ``dst``."""
    return dst in LEGAL_LOOP_TRANSITIONS.get(src, frozenset())


class LoopEventKind(StrEnum):
    """Semantic kinds of Loop lifecycle events (source of provenance edges, D009 §4.2)."""

    STARTED = "started"
    STATE_CHANGED = "state_changed"
    SKILL_USED = "skill_used"
    VERIFIED = "verified"
    FAILED = "failed"
    RETAINED = "retained"
    FINISHED = "finished"
    BUDGET_EXHAUSTED = "budget_exhausted"


@dataclass(frozen=True)
class Budget:
    """Termination bounds for a Loop — REQUIRED (D009 invariant).

    At least one of max_iterations / max_cost / deadline_iso / max_llm_calls
    MUST be set; an empty Budget is a contract violation (prevents "loop never
    ends"). All bounds are non-negative / non-empty when present.
    """

    max_iterations: int | None = None
    max_cost: float | None = None
    deadline_iso: str | None = None
    max_llm_calls: int | None = None

    def __post_init__(self) -> None:
        errors: list[str] = []
        for label, val in (
            ("max_iterations", self.max_iterations),
            ("max_llm_calls", self.max_llm_calls),
        ):
            if val is not None and (not isinstance(val, int) or isinstance(val, bool) or val < 1):
                errors.append(f"{label} must be a positive int or None (got {val!r})")
        if self.max_cost is not None and (
            not isinstance(self.max_cost, (int, float)) or isinstance(self.max_cost, bool) or self.max_cost < 0.0
        ):
            errors.append(f"max_cost must be a non-negative number or None (got {self.max_cost!r})")
        if self.deadline_iso is not None and (
            not isinstance(self.deadline_iso, str) or not self.deadline_iso.strip()
        ):
            errors.append(f"deadline_iso must be a non-empty string or None (got {self.deadline_iso!r})")
        if all(
            getattr(self, b) is None
            for b in ("max_iterations", "max_cost", "deadline_iso", "max_llm_calls")
        ):
            errors.append("Budget must set at least one bound (no unbounded Loops — D009)")
        if errors:
            raise ValueError("Budget invariant violation: " + "; ".join(errors))

    def exhausted(
        self,
        *,
        iterations_used: int = 0,
        cost_used: float = 0.0,
        llm_calls_used: int = 0,
        now_iso: str | None = None,
    ) -> bool:
        """True when any bound is reached/exceeded (termination signal)."""
        if self.max_iterations is not None and iterations_used >= self.max_iterations:
            return True
        if self.max_cost is not None and cost_used >= self.max_cost:
            return True
        if self.max_llm_calls is not None and llm_calls_used >= self.max_llm_calls:
            return True
        if self.deadline_iso is not None and now_iso is not None:
            return now_iso >= self.deadline_iso
        return False


@dataclass(frozen=True)
class LoopEvent:
    """One append-only lifecycle record for a Loop.

    The lifecycle journal is the source from which the LoopGraph provenance
    projection is derived (D009 §4.2). Each event carries its kind, the state
    the Loop was in, an optional typed payload, and an ISO-8601 timestamp.
    """

    kind: LoopEventKind
    state: LoopState
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.kind, LoopEventKind):
            errors.append(f"kind must be a LoopEventKind (got {type(self.kind).__name__})")
        if not isinstance(self.state, LoopState):
            errors.append(f"state must be a LoopState (got {type(self.state).__name__})")
        if not isinstance(self.payload, dict):
            errors.append(f"payload must be a dict (got {type(self.payload).__name__})")
        if not isinstance(self.timestamp, str):
            errors.append(f"timestamp must be a string (got {type(self.timestamp).__name__})")
        if errors:
            raise ValueError("LoopEvent invariant violation: " + "; ".join(errors))

    @staticmethod
    def now(kind: LoopEventKind, state: LoopState, payload: dict[str, Any] | None = None) -> LoopEvent:
        return LoopEvent(
            kind=kind,
            state=state,
            payload=dict(payload) if payload else {},
            timestamp=datetime.now(UTC).isoformat(timespec="seconds"),
        )


@dataclass(frozen=True)
class Loop:
    """A budget-bounded, event-sourced unit of work (D009 §4.1).

    Carries:
      - id: unique Loop id.
      - intent: declarative description of what the Loop is for.
      - budget: REQUIRED termination bounds (D009 invariant — no unbounded Loops).
      - skills: tuple of skill ids the Loop is composed of.
      - lifecycle: append-only tuple of LoopEvent records (starts with STARTED).
      - state: projection of the last lifecycle event (PENDING until STARTED).

    ``advance`` returns a NEW Loop with an appended event and projected state.
    Immutability + typed transitions mirror ``RunFSM``.
    """

    id: str
    intent: str
    budget: Budget
    skills: tuple[str, ...] = ()
    lifecycle: tuple[LoopEvent, ...] = ()
    state: LoopState = LoopState.PENDING

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.id, str) or not self.id.strip():
            errors.append(f"id must be a non-empty string (got {self.id!r})")
        if not isinstance(self.intent, str) or not self.intent.strip():
            errors.append(f"intent must be a non-empty string (got {self.intent!r})")
        if not isinstance(self.budget, Budget):
            errors.append(f"budget must be a Budget (got {type(self.budget).__name__})")
        if not isinstance(self.skills, tuple):
            errors.append(f"skills must be a tuple (got {type(self.skills).__name__})")
        if not isinstance(self.lifecycle, tuple):
            errors.append(f"lifecycle must be a tuple (got {type(self.lifecycle).__name__})")
        if not isinstance(self.state, LoopState):
            errors.append(f"state must be a LoopState (got {type(self.state).__name__})")
        # Consistency: state must equal the projection of the last event.
        if self.lifecycle:
            last = self.lifecycle[-1]
            if last.state is not self.state:
                errors.append(
                    f"state {self.state!r} must equal last lifecycle event state {last.state!r}"
                )
        else:
            if self.state is not LoopState.PENDING:
                errors.append(
                    f"a Loop with empty lifecycle must be PENDING (got {self.state!r})"
                )
        if errors:
            raise ValueError("Loop invariant violation: " + "; ".join(errors))

    def advance(
        self,
        event: LoopEvent,
        *,
        validate_transition: bool = True,
    ) -> Loop:
        """Return a new Loop with ``event`` appended and state projected.

        Args:
            event: the LoopEvent to append (its ``state`` becomes the new state).
            validate_transition: when True, reject illegal state transitions.

        Raises:
            ValueError: on illegal transition, terminal-state advance, or a state
                mismatch between the event and the current state projection.
        """
        if self.state in TERMINAL_LOOP_STATES:
            raise ValueError(
                f"Loop {self.id!r} in terminal state {self.state} cannot advance"
            )
        if validate_transition and not is_legal_loop_transition(self.state, event.state):
            raise ValueError(
                f"illegal loop transition: {self.state} -> {event.state} "
                f"(loop {self.id!r})"
            )
        return Loop(
            id=self.id,
            intent=self.intent,
            budget=self.budget,
            skills=self.skills,
            lifecycle=self.lifecycle + (event,),
            state=event.state,
        )

    @staticmethod
    def start(
        id: str,
        intent: str,
        budget: Budget,
        skills: tuple[str, ...] = (),
    ) -> Loop:
        """Create a Loop and immediately emit its STARTED event (→ RUNNING)."""
        loop = Loop(id=id, intent=intent, budget=budget, skills=skills)
        started = LoopEvent.now(LoopEventKind.STARTED, LoopState.RUNNING, {"intent": intent})
        return loop.advance(started, validate_transition=False)
