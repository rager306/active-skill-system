"""Tests for M053 S09 — Composition reactive behavior wiring."""

from __future__ import annotations

from active_skill_system.adapters.inmemory_trace_collector import InMemoryTraceCollector
from active_skill_system.composition.sandbox.reactive_ops import (
    build_reactive_stack,
    run_behavior_demo,
)
from active_skill_system.domain.graph_primitives import GraphEvent


def test_build_reactive_stack_creates_all_components() -> None:
    runtime, applier, gate = build_reactive_stack()
    assert runtime is not None
    assert applier is not None
    assert gate is not None
    # Should have 3 preset behaviors registered.
    assert len(runtime.list_registrations()) == 3
    # Should have 1 policy registered.
    assert len(gate.list_policies()) == 1


def test_build_reactive_stack_with_trace() -> None:
    trace = InMemoryTraceCollector()
    runtime, _, _ = build_reactive_stack(trace=trace)
    assert runtime._trace is trace


def test_reactive_stack_behaviors_fire_on_event() -> None:
    """Publishing claim.created fires evidence_check behavior."""
    runtime, applier, _ = build_reactive_stack()

    event = GraphEvent(
        id="e1", type="claim.created",
        payload={"claim_id": "c1", "text": "test"},
        actor="test", run_id="r1", timestamp_ns=1,
    )
    runtime.publish(event)

    # evidence_check should have fired and proposed a patch.
    assert len(applier.list_pending()) >= 1


def test_reactive_stack_gap_event_fires_gap_filler() -> None:
    runtime, applier, _ = build_reactive_stack()

    event = GraphEvent(
        id="e1", type="gap.detected",
        payload={"gap_type": "missing_data"},
        actor="test", run_id="r1", timestamp_ns=1,
    )
    runtime.publish(event)

    # gap_filler should have fired.
    assert len(applier.list_pending()) >= 1


def test_behavior_demo_runs_successfully(capsys) -> None:  # type: ignore[no-untyped-def]
    """The demo CLI runs without error and produces output."""
    exit_code = run_behavior_demo(None)
    assert exit_code == 0

    captured = capsys.readouterr()
    assert "Reactive Behavior Demo" in captured.out
    assert "claim.created" in captured.out
    assert "evidence_check" in captured.out
    assert "gap.detected" in captured.out
    assert "Trace:" in captured.out


def test_behavior_demo_shows_trace_spans(capsys) -> None:  # type: ignore[no-untyped-def]
    """Demo output includes trace span information."""
    run_behavior_demo(None)
    captured = capsys.readouterr()
    assert "spans" in captured.out
