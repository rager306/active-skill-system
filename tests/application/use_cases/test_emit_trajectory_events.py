"""Tests for M051 S03 — emit_trajectory_events + composition wiring."""

from __future__ import annotations

from active_skill_system.adapters.event_store_impl import EventStoreImpl
from active_skill_system.adapters.inmemory_event_log import InMemoryEventLog
from active_skill_system.application.use_cases.emit_trajectory_events import (
    emit_trajectory_events,
)
from active_skill_system.domain.graph_primitives import GraphEventType
from active_skill_system.domain.trajectory import (
    TrajectoryRecorder,
    TrajectoryStepKind,
)


def _record_steps() -> tuple:
    rec = TrajectoryRecorder(run_id="r1")
    rec.add(TrajectoryStepKind.PROMPT_BUILD, model="m")
    rec.add(TrajectoryStepKind.LLM_RESPOND, model="m")
    rec.add(TrajectoryStepKind.VERIFY, note="score=1.00")
    rec.add(TrajectoryStepKind.FINISH)
    return rec.steps()


def test_emit_emits_one_event_per_step() -> None:
    store = EventStoreImpl(InMemoryEventLog())
    steps = _record_steps()
    n = emit_trajectory_events(steps=steps, store=store, run_id="r1")
    assert n == 4
    events = list(store.iter_events())
    assert len(events) == 4


def test_emit_maps_step_kinds_to_event_types() -> None:
    store = EventStoreImpl(InMemoryEventLog())
    steps = _record_steps()
    emit_trajectory_events(steps=steps, store=store, run_id="r1")
    types = [e.type for e in store.iter_events()]
    assert GraphEventType.LLM_REQUESTED in types  # prompt_build
    assert GraphEventType.LLM_RESPONDED in types  # llm_respond
    assert GraphEventType.BEHAVIOR_COMPLETED in types  # finish


def test_emit_carries_model_in_payload() -> None:
    store = EventStoreImpl(InMemoryEventLog())
    steps = _record_steps()
    emit_trajectory_events(steps=steps, store=store, run_id="r1")
    llm_events = [e for e in store.iter_events() if e.type == GraphEventType.LLM_RESPONDED]
    assert llm_events[0].payload.get("model") == "m"


def test_emit_is_idempotent_on_step_id() -> None:
    store = EventStoreImpl(InMemoryEventLog())
    steps = _record_steps()
    emit_trajectory_events(steps=steps, store=store, run_id="r1")
    emit_trajectory_events(steps=steps, store=store, run_id="r1")  # re-emit
    assert len(list(store.iter_events())) == 4  # no duplicates


def test_emit_chains_caused_by() -> None:
    store = EventStoreImpl(InMemoryEventLog())
    steps = _record_steps()
    emit_trajectory_events(steps=steps, store=store, run_id="r1")
    events = list(store.iter_events())
    # First event has empty caused_by; subsequent ones chain to previous.
    assert events[0].caused_by == ""
    assert events[1].caused_by == events[0].id
    assert events[2].caused_by == events[1].id


def test_emit_empty_steps_emits_nothing() -> None:
    store = EventStoreImpl(InMemoryEventLog())
    n = emit_trajectory_events(steps=(), store=store, run_id="r1")
    assert n == 0
    assert len(list(store.iter_events())) == 0


def test_emit_failure_step_maps_to_behavior_failed() -> None:
    store = EventStoreImpl(InMemoryEventLog())
    rec = TrajectoryRecorder(run_id="r2")
    rec.add(TrajectoryStepKind.PROMPT_BUILD)
    rec.add(TrajectoryStepKind.FAILURE, note="boom")
    emit_trajectory_events(steps=rec.steps(), store=store, run_id="r2")
    types = [e.type for e in store.iter_events()]
    assert GraphEventType.BEHAVIOR_FAILED in types
