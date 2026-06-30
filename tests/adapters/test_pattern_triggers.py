"""Tests for M053 S07 — Pattern triggers in BehaviorRuntime."""

from __future__ import annotations

import pytest

from active_skill_system.adapters.inmemory_trace_collector import InMemoryTraceCollector
from active_skill_system.adapters.pattern_behavior_runtime import (
    PatternBehaviorRuntime,
)
from active_skill_system.domain.pattern import (
    GraphView,
    Pattern,
    PatternClause,
    PatternCondition,
)


def _empty_graph() -> GraphView:
    return GraphView()


def _graph_with_claim(claim_id: str = "c1") -> GraphView:
    return GraphView(vertices={claim_id: {"type": "claim", "status": "open"}})


def _claim_without_evidence_pattern() -> Pattern:
    return Pattern(
        name="claim_without_evidence",
        clauses=(
            PatternClause(vertex_type="claim", condition=PatternCondition.EXISTS),
            PatternClause(vertex_type="evidence", condition=PatternCondition.NOT_EXISTS),
        ),
        description="Fires when a claim exists without evidence",
    )


# ── Registration ───────────────────────────────────────────────────────────


def test_register_pattern_adds_trigger() -> None:
    rt = PatternBehaviorRuntime()
    rt.register_pattern(_claim_without_evidence_pattern(), lambda ctx: None)
    assert len(rt.list_pattern_triggers()) == 1


def test_register_pattern_rejects_non_pattern() -> None:
    rt = PatternBehaviorRuntime()
    with pytest.raises(TypeError, match="pattern must be a Pattern"):
        rt.register_pattern("not-a-pattern", lambda ctx: None)  # type: ignore[arg-type]


def test_register_pattern_rejects_non_callable() -> None:
    rt = PatternBehaviorRuntime()
    with pytest.raises(TypeError, match="handler must be callable"):
        rt.register_pattern(_claim_without_evidence_pattern(), "not-callable")  # type: ignore[arg-type]


# ── Pattern trigger firing ─────────────────────────────────────────────────


def test_pattern_fires_on_transition() -> None:
    """Pattern fires when graph transitions from not-matching to matching."""
    rt = PatternBehaviorRuntime()
    fired: list[str] = []
    rt.register_pattern(
        _claim_without_evidence_pattern(),
        lambda ctx: fired.append(ctx.event.payload["pattern_name"]),
    )

    # Empty graph → pattern doesn't match (no claim).
    fired_count = rt.check_patterns(_empty_graph())
    assert fired_count == 0
    assert len(fired) == 0

    # Add claim → pattern now matches → fires.
    fired_count = rt.check_patterns(_graph_with_claim())
    assert fired_count == 1
    assert len(fired) == 1
    assert fired[0] == "claim_without_evidence"


def test_pattern_does_not_refire_on_same_state() -> None:
    """Pattern doesn't fire again if it's still matching (no re-transition)."""
    rt = PatternBehaviorRuntime()
    fire_count = [0]
    rt.register_pattern(
        _claim_without_evidence_pattern(),
        lambda ctx: fire_count.__setitem__(0, fire_count[0] + 1),
    )

    # First check: matches → fires.
    rt.check_patterns(_graph_with_claim())
    assert fire_count[0] == 1

    # Second check: still matches → does NOT fire again.
    rt.check_patterns(_graph_with_claim())
    assert fire_count[0] == 1


def test_pattern_refires_after_reset() -> None:
    """Pattern can fire again after state resets (match → no-match → match)."""
    rt = PatternBehaviorRuntime()
    fire_count = [0]
    rt.register_pattern(
        _claim_without_evidence_pattern(),
        lambda ctx: fire_count.__setitem__(0, fire_count[0] + 1),
    )

    # Match → fires.
    rt.check_patterns(_graph_with_claim())
    assert fire_count[0] == 1

    # No match → resets (last_matched=False).
    rt.check_patterns(_empty_graph())
    assert fire_count[0] == 1

    # Match again → fires again.
    rt.check_patterns(_graph_with_claim())
    assert fire_count[0] == 2


def test_multiple_patterns_evaluated() -> None:
    """Multiple patterns are all evaluated on check_patterns."""
    rt = PatternBehaviorRuntime()
    fired: list[str] = []

    rt.register_pattern(
        Pattern(name="has_claim", clauses=(PatternClause(vertex_type="claim"),)),
        lambda ctx: fired.append("has_claim"),
    )
    rt.register_pattern(
        Pattern(name="has_evidence", clauses=(PatternClause(vertex_type="evidence"),)),
        lambda ctx: fired.append("has_evidence"),
    )

    rt.check_patterns(_graph_with_claim())
    assert "has_claim" in fired
    assert "has_evidence" not in fired  # no evidence in graph


# ── Trace instrumentation ──────────────────────────────────────────────────


def test_pattern_trigger_trace_span() -> None:
    """Pattern triggers get trace spans."""
    trace = InMemoryTraceCollector()
    rt = PatternBehaviorRuntime(trace=trace)
    rt.register_pattern(
        _claim_without_evidence_pattern(),
        lambda ctx: None,
        behavior_name="evidence_check",
    )

    rt.check_patterns(_graph_with_claim())
    spans = list(trace.iter_spans())
    assert len(spans) == 1
    assert "behavior.evidence_check" in spans[0].operation
    assert spans[0].attributes.get("pattern_name") == "claim_without_evidence"


def test_pattern_trigger_error_caught() -> None:
    """Pattern trigger handler errors are caught (runtime doesn't crash)."""
    rt = PatternBehaviorRuntime()
    rt.register_pattern(
        _claim_without_evidence_pattern(),
        lambda ctx: (_ for _ in ()).throw(ValueError("boom")),
    )

    # Should not raise.
    rt.check_patterns(_graph_with_claim())

    # The trigger should have fired (fire_count incremented).
    assert rt.list_pattern_triggers()[0].fire_count == 1


# ── Integration with event dispatch ────────────────────────────────────────


def test_pattern_runtime_also_supports_event_behaviors() -> None:
    """PatternBehaviorRuntime inherits event dispatch from parent."""
    from active_skill_system.domain.behavior import Behavior, EventMatcher
    from active_skill_system.domain.graph_primitives import GraphEvent

    rt = PatternBehaviorRuntime()
    event_fired: list[str] = []

    rt.register(
        Behavior(name="event_behavior", matcher=EventMatcher(event_types=("test.event",))),
        lambda ctx: event_fired.append("fired"),
    )

    rt.publish(GraphEvent(
        id="e1", type="test.event", payload={},
        actor="test", run_id="r1", timestamp_ns=1,
    ))
    assert event_fired == ["fired"]
