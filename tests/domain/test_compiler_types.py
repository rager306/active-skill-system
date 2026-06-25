"""Unit tests for compiler domain types (M016 S01 + S02)."""

from __future__ import annotations

import pytest

from active_skill_system.domain.compiler_types import (
    CompilerActionType,
    CompilerEdgeKind,
    CompilerGapClass,
    CompilerMetrics,
    CompilerNodeKind,
    DependencyDistance,
    TransformParams,
)


def test_compiler_node_kind_all_seven() -> None:
    expected = {"loop_nest", "statement", "array_ref", "transform_tile",
                "transform_interchange", "transform_fusion", "transform_unroll"}
    assert {k.value for k in CompilerNodeKind} == expected


def test_compiler_edge_kind_all_five() -> None:
    expected = {"flow_dep", "anti_dep", "output_dep", "legal_transform", "enables"}
    assert {k.value for k in CompilerEdgeKind} == expected


def test_dependency_distance_constructs() -> None:
    d = DependencyDistance(source="i", target="j", dep_type=CompilerEdgeKind.FLOW_DEP, distance=(1, 0))
    assert d.source == "i"
    assert d.dep_type is CompilerEdgeKind.FLOW_DEP


def test_dependency_distance_loop_carried() -> None:
    d = DependencyDistance(source="i", target="i", dep_type=CompilerEdgeKind.FLOW_DEP, distance=(1,))
    assert d.is_loop_carried() is True


def test_dependency_distance_not_loop_carried() -> None:
    d = DependencyDistance(source="i", target="j", dep_type=CompilerEdgeKind.FLOW_DEP, distance=(0, 0))
    assert d.is_loop_carried() is False


def test_dependency_distance_rejects_empty_source() -> None:
    with pytest.raises(ValueError, match="source"):
        DependencyDistance(source="", target="j", dep_type=CompilerEdgeKind.FLOW_DEP, distance=(1,))


def test_dependency_distance_rejects_wrong_dep_type() -> None:
    with pytest.raises(ValueError, match="dep_type"):
        DependencyDistance(source="i", target="j", dep_type=CompilerEdgeKind.LEGAL_TRANSFORM, distance=(1,))


def test_dependency_distance_rejects_empty_distance() -> None:
    with pytest.raises(ValueError, match="distance"):
        DependencyDistance(source="i", target="j", dep_type=CompilerEdgeKind.FLOW_DEP, distance=())


def test_transform_params_constructs() -> None:
    t = TransformParams(transform_type=CompilerNodeKind.TRANSFORM_TILE, params={"tile_size": 32})
    assert t.transform_type is CompilerNodeKind.TRANSFORM_TILE
    assert t.params["tile_size"] == 32
    assert t.legal is True


def test_transform_params_interchange() -> None:
    t = TransformParams(transform_type=CompilerNodeKind.TRANSFORM_INTERCHANGE, params={"order": [1, 0]})
    assert t.transform_type is CompilerNodeKind.TRANSFORM_INTERCHANGE


def test_transform_params_rejects_non_transform_kind() -> None:
    with pytest.raises(ValueError, match="TRANSFORM"):
        TransformParams(transform_type=CompilerNodeKind.LOOP_NEST, params={})


def test_transform_params_illegal_marked() -> None:
    t = TransformParams(
        transform_type=CompilerNodeKind.TRANSFORM_FUSION,
        params={"loops": [0, 1]},
        legal=False,
    )
    assert t.legal is False


def test_module_infra_free() -> None:
    import importlib
    from pathlib import Path

    mod = importlib.import_module("active_skill_system.domain.compiler_types")
    src = Path(mod.__file__).read_text()
    for forbidden in ("import activegraph", "from activegraph", "import anthropic", "import openai"):
        assert forbidden not in src, f"compiler_types.py must not contain '{forbidden}' (R002)"


# ── CompilerMetrics (S02) ──────────────────────────────────────────────────


def test_compiler_metrics_constructs() -> None:
    m = CompilerMetrics(cycles=100, reg_pressure=16, spills=2, energy_proxy=1.5)
    assert m.cycles == 100
    assert m.reg_pressure == 16
    assert m.spills == 2
    assert m.energy_proxy == 1.5
    assert m.is_valid is True


def test_compiler_metrics_rejects_negative_cycles() -> None:
    with pytest.raises(ValueError, match="cycles"):
        CompilerMetrics(cycles=-1, reg_pressure=0, spills=0, energy_proxy=0.0)


def test_compiler_metrics_rejects_negative_reg_pressure() -> None:
    with pytest.raises(ValueError, match="reg_pressure"):
        CompilerMetrics(cycles=10, reg_pressure=-1, spills=0, energy_proxy=0.0)


def test_compiler_metrics_rejects_negative_spills() -> None:
    with pytest.raises(ValueError, match="spills"):
        CompilerMetrics(cycles=10, reg_pressure=0, spills=-1, energy_proxy=0.0)


def test_compiler_metrics_rejects_negative_energy() -> None:
    with pytest.raises(ValueError, match="energy_proxy"):
        CompilerMetrics(cycles=10, reg_pressure=0, spills=0, energy_proxy=-0.1)


def test_compiler_metrics_rejects_non_bool_is_valid() -> None:
    with pytest.raises(ValueError, match="is_valid"):
        CompilerMetrics(cycles=10, reg_pressure=0, spills=0, energy_proxy=0.0, is_valid="yes")  # type: ignore[arg-type]


def test_compiler_metrics_is_hashable() -> None:
    m = CompilerMetrics(cycles=10, reg_pressure=4, spills=0, energy_proxy=1.0)
    assert hash(m) == hash(m)
    # Frozen dataclass: must be usable as dict key
    assert {m: 1}[m] == 1


def test_compiler_metrics_better_than_lower_cycles() -> None:
    a = CompilerMetrics(cycles=50, reg_pressure=8, spills=0, energy_proxy=1.0)
    b = CompilerMetrics(cycles=100, reg_pressure=8, spills=0, energy_proxy=1.0)
    assert a.better_than(b) is True
    assert b.better_than(a) is False


def test_compiler_metrics_better_than_same_cycles_lower_spills() -> None:
    a = CompilerMetrics(cycles=100, reg_pressure=8, spills=0, energy_proxy=1.0)
    b = CompilerMetrics(cycles=100, reg_pressure=8, spills=2, energy_proxy=1.0)
    assert a.better_than(b) is True
    assert b.better_than(a) is False


def test_compiler_metrics_better_than_same_cycles_spills_lower_energy() -> None:
    a = CompilerMetrics(cycles=100, reg_pressure=8, spills=2, energy_proxy=1.0)
    b = CompilerMetrics(cycles=100, reg_pressure=8, spills=2, energy_proxy=2.0)
    assert a.better_than(b) is True


def test_compiler_metrics_invalid_never_better_than_valid() -> None:
    valid = CompilerMetrics(cycles=1000, reg_pressure=64, spills=50, energy_proxy=10.0)
    invalid = CompilerMetrics(cycles=10, reg_pressure=1, spills=0, energy_proxy=0.1, is_valid=False)
    assert invalid.better_than(valid) is False
    assert valid.better_than(invalid) is True


def test_compiler_metrics_equal_not_better() -> None:
    a = CompilerMetrics(cycles=100, reg_pressure=8, spills=2, energy_proxy=1.0)
    b = CompilerMetrics(cycles=100, reg_pressure=8, spills=2, energy_proxy=1.0)
    assert a.better_than(b) is False
    assert b.better_than(a) is False


# ── CompilerGapClass / CompilerActionType (S02) ───────────────────────────


def test_compiler_gap_class_all_five() -> None:
    expected = {"missing_transform", "transform_regression", "loop_carried_dep",
                "register_spill", "perf_regression"}
    assert {g.value for g in CompilerGapClass} == expected


def test_compiler_action_type_all_four() -> None:
    expected = {"apply_transform", "revert_transform", "pick_alternative", "lowering_replan"}
    assert {a.value for a in CompilerActionType} == expected


def test_compiler_gap_class_is_str_enum() -> None:
    assert isinstance(CompilerGapClass.MISSING_TRANSFORM, str)
    assert CompilerGapClass.LOOP_CARRIED_DEP == "loop_carried_dep"


def test_compiler_action_type_is_str_enum() -> None:
    assert isinstance(CompilerActionType.APPLY_TRANSFORM, str)
    assert CompilerActionType.LOWERING_REPLAN == "lowering_replan"
