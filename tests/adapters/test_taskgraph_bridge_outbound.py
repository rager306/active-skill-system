"""Unit tests for TaskGraphBridge outbound projection (M004 S01).

Drives the bridge with a ListEventSink (in-memory fake collector) and asserts
that every domain operation serializes to a structured, round-trip-ready event
payload. The payloads are consumed by S02's apply_event, so this slice
establishes the serialization contract that the inbound side depends on.
"""

from __future__ import annotations

import pytest

from active_skill_system.adapters.taskgraph_bridge import (
    EVENT_CLAIM_PROMOTED,
    EVENT_EDGE_ADDED,
    EVENT_FSM_TRANSITIONED,
    EVENT_GRAPH_COMMITTED,
    EVENT_NODE_ADDED,
    ListEventSink,
    TaskGraphBridge,
)
from active_skill_system.domain.runtime import (
    ClaimStatus,
    EdgeKind,
    NodeKind,
    RunFSM,
    RunState,
    TaskEdge,
    TaskGraph,
    TaskNode,
    TaskNodeId,
)


def _bridge() -> tuple[TaskGraphBridge, ListEventSink]:
    sink = ListEventSink()
    return TaskGraphBridge(sink), sink


def test_on_node_added_emits_round_trip_ready_payload() -> None:
    bridge, sink = _bridge()
    bridge.on_node_added(
        TaskNode(id=TaskNodeId("g1"), kind=NodeKind.GOAL, text="answer X")
    )
    assert len(sink.events) == 1
    e = sink.events[0]
    assert e.event_type == EVENT_NODE_ADDED
    assert e.payload == {"id": "g1", "kind": "goal", "text": "answer X"}


def test_on_edge_added_emits_round_trip_ready_payload() -> None:
    bridge, sink = _bridge()
    bridge.on_edge_added(
        TaskEdge(
            source=TaskNodeId("a"),
            target=TaskNodeId("b"),
            kind=EdgeKind.SUPPORTS,
        )
    )
    assert sink.events[0].event_type == EVENT_EDGE_ADDED
    assert sink.events[0].payload == {
        "source": "a",
        "target": "b",
        "kind": "supports",
    }


def test_on_graph_committed_emits_version_pair() -> None:
    bridge, sink = _bridge()
    g = TaskGraph().add_node(
        TaskNode(id=TaskNodeId("g1"), kind=NodeKind.GOAL, text="G")
    ).commit()
    bridge.on_graph_committed(g, prev_version=0)
    assert sink.events[0].event_type == EVENT_GRAPH_COMMITTED
    assert sink.events[0].payload == {"version": 2, "prev_version": 0}


def test_on_claim_promoted_emits_status_transition() -> None:
    bridge, sink = _bridge()
    bridge.on_claim_promoted("c1", ClaimStatus.PROPOSED, ClaimStatus.VERIFIED)
    assert sink.events[0].event_type == EVENT_CLAIM_PROMOTED
    assert sink.events[0].payload == {
        "claim_id": "c1",
        "prev_status": "proposed",
        "new_status": "verified",
    }


def test_on_fsm_transitioned_emits_state_transition() -> None:
    bridge, sink = _bridge()
    fsm = RunFSM().transition(RunState.CLASSIFYING)
    bridge.on_fsm_transitioned(
        run_id="run1",
        prev_state_value=RunState.RECEIVED.value,
        new_state_value=fsm.state.value,
    )
    assert sink.events[0].event_type == EVENT_FSM_TRANSITIONED
    assert sink.events[0].payload == {
        "run_id": "run1",
        "prev_state": "received",
        "new_state": "classifying",
    }


def test_bridge_collects_multiple_events_in_order() -> None:
    """Ordering matters: S02 replays the same sequence to reconstruct the graph."""
    bridge, sink = _bridge()
    bridge.on_node_added(TaskNode(TaskNodeId("a"), NodeKind.FACT, "A"))
    bridge.on_node_added(TaskNode(TaskNodeId("b"), NodeKind.FACT, "B"))
    bridge.on_edge_added(
        TaskEdge(TaskNodeId("a"), TaskNodeId("b"), EdgeKind.SUPPORTS)
    )
    assert [e.event_type for e in sink.events] == [
        EVENT_NODE_ADDED,
        EVENT_NODE_ADDED,
        EVENT_EDGE_ADDED,
    ]


def test_bridge_helper_events_property_exposes_sink_events() -> None:
    bridge, sink = _bridge()
    assert list(bridge.events) == []
    bridge.on_node_added(TaskNode(TaskNodeId("x"), NodeKind.FACT, "x"))
    assert len(list(bridge.events)) == 1


def test_bridge_helper_events_raises_for_non_buffering_sink() -> None:
    """A production-style sink (no .events attribute) signals an AttributeError."""

    class _SinkingEventSink:
        def emit(self, event_type, payload):  # noqa: ANN001
            pass

    bridge = TaskGraphBridge(_SinkingEventSink())
    with pytest.raises(AttributeError, match="no .events"):
        list(bridge.events)
