"""L1 Domain — TrajectoryStep and TrajectoryRecorder (Wave 2 P1, M048 S01).

A TrajectoryStep is a typed record of one agent action during a sandbox run:
prompt build, LLM response, code extract, autofix, executor gate, verify,
finish, failure. Steps are recorded in order and projected into the LoopGraph
as TRAJECTORY_STEP vertices connected by NEXT edges.

Pure domain. No I/O, no infrastructure imports.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from enum import StrEnum


class TrajectoryStepKind(StrEnum):
    """Standard step kinds recorded during a sandbox agent run."""

    PROMPT_BUILD = "prompt_build"
    LLM_RESPOND = "llm_respond"
    CODE_EXTRACT = "code_extract"
    CANDIDATE_WRITE = "candidate_write"
    AUTOFIX = "autofix"
    EXECUTOR_GATE = "executor_gate"
    VERIFY = "verify"
    FINISH = "finish"
    FAILURE = "failure"


@dataclass(frozen=True)
class TrajectoryStep:
    """One recorded agent step.

    Fields:
      - id: unique step id (uuid hex).
      - step_kind: a TrajectoryStepKind.
      - timestamp: unix time (seconds since epoch).
      - duration_ms: optional wall-clock duration in milliseconds.
      - model: optional model name (for LLM_RESPOND).
      - note: optional short human-readable note (e.g. error reason).
    """

    id: str
    step_kind: TrajectoryStepKind
    timestamp: float
    duration_ms: float | None = None
    model: str | None = None
    note: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError(f"id must be non-empty string (got {self.id!r})")
        if not isinstance(self.step_kind, TrajectoryStepKind):
            raise ValueError(f"step_kind must be TrajectoryStepKind (got {type(self.step_kind).__name__})")


class TrajectoryRecorder:
    """In-memory step recorder. Append-only. Returns tuple on demand.

    Usage::

        rec = TrajectoryRecorder()
        rec.add(TrajectoryStepKind.PROMPT_BUILD, model=model)
        ...
        steps = rec.steps()
    """

    def __init__(self, run_id: str | None = None) -> None:
        self._run_id = run_id or uuid.uuid4().hex[:8]
        self._steps: list[TrajectoryStep] = []
        self._last_t: float = time.time()

    @property
    def run_id(self) -> str:
        return self._run_id

    def add(
        self,
        kind: TrajectoryStepKind,
        *,
        model: str | None = None,
        note: str | None = None,
        duration_ms: float | None = None,
    ) -> TrajectoryStep:
        now = time.time()
        if duration_ms is None:
            duration_ms = (now - self._last_t) * 1000.0
        step = TrajectoryStep(
            id=f"{self._run_id}-{len(self._steps):03d}",
            step_kind=kind,
            timestamp=now,
            duration_ms=duration_ms,
            model=model,
            note=note,
        )
        self._steps.append(step)
        self._last_t = now
        return step

    def steps(self) -> tuple[TrajectoryStep, ...]:
        return tuple(self._steps)

    def __len__(self) -> int:
        return len(self._steps)