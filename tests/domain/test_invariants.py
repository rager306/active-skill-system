"""Offline unit tests for the L1 Domain entities and their invariants.

These tests verify that the four domain entities (Genome, Expression,
Evolution, GovernancePolicy) and the Mutation value object:

  1) Construct successfully with valid arguments.
  2) Reject invalid arguments by raising ValueError on invariant
     violation (every invariant gets at least one negative test).
  3) Are frozen (immutable, hashable).
  4) Stay infra-free (R002) - the L1 domain module source must not
     import activegraph / anthropic / openai.

All tests are offline, deterministic, and require no runtime startup.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from active_skill_system.domain import (
    Evolution,
    EvolutionId,
    Expression,
    ExpressionId,
    Genome,
    GenomeId,
    GovernancePolicy,
    Mutation,
)

# ── Genome ────────────────────────────────────────────────────────────────


def test_genome_constructs_with_valid_args() -> None:
    g = Genome(
        id=GenomeId("g1"),
        name="reasoning",
        signature="def reason(p): return p > 0.5",
        capabilities=frozenset({"logic", "search"}),
        invariants=(),
    )
    assert g.id.value == "g1"
    assert g.name == "reasoning"
    assert "logic" in g.capabilities
    assert hash(g) == hash(g)  # frozen => hashable


def test_genome_invariant_empty_name_raises() -> None:
    with pytest.raises(ValueError, match="name"):
        Genome(
            id=GenomeId("g2"),
            name="",
            signature="x",
            capabilities=frozenset({"a"}),
        )


def test_genome_invariant_empty_capabilities_raises() -> None:
    with pytest.raises(ValueError, match="capabilities"):
        Genome(
            id=GenomeId("g3"),
            name="x",
            signature="x",
            capabilities=frozenset(),
        )


# ── Expression ───────────────────────────────────────────────────────────


def test_expression_constructs_with_valid_args() -> None:
    e = Expression(
        id=ExpressionId("e1"),
        genome_id=GenomeId("g1"),
        args=(1, 2, 3),
        produced_at=datetime.now(UTC),
        evidence_ids=(),
        status="ok",
    )
    assert e.status == "ok"
    assert e.genome_id.value == "g1"
    assert e.args == (1, 2, 3)
    assert hash(e) == hash(e)  # frozen => hashable


def test_expression_invariant_duplicate_evidence_raises() -> None:
    with pytest.raises(ValueError, match="evidence_ids must be unique"):
        Expression(
            id=ExpressionId("e2"),
            genome_id=GenomeId("g1"),
            evidence_ids=(ExpressionId("dup"), ExpressionId("dup")),
        )


def test_expression_invariant_invalid_status_raises() -> None:
    with pytest.raises(ValueError, match="status"):
        Expression(
            id=ExpressionId("e3"),
            genome_id=GenomeId("g1"),
            status="bogus",  # type: ignore[arg-type]
        )


# ── Evolution + Mutation ─────────────────────────────────────────────────


def test_evolution_constructs_with_valid_args() -> None:
    e = Evolution(
        parent_ids=(GenomeId("g1"),),
        child_id=EvolutionId("ev1"),
        mutation=Mutation(op="add", target="capabilities", value="q"),
        fitness=0.8,
    )
    assert e.fitness == 0.8
    assert e.mutation.op == "add"


def test_evolution_invariant_fitness_out_of_range_raises() -> None:
    with pytest.raises(ValueError, match="fitness must be in"):
        Evolution(
            parent_ids=(GenomeId("g1"),),
            child_id=EvolutionId("ev1"),
            mutation=Mutation(op="add", target="x", value="y"),
            fitness=1.5,
        )


def test_evolution_invariant_child_in_parents_raises() -> None:
    parent = EvolutionId("ev-parent")
    with pytest.raises(ValueError, match="must not appear in parent_ids"):
        Evolution(
            parent_ids=(parent,),
            child_id=parent,  # collision
            mutation=Mutation(op="add", target="x", value="y"),
            fitness=0.5,
        )


# ── GovernancePolicy ────────────────────────────────────────────────────


def test_governance_default_policy_constructs() -> None:
    p = GovernancePolicy.default_policy()
    assert p.max_evolution_depth >= 1
    assert 0.0 <= p.review_threshold <= 1.0
    assert p.frozen is False


def test_governance_invariant_negative_depth_raises() -> None:
    with pytest.raises(ValueError, match="max_evolution_depth"):
        GovernancePolicy(max_evolution_depth=0, review_threshold=0.5)


def test_governance_invariant_threshold_out_of_range_raises() -> None:
    with pytest.raises(ValueError, match="review_threshold must be in"):
        GovernancePolicy(max_evolution_depth=3, review_threshold=1.5)


# ── bonus: R002 enforcement (L1 domain source-text check) ──────────────


def test_domain_layer_is_infra_free() -> None:
    """Source-text check: no domain/*.py file imports infrastructure packages.

    R002 says domain + application are infra-free. This test enforces the
    constraint at the L1 layer by inspecting source for forbidden imports.
    If a future change adds `import activegraph` to a domain module, this
    test fails immediately.
    """
    domain_dir = (
        Path(__file__).resolve().parent.parent.parent / "src" / "active_skill_system" / "domain"
    )
    assert domain_dir.is_dir(), f"domain dir not found: {domain_dir}"
    forbidden = ("import activegraph", "from activegraph", "import anthropic", "import openai")
    for py in sorted(domain_dir.glob("*.py")):
        src = py.read_text()
        for marker in forbidden:
            assert marker not in src, (
                f"domain/{py.name} contains '{marker}' (R002 violated - L1 must be infra-free)"
            )
