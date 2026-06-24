"""Property-based tests for domain/runtime invariants (M010 S01).

Uses hypothesis to generate random valid inputs and verify invariants hold
across a wide input space — catching edge-cases hand-written tests miss.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from active_skill_system.domain.runtime import (
    Claim,
    ClaimStatus,
    EdgeKind,
    GraphPatch,
    NodeKind,
    PatchOp,
    RunFSM,
    RunState,
    TaskEdge,
    TaskGraph,
    TaskNode,
    TaskNodeId,
    is_measurable_improvement,
)

# ── Strategies ────────────────────────────────────────────────────────────


# Valid node-id strings (non-empty, no whitespace-only).
_node_id_str = st.text(min_size=1, max_size=20).filter(lambda s: s.strip())

# Non-empty text.
_text = st.text(min_size=1, max_size=50).filter(lambda s: s.strip())

# Kinds that require text (so TaskNode construction succeeds).
_factual_kinds = st.sampled_from(
    [NodeKind.GOAL, NodeKind.FACT, NodeKind.CONSTRAINT, NodeKind.CLAIM, NodeKind.MECHANISM]
)


def _task_nodes():
    return st.builds(
        TaskNode,
        id=st.builds(TaskNodeId, _node_id_str),
        kind=_factual_kinds,
        text=_text,
    )


def _task_edges(node_ids: list[str]):
    """Build edges between pairs of existing node ids (no self-loops)."""
    if len(node_ids) < 2:
        return st.none()
    pairs = [
        (a, b)
        for i, a in enumerate(node_ids)
        for j, b in enumerate(node_ids)
        if i != j
    ]
    return st.sampled_from(pairs).map(
        lambda pair: TaskEdge(
            source=TaskNodeId(pair[0]),
            target=TaskNodeId(pair[1]),
            kind=st.sampled_from(list(EdgeKind)).example(),
        )
    )


# ── TaskGraph properties ──────────────────────────────────────────────────


@given(node=_task_nodes())
@settings(max_examples=50)
def test_property_add_node_increments_version(node: TaskNode) -> None:
    """add_node always increments version and links parent."""
    g0 = TaskGraph()
    g1 = g0.add_node(node)
    assert g1.version == g0.version + 1
    assert g1.parent_version == g0.version


@given(node=_task_nodes())
@settings(max_examples=50)
def test_property_add_node_is_immutable(node: TaskNode) -> None:
    """add_node returns a NEW graph; original unchanged."""
    g0 = TaskGraph()
    g1 = g0.add_node(node)
    assert len(g0.nodes) == 0
    assert len(g1.nodes) == 1


@given(text=_text)
@settings(max_examples=30)
def test_property_claim_text_round_trips(text: str) -> None:
    """Claim stores its text faithfully."""
    c = Claim(id="c", text=text, status=ClaimStatus.PROPOSED)
    assert c.text == text


# ── GraphPatch properties ─────────────────────────────────────────────────


@given(text=_text)
@settings(max_examples=30)
def test_property_patch_add_node_produces_valid_graph(text: str) -> None:
    """GraphPatch with add_node always produces a graph with version > 0."""
    patch = GraphPatch(
        operations=(
            PatchOp(
                op_type="add_node",
                payload={"node_id": "p1", "kind": NodeKind.FACT.value, "text": text},
            ),
        )
    )
    g = patch.apply(TaskGraph())
    assert g.version >= 1
    assert len(g.nodes) >= 1


# ── FSM properties ────────────────────────────────────────────────────────


# All legal transitions from concept.md §4.3.
_LEGAL_TRANSITIONS = [
    (RunState.RECEIVED, RunState.CLASSIFYING),
    (RunState.CLASSIFYING, RunState.DIRECT_PATH),
    (RunState.CLASSIFYING, RunState.MODELING),
    (RunState.VALIDATING_MODEL, RunState.PLANNING),
    (RunState.PLANNING, RunState.EXECUTING),
    (RunState.SYNTHESIZING, RunState.VALIDATING_OUTPUT),
]


@given(src_dst=st.sampled_from(_LEGAL_TRANSITIONS))
def test_property_legal_fsm_transitions_succeed(src_dst) -> None:  # noqa: ANN001
    """Every legal transition succeeds and grows history."""
    src, dst = src_dst
    # Build FSM at the source state with a RECEIVED-prefixed history.
    fsm = RunFSM(state=src, history=(RunState.RECEIVED, src))
    advanced = fsm.transition(dst)
    assert advanced.state == dst
    assert len(advanced.history) == len(fsm.history) + 1


# Illegal transition pairs (skip-paths).
_ILLEGAL_TRANSITIONS = [
    (RunState.RECEIVED, RunState.PLANNING),
    (RunState.RECEIVED, RunState.COMPLETED),
    (RunState.COMPLETED, RunState.PLANNING),
    (RunState.EXECUTING, RunState.COMPLETED),
    (RunState.RECEIVED, RunState.SYNTHESIZING),
]


@given(src_dst=st.sampled_from(_ILLEGAL_TRANSITIONS))
def test_property_illegal_fsm_transitions_raise(src_dst) -> None:  # noqa: ANN001
    """Every illegal transition raises ValueError."""
    src, dst = src_dst
    fsm = RunFSM(state=src, history=(RunState.RECEIVED, src))
    try:
        fsm.transition(dst)
        raise AssertionError(f"illegal transition {src}→{dst} should have raised")
    except ValueError:
        pass  # Expected.


# ── Claim anti-fancy property ────────────────────────────────────────────


@given(text=_text)
@settings(max_examples=30)
def test_property_ungrounded_claim_cannot_verify(text: str) -> None:
    """A claim with no evidence and no grounding kind can NEVER be VERIFIED."""
    c = Claim(id="c", text=text, status=ClaimStatus.PROPOSED)
    try:
        c.with_status(ClaimStatus.VERIFIED)
        raise AssertionError("ungrounded claim should not be verifiable")
    except ValueError:
        pass  # Expected — anti-fancy invariant holds.


# ── MeasurableImprovement property ──────────────────────────────────────


@given(
    gaps_b=st.integers(min_value=0, max_value=20),
    gaps_a=st.integers(min_value=0, max_value=20),
    constr_b=st.integers(min_value=0, max_value=10),
    constr_a=st.integers(min_value=0, max_value=10),
    ver_b=st.integers(min_value=0, max_value=10),
    ver_a=st.integers(min_value=0, max_value=10),
)
@settings(max_examples=100)
def test_property_improvement_never_accepts_constraint_regression(
    gaps_b: int, gaps_a: int, constr_b: int, constr_a: int, ver_b: int, ver_a: int
) -> None:
    """If constraints worsen, the gate NEVER accepts — regardless of gaps/verified."""
    result = is_measurable_improvement(
        gaps_before=gaps_b,
        gaps_after=gaps_a,
        constraints_before=constr_b,
        constraints_after=constr_a,
        verified_before=ver_b,
        verified_after=ver_a,
    )
    if constr_a > constr_b:
        assert result is False
