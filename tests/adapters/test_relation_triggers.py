"""Tests for M054 S03 — Relation triggers in BehaviorRuntime."""

from __future__ import annotations

import pytest

from active_skill_system.adapters.inmemory_trace_collector import InMemoryTraceCollector
from active_skill_system.adapters.relation_behavior_runtime import (
    RelationBehaviorRuntime,
)
from active_skill_system.domain.pattern import GraphView
from active_skill_system.domain.relation import Relation, RelationBehavior


def _graph_with_supports_edge() -> GraphView:
    return GraphView(
        vertices={
            "e1": {"type": "evidence"},
            "c1": {"type": "claim"},
        },
        edges=[{"kind": "supports", "source": "e1", "target": "c1"}],
    )


def _graph_empty() -> GraphView:
    return GraphView()


def _supports_relation_behavior() -> RelationBehavior:
    return RelationBehavior(
        name="evidence_linker",
        relation=Relation(kind="supports", source_type="evidence", target_type="claim"),
    )


# ── Registration ──────────────────────────────────────────────────────────


def test_register_relation_behavior_adds_trigger() -> None:
    rt = RelationBehaviorRuntime()
    rt.register_relation_behavior(_supports_relation_behavior(), lambda ctx: None)
    assert len(rt.list_relation_triggers()) == 1


def test_register_rejects_non_relation_behavior() -> None:
    rt = RelationBehaviorRuntime()
    with pytest.raises(TypeError, match="relation_behavior must be a RelationBehavior"):
        rt.register_relation_behavior("not-a-rb", lambda ctx: None)  # type: ignore[arg-type]


def test_register_rejects_non_callable_handler() -> None:
    rt = RelationBehaviorRuntime()
    with pytest.raises(TypeError, match="handler must be callable"):
        rt.register_relation_behavior(_supports_relation_behavior(), "not-callable")  # type: ignore[arg-type]


# ── Trigger firing ────────────────────────────────────────────────────────


def test_relation_trigger_fires_on_matching_edge() -> None:
    rt = RelationBehaviorRuntime()
    fired: list[str] = []
    rt.register_relation_behavior(
        _supports_relation_behavior(),
        lambda ctx: fired.append(ctx.event.payload["edge_kind"]),
    )

    fired_count = rt.check_relations(_graph_with_supports_edge())
    assert fired_count == 1
    assert len(fired) == 1
    assert fired[0] == "supports"


def test_relation_trigger_no_fire_on_empty_graph() -> None:
    rt = RelationBehaviorRuntime()
    fired: list[str] = []
    rt.register_relation_behavior(
        _supports_relation_behavior(),
        lambda ctx: fired.append("fired"),
    )

    fired_count = rt.check_relations(_graph_empty())
    assert fired_count == 0
    assert len(fired) == 0


def test_relation_trigger_no_refire_on_same_edge() -> None:
    rt = RelationBehaviorRuntime()
    fire_count = [0]
    rt.register_relation_behavior(
        _supports_relation_behavior(),
        lambda ctx: fire_count.__setitem__(0, fire_count[0] + 1),
    )

    graph = _graph_with_supports_edge()
    rt.check_relations(graph)
    rt.check_relations(graph)  # same edge — should not refire
    assert fire_count[0] == 1


def test_relation_trigger_wrong_kind_no_fire() -> None:
    rt = RelationBehaviorRuntime()
    fired: list[str] = []
    rt.register_relation_behavior(
        _supports_relation_behavior(),
        lambda ctx: fired.append("fired"),
    )

    # Edge with wrong kind (contradicts, not supports).
    graph = GraphView(
        vertices={"e1": {"type": "evidence"}, "c1": {"type": "claim"}},
        edges=[{"kind": "contradicts", "source": "e1", "target": "c1"}],
    )
    fired_count = rt.check_relations(graph)
    assert fired_count == 0


def test_relation_trigger_wrong_source_type_no_fire() -> None:
    rt = RelationBehaviorRuntime()
    fired: list[str] = []
    rt.register_relation_behavior(
        _supports_relation_behavior(),
        lambda ctx: fired.append("fired"),
    )

    # Edge from wrong source type (memo, not evidence).
    graph = GraphView(
        vertices={"m1": {"type": "memo"}, "c1": {"type": "claim"}},
        edges=[{"kind": "supports", "source": "m1", "target": "c1"}],
    )
    fired_count = rt.check_relations(graph)
    assert fired_count == 0


def test_multiple_relation_triggers_evaluated() -> None:
    rt = RelationBehaviorRuntime()
    fired: list[str] = []

    rt.register_relation_behavior(
        RelationBehavior(
            name="supports_handler",
            relation=Relation(kind="supports", source_type="evidence", target_type="claim"),
        ),
        lambda ctx: fired.append("supports"),
    )
    rt.register_relation_behavior(
        RelationBehavior(
            name="contradicts_handler",
            relation=Relation(kind="contradicts", source_type="claim", target_type="claim"),
        ),
        lambda ctx: fired.append("contradicts"),
    )

    graph = GraphView(
        vertices={"e1": {"type": "evidence"}, "c1": {"type": "claim"}, "c2": {"type": "claim"}},
        edges=[
            {"kind": "supports", "source": "e1", "target": "c1"},
            {"kind": "contradicts", "source": "c2", "target": "c1"},
        ],
    )
    rt.check_relations(graph)
    assert "supports" in fired
    assert "contradicts" in fired


# ── Trace instrumentation ─────────────────────────────────────────────────


def test_relation_trigger_trace_span() -> None:
    trace = InMemoryTraceCollector()
    rt = RelationBehaviorRuntime(trace=trace)
    rt.register_relation_behavior(
        RelationBehavior(
            name="linker",
            relation=Relation(kind="supports", source_type="evidence", target_type="claim"),
        ),
        lambda ctx: None,
    )

    rt.check_relations(_graph_with_supports_edge())
    spans = list(trace.iter_spans())
    assert len(spans) == 1
    assert "behavior.linker" in spans[0].operation
    assert spans[0].attributes.get("relation_kind") == "supports"


def test_relation_trigger_error_caught() -> None:
    rt = RelationBehaviorRuntime()
    rt.register_relation_behavior(
        _supports_relation_behavior(),
        lambda ctx: (_ for _ in ()).throw(ValueError("boom")),
    )

    # Should not raise.
    rt.check_relations(_graph_with_supports_edge())
    assert rt.list_relation_triggers()[0].fire_count == 1


# ── Inherits event + pattern dispatch ─────────────────────────────────────


def test_inherits_event_dispatch() -> None:
    """RelationBehaviorRuntime inherits event dispatch from parent."""
    from active_skill_system.domain.behavior import Behavior, EventMatcher
    from active_skill_system.domain.graph_primitives import GraphEvent

    rt = RelationBehaviorRuntime()
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


def test_inherits_pattern_dispatch() -> None:
    """RelationBehaviorRuntime inherits pattern dispatch from parent."""
    from active_skill_system.domain.pattern import Pattern, PatternClause

    rt = RelationBehaviorRuntime()
    pattern_fired: list[str] = []
    rt.register_pattern(
        Pattern(name="has_claim", clauses=(PatternClause(vertex_type="claim"),)),
        lambda ctx: pattern_fired.append("fired"),
    )
    rt.check_patterns(GraphView(vertices={"c1": {"type": "claim"}}))
    assert pattern_fired == ["fired"]
