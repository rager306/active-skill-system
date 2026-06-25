"""Tests for TransformationSelector (M020 S01)."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from active_skill_system.application.transformation_selector import (
    StageRequirements,
    TransformationSelector,
)
from active_skill_system.domain.compiler_types import CompilerNodeKind, TransformParams


def _tile(tile_size: int = 32) -> TransformParams:
    return TransformParams(transform_type=CompilerNodeKind.TRANSFORM_TILE, params={"tile_size": tile_size}, legal=True)


def _unroll(factor: int = 2) -> TransformParams:
    return TransformParams(transform_type=CompilerNodeKind.TRANSFORM_UNROLL, params={"unroll_factor": factor}, legal=True)


def _fusion(k: int = 2) -> TransformParams:
    return TransformParams(transform_type=CompilerNodeKind.TRANSFORM_FUSION, params={"fused_loops": k}, legal=True)


# ── StageRequirements validation ──────────────────────────────────────────


def test_stage_requirements_rejects_empty_stage_name() -> None:
    with pytest.raises(ValueError, match="stage_name"):
        StageRequirements(stage_name="", allowed_kinds=frozenset({CompilerNodeKind.TRANSFORM_TILE}))


def test_stage_requirements_rejects_non_frozenset_kinds() -> None:
    with pytest.raises(ValueError, match="allowed_kinds must be a frozenset"):
        StageRequirements(stage_name="optimize", allowed_kinds={CompilerNodeKind.TRANSFORM_TILE})  # type: ignore[arg-type]


def test_stage_requirements_rejects_invalid_kind() -> None:
    with pytest.raises(ValueError, match="CompilerNodeKind"):
        StageRequirements(stage_name="x", allowed_kinds=frozenset({"not_a_kind"}))  # type: ignore[arg-type]


def test_stage_requirements_rejects_zero_min_tile_size() -> None:
    with pytest.raises(ValueError, match="min_tile_size"):
        StageRequirements(stage_name="x", min_tile_size=0)


def test_stage_requirements_default_min_tile_size_is_1() -> None:
    s = StageRequirements(stage_name="x", allowed_kinds=frozenset({CompilerNodeKind.TRANSFORM_TILE}))
    assert s.min_tile_size == 1


# ── TransformationSelector filtering ─────────────────────────────────────


def test_selector_returns_empty_for_unknown_stage() -> None:
    sel = TransformationSelector()
    assert sel.select_for_stage("unknown", (_tile(), _unroll())) == ()


def test_selector_filters_by_allowed_kinds() -> None:
    sel = TransformationSelector()
    sel.register_stage(StageRequirements(
        stage_name="optimize",
        allowed_kinds=frozenset({CompilerNodeKind.TRANSFORM_TILE, CompilerNodeKind.TRANSFORM_UNROLL}),
    ))
    selected = sel.select_for_stage("optimize", (_tile(), _unroll(), _fusion()))
    assert len(selected) == 2
    kinds = {c.transform_type for c in selected}
    assert kinds == {CompilerNodeKind.TRANSFORM_TILE, CompilerNodeKind.TRANSFORM_UNROLL}


def test_selector_returns_empty_when_allowed_kinds_empty() -> None:
    sel = TransformationSelector()
    sel.register_stage(StageRequirements(stage_name="restrictive", allowed_kinds=frozenset()))
    assert sel.select_for_stage("restrictive", (_tile(), _unroll())) == ()


def test_selector_enforces_min_tile_size_on_tile_candidates() -> None:
    sel = TransformationSelector()
    sel.register_stage(StageRequirements(
        stage_name="optimize",
        allowed_kinds=frozenset({CompilerNodeKind.TRANSFORM_TILE}),
        min_tile_size=16,
    ))
    candidates = (_tile(tile_size=8), _tile(tile_size=16), _tile(tile_size=32))
    selected = sel.select_for_stage("optimize", candidates)
    assert len(selected) == 2
    tile_sizes = sorted(c.params["tile_size"] for c in selected)
    assert tile_sizes == [16, 32]


def test_selector_min_tile_size_does_not_filter_non_tile_kinds() -> None:
    """min_tile_size constraint applies only to TILE candidates."""
    sel = TransformationSelector()
    sel.register_stage(StageRequirements(
        stage_name="all",
        allowed_kinds=frozenset({CompilerNodeKind.TRANSFORM_TILE, CompilerNodeKind.TRANSFORM_UNROLL}),
        min_tile_size=64,  # high threshold — no TILE will pass
    ))
    candidates = (_tile(tile_size=8), _unroll(factor=2), _fusion(k=3))
    selected = sel.select_for_stage("all", candidates)
    # Only UNROLL survives (TILE filtered, FUSION not allowed).
    assert len(selected) == 1
    assert selected[0].transform_type is CompilerNodeKind.TRANSFORM_UNROLL


def test_selector_accepts_list_and_tuple_inputs() -> None:
    """select_for_stage accepts both tuple and list inputs."""
    sel = TransformationSelector()
    sel.register_stage(StageRequirements(
        stage_name="all",
        allowed_kinds=frozenset({CompilerNodeKind.TRANSFORM_TILE}),
    ))
    as_list = sel.select_for_stage("all", [_tile(tile_size=16)])
    as_tuple = sel.select_for_stage("all", (_tile(tile_size=16),))
    assert len(as_list) == 1
    assert len(as_tuple) == 1


def test_register_stage_overwrites_same_name() -> None:
    sel = TransformationSelector()
    sel.register_stage(StageRequirements(stage_name="x", allowed_kinds=frozenset({CompilerNodeKind.TRANSFORM_TILE})))
    sel.register_stage(StageRequirements(stage_name="x", allowed_kinds=frozenset({CompilerNodeKind.TRANSFORM_UNROLL})))
    stages = sel.stages()
    assert stages["x"].allowed_kinds == frozenset({CompilerNodeKind.TRANSFORM_UNROLL})


def test_register_stage_rejects_non_StageRequirements() -> None:
    sel = TransformationSelector()
    with pytest.raises(TypeError, match="StageRequirements"):
        sel.register_stage("not a stage")  # type: ignore[arg-type]


def test_stages_returns_snapshot() -> None:
    sel = TransformationSelector()
    sel.register_stage(StageRequirements(stage_name="a", allowed_kinds=frozenset({CompilerNodeKind.TRANSFORM_TILE})))
    snap = sel.stages()
    assert "a" in snap
    # Snapshot is independent — mutating it doesn't affect selector.
    snap["b"] = "garbage"  # type: ignore[assignment]
    assert "b" not in sel.stages()


# ── R002 (module infra-free) ──────────────────────────────────────────────


def test_module_infra_free() -> None:
    mod = importlib.import_module("active_skill_system.application.transformation_selector")
    src = Path(mod.__file__).read_text(encoding="utf-8")
    for forbidden in ("import activegraph", "from activegraph", "import anthropic", "import openai"):
        assert forbidden not in src, (
            f"transformation_selector.py must not contain '{forbidden}' (R002)"
        )
