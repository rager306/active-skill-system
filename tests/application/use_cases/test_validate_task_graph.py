"""Unit tests for ValidateTaskGraphUseCase (Cognitive Runtime validators).

Pure, deterministic tests on real TaskGraph instances (no I/O). Cover:
  - empty graph: not reachable.
  - goal with direct evidence support: reachable.
  - transitive support (evidence -> claim -> goal): reachable + claim grounded.
  - unsupported goal: gap reported, not reachable.
  - ungrounded factual claim: anti-fantasy violation.
  - contradiction edge: constraint violation.
  - hypothesis is NOT an ungrounded factual claim (it is a formulation).
"""

from __future__ import annotations

from active_skill_system.application.use_cases.validate_task_graph import (
    ValidateTaskGraphUseCase,
)
from active_skill_system.domain.runtime import (
    EdgeKind,
    NodeKind,
    TaskEdge,
    TaskGraph,
    TaskNode,
    TaskNodeId,
)


def _goal(nid: str, text: str = "G") -> TaskNode:
    return TaskNode(id=TaskNodeId(nid), kind=NodeKind.GOAL, text=text)


def _evidence(nid: str) -> TaskNode:
    return TaskNode(id=TaskNodeId(nid), kind=NodeKind.EVIDENCE, text="")


def _claim(nid: str, text: str = "X") -> TaskNode:
    return TaskNode(id=TaskNodeId(nid), kind=NodeKind.CLAIM, text=text)


def _hypothesis(nid: str, text: str = "maybe") -> TaskNode:
    return TaskNode(id=TaskNodeId(nid), kind=NodeKind.HYPOTHESIS, text=text)


def _support(src: str, target: str) -> TaskEdge:
    return TaskEdge(source=TaskNodeId(src), target=TaskNodeId(target), kind=EdgeKind.SUPPORTS)


def test_empty_graph_not_reachable() -> None:
    r = ValidateTaskGraphUseCase().validate(TaskGraph())
    assert r.reachable is False
    assert r.goal_count == 0
    assert r.gaps == ()


def test_goal_with_direct_evidence_is_reachable() -> None:
    g = (
        TaskGraph()
        .add_node(_goal("g1"))
        .add_node(_evidence("e1"))
        .add_edge(_support("e1", "g1"))
    )
    r = ValidateTaskGraphUseCase().validate(g)
    assert r.reachable is True
    assert r.supported_goal_ids == ("g1",)
    assert r.gaps == ()


def test_transitive_support_evidence_claim_goal() -> None:
    g = (
        TaskGraph()
        .add_node(_goal("g"))
        .add_node(_claim("c"))
        .add_node(_evidence("e"))
        .add_edge(TaskEdge(TaskNodeId("e"), TaskNodeId("c"), EdgeKind.DERIVED_FROM))
        .add_edge(_support("c", "g"))
    )
    r = ValidateTaskGraphUseCase().validate(g)
    assert r.reachable is True
    assert r.ungrounded_factual_claims == ()  # claim is grounded via evidence


def test_unsupported_goal_is_a_gap() -> None:
    g = TaskGraph().add_node(_goal("g1"))
    r = ValidateTaskGraphUseCase().validate(g)
    assert r.reachable is False
    assert r.supported_goal_ids == ()
    assert any(gap.node_id == "g1" for gap in r.gaps)


def test_ungrounded_claim_is_anti_fantasy_violation() -> None:
    g = TaskGraph().add_node(_claim("c1", "X is true"))
    r = ValidateTaskGraphUseCase().validate(g)
    assert "c1" in r.ungrounded_factual_claims


def test_hypothesis_is_not_an_ungrounded_factual_claim() -> None:
    # A hypothesis is a formulation (concept.md §9 rule 4/5), not a factual
    # assertion: it may exist without grounding and is NOT a violation.
    g = TaskGraph().add_node(_hypothesis("h1", "perhaps Y"))
    r = ValidateTaskGraphUseCase().validate(g)
    assert r.ungrounded_factual_claims == ()


def test_contradiction_is_a_constraint_violation() -> None:
    g = (
        TaskGraph()
        .add_node(TaskNode(TaskNodeId("a"), NodeKind.FACT, "A"))
        .add_node(TaskNode(TaskNodeId("b"), NodeKind.FACT, "B"))
        .add_edge(TaskEdge(TaskNodeId("a"), TaskNodeId("b"), EdgeKind.CONTRADICTS))
    )
    r = ValidateTaskGraphUseCase().validate(g)
    assert "a->b" in r.constraint_violations


def test_claim_supported_only_by_another_ungrounded_claim_still_ungrounded() -> None:
    # c1 supports c2, but neither has evidence: both ungrounded (no fact path).
    g = (
        TaskGraph()
        .add_node(_claim("c1"))
        .add_node(_claim("c2"))
        .add_edge(_support("c1", "c2"))
    )
    r = ValidateTaskGraphUseCase().validate(g)
    assert set(r.ungrounded_factual_claims) == {"c1", "c2"}


def test_use_case_is_infra_free() -> None:
    """The use-case module must not import infrastructure (R002/R004)."""
    import importlib
    from pathlib import Path

    mod = importlib.import_module("active_skill_system.application.use_cases.validate_task_graph")
    assert mod.__file__ is not None
    src = Path(mod.__file__).read_text()
    for forbidden in ("import activegraph", "from activegraph", "import anthropic", "import openai"):
        assert forbidden not in src, f"validate_task_graph.py must not contain '{forbidden}' (R002)"
