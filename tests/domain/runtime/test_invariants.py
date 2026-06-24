"""Unit tests for domain/runtime invariants (Cognitive Runtime bounded context).

Verifies the four modules' invariants:
  nodes.py   - TaskNode construction + text-required-for-factual rejection.
  edges.py   - self-loop rejection + type checks.
  claim.py   - anti-fantasy: ungrounded VERIFIED rejected (construction AND
               with_status); grounded promotion allowed.
  graph.py   - versioning (monotone + parent linkage), dangling-edge rejection,
               immutability of add_node/add_edge/commit.

All offline, deterministic, no runtime.
"""

from __future__ import annotations

import pytest

from active_skill_system.domain.runtime import (
    Claim,
    ClaimStatus,
    EdgeKind,
    GroundingKind,
    NodeKind,
    TaskEdge,
    TaskGraph,
    TaskNode,
    TaskNodeId,
)

# ── nodes ─────────────────────────────────────────────────────────────────


def test_node_constructs() -> None:
    n = TaskNode(id=TaskNodeId("g1"), kind=NodeKind.GOAL, text="answer X")
    assert n.kind is NodeKind.GOAL
    assert hash(n) == hash(n)  # frozen => hashable


def test_node_factual_kind_requires_text() -> None:
    with pytest.raises(ValueError, match="requires non-empty text"):
        TaskNode(id=TaskNodeId("g2"), kind=NodeKind.FACT, text="")


def test_node_gap_allows_empty_text() -> None:
    n = TaskNode(id=TaskNodeId("gap1"), kind=NodeKind.GAP, text="")
    assert n.kind is NodeKind.GAP


def test_node_id_must_be_tasknodeid() -> None:
    with pytest.raises(ValueError, match="TaskNodeId"):
        TaskNode(id="plain-string", kind=NodeKind.GOAL, text="x")  # type: ignore[arg-type]


# ── edges ─────────────────────────────────────────────────────────────────


def test_edge_constructs() -> None:
    e = TaskEdge(source=TaskNodeId("a"), target=TaskNodeId("b"), kind=EdgeKind.SUPPORTS)
    assert e.kind is EdgeKind.SUPPORTS


def test_edge_self_loop_forbidden() -> None:
    same = TaskNodeId("a")
    with pytest.raises(ValueError, match="self-loop"):
        TaskEdge(source=same, target=same, kind=EdgeKind.SUPPORTS)


# ── claim: anti-fantasy invariant (load-bearing) ──────────────────────────


def test_claim_default_is_proposed_ungrounded() -> None:
    c = Claim(id="c1", text="X is true")
    assert c.status is ClaimStatus.PROPOSED
    assert c.grounded is False


def test_claim_verified_without_grounding_rejected_at_construction() -> None:
    with pytest.raises(ValueError, match="anti-fantasy"):
        Claim(id="c2", text="X", status=ClaimStatus.VERIFIED)


def test_claim_with_status_verified_without_grounding_rejected() -> None:
    c = Claim(id="c3", text="X", status=ClaimStatus.PROPOSED)
    with pytest.raises(ValueError, match="anti-fantasy"):
        c.with_status(ClaimStatus.VERIFIED)
    # the original is untouched (immutability)
    assert c.status is ClaimStatus.PROPOSED


def test_claim_promote_to_verified_with_evidence_allowed() -> None:
    c = Claim(id="c4", text="X", status=ClaimStatus.PROPOSED, evidence_ids=("e1",))
    verified = c.with_status(ClaimStatus.VERIFIED)
    assert verified.status is ClaimStatus.VERIFIED
    assert verified.grounded is True


def test_claim_promote_to_verified_with_deterministic_grounding_allowed() -> None:
    c = Claim(
        id="c5",
        text="sum is 4",
        status=ClaimStatus.PROPOSED,
        grounding_kind=GroundingKind.DETERMINISTIC_COMPUTATION,
    )
    verified = c.with_status(ClaimStatus.VERIFIED)
    assert verified.status is ClaimStatus.VERIFIED
    assert verified.grounded is True


# ── graph: versioning + immutability ──────────────────────────────────────


def _goal(text: str = "goal", nid: str = "g") -> TaskNode:
    return TaskNode(id=TaskNodeId(nid), kind=NodeKind.GOAL, text=text)


def test_graph_starts_at_version_zero_no_parent() -> None:
    g = TaskGraph()
    assert g.version == 0
    assert g.parent_version is None


def test_graph_add_node_increments_version_and_links_parent() -> None:
    g0 = TaskGraph()
    g1 = g0.add_node(_goal())
    assert g1.version == 1
    assert g1.parent_version == 0
    assert len(g1.nodes) == 1
    # original is immutable
    assert g0.version == 0 and len(g0.nodes) == 0


def test_graph_add_edge_between_existing_nodes() -> None:
    g = TaskGraph().add_node(_goal(nid="a")).add_node(_goal(text="evidence", nid="b"))
    g2 = g.add_edge(TaskEdge(source=TaskNodeId("a"), target=TaskNodeId("b"), kind=EdgeKind.REQUIRES))
    assert len(g2.edges) == 1
    assert g2.version == g.version + 1


def test_graph_dangling_edge_rejected() -> None:
    g = TaskGraph().add_node(_goal(nid="a"))
    with pytest.raises(ValueError, match="unknown nodes"):
        TaskGraph(
            nodes=g.nodes,
            edges=frozenset({TaskEdge(source=TaskNodeId("a"), target=TaskNodeId("missing"), kind=EdgeKind.SUPPORTS)}),
            version=1,
            parent_version=0,
        )


def test_graph_commit_snapshots_new_version() -> None:
    g = TaskGraph().add_node(_goal())
    snap = g.commit()
    assert snap.version == g.version + 1
    assert snap.parent_version == g.version
    assert snap.nodes == g.nodes  # structure unchanged


# ── R002: domain/runtime is infra-free ────────────────────────────────────


def test_runtime_domain_is_infra_free() -> None:
    """Source-text check: no domain/runtime/*.py imports infrastructure (R002)."""
    from pathlib import Path

    runtime_dir = (
        Path(__file__).resolve().parent.parent.parent.parent
        / "src"
        / "active_skill_system"
        / "domain"
        / "runtime"
    )
    assert runtime_dir.is_dir(), f"runtime dir not found: {runtime_dir}"
    forbidden = ("import activegraph", "from activegraph", "import anthropic", "import openai")
    for py in sorted(runtime_dir.glob("*.py")):
        src = py.read_text()
        for marker in forbidden:
            assert marker not in src, (
                f"domain/runtime/{py.name} contains '{marker}' (R002 violated)"
            )
