"""L2 Application — emit trajectory events to EventStore (M051 S03, Wave A).

Bridges the existing TrajectoryRecorder (domain/trajectory.py) output to the
new EventStore port (application/ports/event_store.py). Called by composition
after a SandboxAgentRunner.run() completes; emits one GraphEvent per
trajectory step into the EventStore, additive to the existing LadybugDB
LoopGraph provenance.

Pure application (R002): depends only on ports + domain types.
"""

from __future__ import annotations

from active_skill_system.application.ports.event_store import EventStore
from active_skill_system.domain.graph_primitives import GraphEvent, GraphEventType
from active_skill_system.domain.trajectory import TrajectoryStep, TrajectoryStepKind

# Map TrajectoryStepKind → GraphEvent type string.
_STEP_TO_EVENT_TYPE: dict[TrajectoryStepKind, str] = {
    TrajectoryStepKind.PROMPT_BUILD: GraphEventType.LLM_REQUESTED,
    TrajectoryStepKind.LLM_RESPOND: GraphEventType.LLM_RESPONDED,
    TrajectoryStepKind.CODE_EXTRACT: "trajectory.code_extract",
    TrajectoryStepKind.CANDIDATE_WRITE: "trajectory.candidate_write",
    TrajectoryStepKind.AUTOFIX: "trajectory.autofix",
    TrajectoryStepKind.EXECUTOR_GATE: "tool.requested",
    TrajectoryStepKind.VERIFY: "trajectory.verify",
    TrajectoryStepKind.FINISH: GraphEventType.BEHAVIOR_COMPLETED,
    TrajectoryStepKind.FAILURE: GraphEventType.BEHAVIOR_FAILED,
}


def emit_trajectory_events(
    *,
    steps: tuple[TrajectoryStep, ...],
    store: EventStore,
    run_id: str,
    actor: str = "sandbox-agent",
) -> int:
    """Emit one GraphEvent per trajectory step into the EventStore.

    Returns the number of events emitted. Idempotent: re-emitting the same
    steps is a no-op (EventStore.append is idempotent on event id).
    """
    count = 0
    caused_by = ""
    for step in steps:
        etype = _STEP_TO_EVENT_TYPE.get(step.step_kind, "trajectory.step")
        payload: dict = {"step_kind": step.step_kind.value}
        if step.model:
            payload["model"] = step.model
        if step.note:
            payload["note"] = step.note
        if step.duration_ms is not None:
            payload["duration_ms"] = step.duration_ms
        event = GraphEvent.now(
            etype,
            payload=payload,
            actor=actor,
            run_id=run_id,
            caused_by=caused_by,
            event_id=f"evt-{step.id}",  # deterministic id from step id
        )
        store.append(event)
        caused_by = event.id
        count += 1
    return count
