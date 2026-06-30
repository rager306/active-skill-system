"""Tests for M054 S00 — Relation + RelationBehavior domain types."""

from __future__ import annotations

import pytest

from active_skill_system.domain.relation import (
    Relation,
    RelationBehavior,
    RelationCardinality,
)

# ── Relation ──────────────────────────────────────────────────────────────


def test_relation_creation_defaults() -> None:
    r = Relation(kind="supports", source_type="evidence", target_type="claim")
    assert r.kind == "supports"
    assert r.source_type == "evidence"
    assert r.target_type == "claim"
    assert r.cardinality == RelationCardinality.MANY_TO_MANY
    assert r.metadata == {}


def test_relation_creation_full() -> None:
    r = Relation(
        kind="depends_on", source_type="task", target_type="task",
        cardinality=RelationCardinality.ONE_TO_MANY,
        metadata={"weight": 0.9},
    )
    assert r.cardinality == RelationCardinality.ONE_TO_MANY
    assert r.metadata == {"weight": 0.9}


def test_relation_rejects_empty_kind() -> None:
    with pytest.raises(ValueError, match="kind must be non-empty"):
        Relation(kind="", source_type="a", target_type="b")


def test_relation_rejects_empty_source_type() -> None:
    with pytest.raises(ValueError, match="source_type must be non-empty"):
        Relation(kind="k", source_type="", target_type="b")


def test_relation_rejects_empty_target_type() -> None:
    with pytest.raises(ValueError, match="target_type must be non-empty"):
        Relation(kind="k", source_type="a", target_type="")


def test_relation_rejects_bad_cardinality() -> None:
    with pytest.raises(ValueError, match="cardinality must be one of"):
        Relation(kind="k", source_type="a", target_type="b", cardinality="invalid")


def test_relation_matches_edge_positive() -> None:
    r = Relation(kind="supports", source_type="evidence", target_type="claim")
    assert r.matches_edge("supports", "evidence", "claim") is True


def test_relation_matches_edge_wrong_kind() -> None:
    r = Relation(kind="supports", source_type="evidence", target_type="claim")
    assert r.matches_edge("contradicts", "evidence", "claim") is False


def test_relation_matches_edge_wrong_source_type() -> None:
    r = Relation(kind="supports", source_type="evidence", target_type="claim")
    assert r.matches_edge("supports", "memo", "claim") is False


def test_relation_matches_edge_wrong_target_type() -> None:
    r = Relation(kind="supports", source_type="evidence", target_type="claim")
    assert r.matches_edge("supports", "evidence", "memo") is False


def test_relation_cardinality_constants() -> None:
    assert RelationCardinality.ONE_TO_ONE == "1:1"
    assert RelationCardinality.ONE_TO_MANY == "1:N"
    assert RelationCardinality.MANY_TO_ONE == "N:1"
    assert RelationCardinality.MANY_TO_MANY == "N:N"


# ── RelationBehavior ──────────────────────────────────────────────────────


def test_relation_behavior_creation_defaults() -> None:
    rel = Relation(kind="supports", source_type="evidence", target_type="claim")
    rb = RelationBehavior(name="evidence_linker", relation=rel)
    assert rb.name == "evidence_linker"
    assert rb.activate_after == 0
    assert rb.description == ""


def test_relation_behavior_creation_full() -> None:
    rel = Relation(kind="contradicts", source_type="claim", target_type="claim")
    rb = RelationBehavior(
        name="contradiction_handler", relation=rel,
        description="Handles contradictions", activate_after=2,
    )
    assert rb.description == "Handles contradictions"
    assert rb.activate_after == 2


def test_relation_behavior_rejects_empty_name() -> None:
    rel = Relation(kind="k", source_type="a", target_type="b")
    with pytest.raises(ValueError, match="name must be non-empty"):
        RelationBehavior(name="", relation=rel)


def test_relation_behavior_rejects_non_relation() -> None:
    with pytest.raises(ValueError, match="relation must be a Relation"):
        RelationBehavior(name="b", relation="not-a-relation")  # type: ignore[arg-type]


def test_relation_behavior_rejects_negative_activate_after() -> None:
    rel = Relation(kind="k", source_type="a", target_type="b")
    with pytest.raises(ValueError, match="activate_after must be non-negative"):
        RelationBehavior(name="b", relation=rel, activate_after=-1)


def test_relation_behavior_matches_edge_delegates() -> None:
    rel = Relation(kind="supports", source_type="evidence", target_type="claim")
    rb = RelationBehavior(name="linker", relation=rel)
    assert rb.matches_edge("supports", "evidence", "claim") is True
    assert rb.matches_edge("contradicts", "evidence", "claim") is False
