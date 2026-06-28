"""Tests for M048 S01 — TrajectoryStep + TrajectoryRecorder + LoopGraph extension."""

from __future__ import annotations

import pytest

from active_skill_system.domain.loop import Budget, Loop
from active_skill_system.domain.loop_graph import (
    LoopEdgeKind,
    LoopVertexKind,
    project,
)
from active_skill_system.domain.trajectory import (
    TrajectoryRecorder,
    TrajectoryStep,
    TrajectoryStepKind,
)


def _make_loop() -> Loop:
    return Loop.start(
        id="test-loop-1",
        intent="test intent",
        budget=Budget(max_llm_calls=1, max_cost=0.05),
        skills=("sandbox-cache-task",),
    )


def test_trajectory_step_post_init_rejects_empty_id() -> None:
    with pytest.raises(ValueError, match="id must be non-empty"):
        TrajectoryStep(id="", step_kind=TrajectoryStepKind.PROMPT_BUILD, timestamp=0.0)


def test_trajectory_step_post_init_rejects_bad_kind() -> None:
    with pytest.raises(ValueError, match="step_kind must be TrajectoryStepKind"):
        TrajectoryStep(id="x", step_kind="not-a-kind", timestamp=0.0)  # type: ignore[arg-type]


def test_recorder_records_steps_in_order() -> None:
    rec = TrajectoryRecorder(run_id="r1")
    rec.add(TrajectoryStepKind.PROMPT_BUILD, model="m")
    rec.add(TrajectoryStepKind.LLM_RESPOND, model="m")
    rec.add(TrajectoryStepKind.VERIFY, note="score=1.00")
    steps = rec.steps()
    assert len(steps) == 3
    assert [s.step_kind for s in steps] == [
        TrajectoryStepKind.PROMPT_BUILD,
        TrajectoryStepKind.LLM_RESPOND,
        TrajectoryStepKind.VERIFY,
    ]


def test_recorder_step_ids_are_unique_and_sequential() -> None:
    rec = TrajectoryRecorder(run_id="r2")
    s1 = rec.add(TrajectoryStepKind.PROMPT_BUILD)
    s2 = rec.add(TrajectoryStepKind.LLM_RESPOND)
    assert s1.id != s2.id
    assert s1.id.endswith("-000")
    assert s2.id.endswith("-001")


def test_recorder_computes_duration_ms_when_not_given() -> None:
    rec = TrajectoryRecorder(run_id="r3")
    s = rec.add(TrajectoryStepKind.PROMPT_BUILD)
    assert s.duration_ms is not None
    assert s.duration_ms >= 0.0


def test_recorder_accepts_explicit_duration_ms() -> None:
    rec = TrajectoryRecorder(run_id="r4")
    s = rec.add(TrajectoryStepKind.VERIFY, duration_ms=123.4)
    assert s.duration_ms == 123.4


def test_project_without_trajectory_emits_no_trajectory_vertices() -> None:
    loop = _make_loop()
    g = project(loop)
    kinds = {v.kind for v in g.vertices}
    assert LoopVertexKind.TRAJECTORY_STEP not in kinds


def test_project_with_trajectory_emits_vertices_and_next_edges() -> None:
    loop = _make_loop()
    rec = TrajectoryRecorder(run_id="proj1")
    rec.add(TrajectoryStepKind.PROMPT_BUILD)
    rec.add(TrajectoryStepKind.LLM_RESPOND)
    rec.add(TrajectoryStepKind.VERIFY)
    g = project(loop, trajectory=rec.steps())

    traj_vertices = [v for v in g.vertices if v.kind == LoopVertexKind.TRAJECTORY_STEP]
    assert len(traj_vertices) == 3
    assert all(v.label == step.step_kind.value for v, step in zip(traj_vertices, rec.steps(), strict=True))

    next_edges = [e for e in g.edges if e.kind == LoopEdgeKind.NEXT]
    assert len(next_edges) == 2

    uses_edges = [e for e in g.edges if e.kind == LoopEdgeKind.USES and "trajectory_step" in e.dst]
    assert len(uses_edges) == 3


def test_project_trajectory_step_payload_carries_metadata() -> None:
    loop = _make_loop()
    rec = TrajectoryRecorder(run_id="proj2")
    rec.add(TrajectoryStepKind.LLM_RESPOND, model="minimax/MiniMax-M3")
    g = project(loop, trajectory=rec.steps())
    uses_edges = [e for e in g.edges if e.kind == LoopEdgeKind.USES and "trajectory_step" in e.dst]
    assert len(uses_edges) == 1
    payload = uses_edges[0].payload
    assert payload["step_kind"] == "llm_respond"
    assert payload["model"] == "minimax/MiniMax-M3"


def test_project_trajectory_is_idempotent() -> None:
    loop = _make_loop()
    rec = TrajectoryRecorder(run_id="proj3")
    rec.add(TrajectoryStepKind.PROMPT_BUILD)
    rec.add(TrajectoryStepKind.FINISH)
    g1 = project(loop, trajectory=rec.steps())
    g2 = project(loop, trajectory=rec.steps())
    assert g1.vertices == g2.vertices
    assert g1.edges == g2.edges
