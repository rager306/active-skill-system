"""Tests for ActivegraphEventSink + replay contract (M005).

S01: ActivegraphEventSink (production EventSink over activegraph.Graph.emit).
S02: replay contract — out(ops) → sink → graph.events → TaskGraphState.apply_event
→ restored graph/claim/fsm == original. R5 / C9 / C13 closed by M005.
"""

from __future__ import annotations

import pytest
from activegraph import Graph

from active_skill_system.adapters.activegraph_event_sink import ActivegraphEventSink
from active_skill_system.adapters.taskgraph_bridge import (
    EVENT_CLAIM_PROMOTED,
    EVENT_EDGE_ADDED,
    EVENT_FSM_TRANSITIONED,
    EVENT_NODE_ADDED,
    TaskGraphBridge,
    TaskGraphState,
)
from active_skill_system.domain.runtime import (
    ClaimStatus,
    EdgeKind,
    NodeKind,
    RunState,
    TaskEdge,
    TaskNode,
    TaskNodeId,
)

# ── S01: ActivegraphEventSink (production EventSink) ──────────────────────


def test_sink_emits_event_into_real_graph() -> None:
    g = Graph()
    sink = ActivegraphEventSink(g)
    sink.emit("task.node.added", {"id": "n1", "kind": "fact", "text": "X"})
    events = list(g.events)
    assert len(events) == 1
    assert events[0].type == "task.node.added"
    assert events[0].payload == {"id": "n1", "kind": "fact", "text": "X"}


def test_sink_assigns_unique_event_ids() -> None:
    g = Graph()
    sink = ActivegraphEventSink(g)
    for i in range(5):
        sink.emit("task.node.added", {"id": f"n{i}", "kind": "fact", "text": ""})
    ids = {e.id for e in g.events}
    assert len(ids) == 5  # all distinct


def test_sink_rejects_bad_input() -> None:
    g = Graph()
    sink = ActivegraphEventSink(g)
    with pytest.raises(ValueError, match="non-empty string"):
        sink.emit("", {"k": "v"})
    with pytest.raises(ValueError, match="must be a dict"):
        sink.emit("task.x", "not a dict")  # type: ignore[arg-type]


def test_sink_constructor_rejects_none() -> None:
    with pytest.raises(ValueError, match="non-None"):
        ActivegraphEventSink(None)  # type: ignore[arg-type]


def test_bridge_to_real_activegraph_sink_passes_all_5_operations() -> None:
    """S01 climax: bridge → production sink → graph.events contains 5 events."""
    g = Graph()
    sink = ActivegraphEventSink(g)
    bridge = TaskGraphBridge(sink)

    bridge.on_node_added(TaskNode(TaskNodeId("g"), NodeKind.GOAL, "G"))
    bridge.on_node_added(TaskNode(TaskNodeId("e"), NodeKind.EVIDENCE, ""))
    bridge.on_edge_added(TaskEdge(TaskNodeId("e"), TaskNodeId("g"), EdgeKind.SUPPORTS))
    bridge.on_claim_promoted("c1", ClaimStatus.PROPOSED, ClaimStatus.VERIFIED)
    bridge.on_fsm_transitioned("r", RunState.RECEIVED.value, RunState.CLASSIFYING.value)

    events = list(g.events)
    assert [e.type for e in events] == [
        EVENT_NODE_ADDED,
        EVENT_NODE_ADDED,
        EVENT_EDGE_ADDED,
        EVENT_CLAIM_PROMOTED,
        EVENT_FSM_TRANSITIONED,
    ]


# ── S02: replay contract (R5 / C9 / C13) ────────────────────────────────


def _replay_collected(events) -> TaskGraphState:
    state = TaskGraphState()
    for e in events:
        state = state.apply_event(e.type, e.payload)
    return state


def test_replay_roundtrip_graph_via_real_activegraph() -> None:
    """Out(graph ops) → graph → iter_events → apply_event → restored == original."""
    g = Graph()
    sink = ActivegraphEventSink(g)
    bridge = TaskGraphBridge(sink)

    # Build a real TaskGraph and emit each operation in order.
    ev = TaskNode(TaskNodeId("e"), NodeKind.EVIDENCE, "")
    goal = TaskNode(TaskNodeId("g"), NodeKind.GOAL, "answer")
    edge = TaskEdge(TaskNodeId("e"), TaskNodeId("g"), EdgeKind.SUPPORTS)
    graph = (
        TaskGraphState()
        .graph.add_node(ev)
        .add_node(goal)
        .add_edge(edge)
        .commit()
    )

    bridge.on_node_added(ev)
    bridge.on_node_added(goal)
    bridge.on_edge_added(edge)
    bridge.on_graph_committed(graph, prev_version=0)

    replayed = _replay_collected(g.events)
    assert replayed.graph.version == graph.version
    assert {str(n.id) for n in replayed.graph.nodes} == {str(n.id) for n in graph.nodes}
    assert {str(e.source) + "->" + str(e.target) for e in replayed.graph.edges} == {
        str(e.source) + "->" + str(e.target) for e in graph.edges
    }


def test_replay_roundtrip_claim_status_via_real_activegraph() -> None:
    g = Graph()
    sink = ActivegraphEventSink(g)
    bridge = TaskGraphBridge(sink)
    bridge.on_claim_promoted("c1", ClaimStatus.PROPOSED, ClaimStatus.VERIFIED)

    replayed = _replay_collected(g.events)
    assert replayed.claim_statuses == {"c1": ClaimStatus.VERIFIED}


def test_replay_roundtrip_fsm_state_via_real_activegraph() -> None:
    g = Graph()
    sink = ActivegraphEventSink(g)
    bridge = TaskGraphBridge(sink)
    bridge.on_fsm_transitioned("r", RunState.RECEIVED.value, RunState.CLASSIFYING.value)

    replayed = _replay_collected(g.events)
    assert replayed.run_fsm is not None
    assert replayed.run_fsm.state is RunState.CLASSIFYING
