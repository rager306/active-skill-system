"""Round-trip tests for TaskGraphBridge (M004 S02).

Drives the outbound projection (S01) → collects the events in a
``ListEventSink`` → replays them into a fresh ``TaskGraphState`` via
``apply_event`` → asserts the reconstructed state matches the original. This
is the load-bearing proof that R1 (Task Graph ↔ activegraph mapping) holds in
code: the serialization contract is closed under round-trip.
"""

from __future__ import annotations

from active_skill_system.adapters.taskgraph_bridge import (
    ListEventSink,
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


def _replay(events) -> TaskGraphState:
    """Apply each event in order; return the resulting state."""
    state = TaskGraphState()
    for e in events:
        state = state.apply_event(e.event_type, e.payload)
    return state


def test_roundtrip_empty_graph() -> None:
    """An empty graph survives a no-op replay (zero events)."""
    state = _replay([])  # zero events in, zero events out
    assert state.graph.version == 0
    assert state.claim_statuses == {}


def test_roundtrip_task_graph_node_edge_commit() -> None:
    """Build a real graph outbound, replay, compare version + structure."""
    sink = ListEventSink()
    bridge = TaskGraphBridge(sink)

    g0 = TaskGraphState().graph
    g1 = g0.add_node(TaskNode(TaskNodeId("g"), NodeKind.GOAL, "G"))
    g2 = g1.add_node(TaskNode(TaskNodeId("e"), NodeKind.EVIDENCE, ""))
    g3 = g2.add_edge(TaskEdge(TaskNodeId("e"), TaskNodeId("g"), EdgeKind.SUPPORTS))
    g4 = g3.commit()

    # Emit each node the moment it is added, in order, so replay sees them too.
    bridge.on_node_added(TaskNode(TaskNodeId("g"), NodeKind.GOAL, "G"))
    bridge.on_node_added(TaskNode(TaskNodeId("e"), NodeKind.EVIDENCE, ""))
    bridge.on_edge_added(TaskEdge(TaskNodeId("e"), TaskNodeId("g"), EdgeKind.SUPPORTS))
    bridge.on_graph_committed(g4, prev_version=g3.version)

    state = _replay(sink.events)
    assert state.graph.version == g4.version
    assert {str(n.id) for n in state.graph.nodes} == {str(n.id) for n in g4.nodes}
    assert {str(e.source) + "->" + str(e.target) for e in state.graph.edges} == {
        str(e.source) + "->" + str(e.target) for e in g4.edges
    }


def test_roundtrip_claim_promotion() -> None:
    """A claim promotion round-trips: outbound emits the new status; replay stores it."""
    sink = ListEventSink()
    bridge = TaskGraphBridge(sink)
    bridge.on_claim_promoted("c1", ClaimStatus.PROPOSED, ClaimStatus.VERIFIED)

    state = _replay(sink.events)
    assert state.claim_statuses == {"c1": ClaimStatus.VERIFIED}


def test_roundtrip_fsm_transition() -> None:
    """An FSM transition round-trips through a fresh state starting at RECEIVED."""
    sink = ListEventSink()
    bridge = TaskGraphBridge(sink)
    # Build the canonical sequence: received → classifying → modeling
    fsm0 = TaskGraphState().run_fsm or __import__(
        "active_skill_system.domain.runtime", fromlist=["RunFSM"]
    ).RunFSM()
    assert fsm0.state is RunState.RECEIVED
    fsm1 = fsm0.transition(RunState.CLASSIFYING)
    bridge.on_fsm_transitioned("run1", fsm0.state.value, fsm1.state.value)
    fsm2 = fsm1.transition(RunState.MODELING)
    bridge.on_fsm_transitioned("run1", fsm1.state.value, fsm2.state.value)

    state = _replay(sink.events)
    assert state.run_fsm is not None
    assert state.run_fsm.state is RunState.MODELING
    # History preserved through the run.
    assert state.run_fsm.history[-1] is RunState.MODELING


def test_roundtrip_unknown_event_is_forward_compat_noop() -> None:
    """An unknown event type must not crash replay (forward-compat)."""
    state = TaskGraphState()
    next_state = state.apply_event("task.future.unknown", {"any": "payload"})
    assert next_state is state  # identity preserved on no-op


def test_roundtrip_mixed_stream_reconstructs_whole_state() -> None:
    """A mixed stream of node + edge + claim + fsm events reconstructs all four pieces."""
    sink = ListEventSink()
    bridge = TaskGraphBridge(sink)

    # Build the graph the way a real driver would (target-узел первым, чтобы edges не висели).
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

    bridge.on_node_added(goal)
    bridge.on_node_added(ev)
    bridge.on_edge_added(edge)
    bridge.on_claim_promoted("c1", ClaimStatus.PROPOSED, ClaimStatus.GROUNDED)
    # The outbound receiver needs a legal transition sequence; replay the
    # same to compare apples-to-apples below.
    bridge.on_fsm_transitioned("r", RunState.RECEIVED.value, RunState.CLASSIFYING.value)
    bridge.on_fsm_transitioned("r", RunState.CLASSIFYING.value, RunState.MODELING.value)
    bridge.on_graph_committed(graph, prev_version=0)

    state = _replay(sink.events)
    assert state.graph.version == graph.version
    assert {"g", "e"} <= {str(n.id) for n in state.graph.nodes}
    assert state.claim_statuses.get("c1") == ClaimStatus.GROUNDED
    assert state.run_fsm is not None and state.run_fsm.state is RunState.MODELING
