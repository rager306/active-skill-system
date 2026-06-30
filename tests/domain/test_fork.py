"""Tests for M052 S08 — Fork + Diff domain types."""

from __future__ import annotations

import pytest

from active_skill_system.domain.fork import (
    Diff,
    DivergentObject,
    DivergentRelation,
    Fork,
)


def test_fork_post_init_rejects_empty_parent() -> None:
    with pytest.raises(ValueError, match="parent_run_id must be non-empty"):
        Fork(parent_run_id="", fork_run_id="f", at_event_id="e")


def test_fork_post_init_rejects_empty_fork() -> None:
    with pytest.raises(ValueError, match="fork_run_id must be non-empty"):
        Fork(parent_run_id="p", fork_run_id="", at_event_id="e")


def test_fork_post_init_rejects_empty_event() -> None:
    with pytest.raises(ValueError, match="at_event_id must be non-empty"):
        Fork(parent_run_id="p", fork_run_id="f", at_event_id="")


def test_fork_accepts_empty_overrides() -> None:
    f = Fork(parent_run_id="p", fork_run_id="f", at_event_id="e")
    assert f.config_overrides == {}


def test_fork_accepts_overrides() -> None:
    f = Fork(parent_run_id="p", fork_run_id="f", at_event_id="e", config_overrides={"model": "glm"})
    assert f.config_overrides == {"model": "glm"}


def test_divergent_object_rejects_bad_change_type() -> None:
    with pytest.raises(ValueError, match="change_type must be"):
        DivergentObject(vertex_id="v", change_type="invalid")


def test_divergent_object_summary() -> None:
    obj = DivergentObject(vertex_id="loop:abc", change_type="added")
    assert obj.summary() == "loop:abc: added"


def test_divergent_relation_rejects_bad_change_type() -> None:
    with pytest.raises(ValueError, match="change_type must be"):
        DivergentRelation(edge_key="uses|a|b", change_type="invalid")


def test_divergent_relation_summary() -> None:
    rel = DivergentRelation(edge_key="uses|a|b", change_type="removed")
    assert rel.summary() == "uses|a|b: removed"


def test_diff_is_identical_when_empty() -> None:
    d = Diff(parent_run_id="p", fork_run_id="f")
    assert d.is_identical is True


def test_diff_not_identical_when_objects_differ() -> None:
    d = Diff(
        parent_run_id="p",
        fork_run_id="f",
        divergent_objects=(DivergentObject(vertex_id="v", change_type="added"),),
    )
    assert d.is_identical is False


def test_diff_summary() -> None:
    d = Diff(
        parent_run_id="p",
        fork_run_id="f",
        divergent_objects=(DivergentObject(vertex_id="v1", change_type="added"),),
        divergent_relations=(DivergentRelation(edge_key="uses|a|b", change_type="removed"),),
        split_event_id="evt-017",
    )
    s = d.summary()
    assert "p vs f" in s
    assert "evt-017" in s
    assert "divergent objects: 1" in s
    assert "v1: added" in s
    assert "uses|a|b: removed" in s


def test_diff_summary_truncates_large_diffs() -> None:
    objs = tuple(DivergentObject(vertex_id=f"v{i}", change_type="changed") for i in range(15))
    d = Diff(parent_run_id="p", fork_run_id="f", divergent_objects=objs)
    s = d.summary()
    assert "and" in s  # truncation indicator
