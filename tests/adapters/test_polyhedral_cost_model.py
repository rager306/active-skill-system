"""Tests for PolyhedralCostModel (M019 S02)."""

from __future__ import annotations

import json
from pathlib import Path

from active_skill_system.adapters.polyhedral_cost_model import PolyhedralCostModel
from active_skill_system.application.ports.tool import ToolCapability
from active_skill_system.domain.compiler_types import CompilerMetrics


def _baseline_dict(cycles: int = 1000, cache_misses: int = 100, vectorization_factor: float = 0.0) -> dict:
    return {
        "cycles": cycles, "reg_pressure": 10, "spills": 2, "energy_proxy": 1.0,
        "is_valid": True, "cache_misses": cache_misses, "vectorization_factor": vectorization_factor,
    }


# ── Tool surface ──────────────────────────────────────────────────────────


def test_tool_name_and_capabilities() -> None:
    tool = PolyhedralCostModel()
    assert tool.name == "compiler_apply_transform"
    assert ToolCapability.COMPUTE in tool.capabilities


# ── Transform formulas ────────────────────────────────────────────────────


def test_tile_reduces_cycles_drops_cache_misses_increases_vec() -> None:
    """TILE(10) on baseline cycles=1000, cache_misses=100, vec=0.0:
    cycles //= 10 = 100; cache_misses -= 50 = 50; vec += 0.2 = 0.2.
    """
    tool = PolyhedralCostModel()
    result = tool.invoke({
        "transform_type": "transform_tile",
        "params": {"tile_size": 10},
        "baseline": _baseline_dict(cycles=1000, cache_misses=100, vectorization_factor=0.0),
    })
    assert result.success is True
    parsed = json.loads(result.text)
    assert parsed["cycles"] == 100
    assert parsed["cache_misses"] == 50  # 100 - 5*10
    assert abs(parsed["vectorization_factor"] - 0.2) < 1e-9


def test_tile_caps_vectorization_at_1() -> None:
    """TILE with vec=0.9 -> +0.2 = 1.1 -> clamped to 1.0."""
    tool = PolyhedralCostModel()
    result = tool.invoke({
        "transform_type": "transform_tile",
        "params": {"tile_size": 10},
        "baseline": _baseline_dict(cycles=1000, cache_misses=100, vectorization_factor=0.9),
    })
    parsed = json.loads(result.text)
    assert parsed["vectorization_factor"] == 1.0


def test_tile_clamps_cache_misses_at_zero() -> None:
    """Tile cache_misses drop = 5*N. With N=10 and baseline=30, result = -20 -> clamped to 0."""
    tool = PolyhedralCostModel()
    result = tool.invoke({
        "transform_type": "transform_tile",
        "params": {"tile_size": 10},
        "baseline": _baseline_dict(cycles=1000, cache_misses=30, vectorization_factor=0.0),
    })
    parsed = json.loads(result.text)
    assert parsed["cache_misses"] == 0


def test_interchange_divides_cache_misses() -> None:
    """INTERCHANGE: cache_misses //= 2 = 50; cycles unchanged."""
    tool = PolyhedralCostModel()
    result = tool.invoke({
        "transform_type": "transform_interchange",
        "params": {},
        "baseline": _baseline_dict(cycles=1000, cache_misses=100, vectorization_factor=0.0),
    })
    parsed = json.loads(result.text)
    assert parsed["cycles"] == 1000
    assert parsed["cache_misses"] == 50


def test_fusion_reduces_cycles_more_conservatively_than_pedagogical() -> None:
    """FUSION(K=2) on cycles=1000: round(1000 * 0.6**2) = round(360) = 360.
    Pedagogical (CompilerToolStub) uses 0.7 -> 490. Polyhedral is more conservative.
    """
    tool = PolyhedralCostModel()
    result = tool.invoke({
        "transform_type": "transform_fusion",
        "params": {"fused_loops": 2},
        "baseline": _baseline_dict(cycles=1000, cache_misses=100, vectorization_factor=1.0),
    })
    parsed = json.loads(result.text)
    assert parsed["cycles"] == 360
    # Vectorization_factor *= 0.7 (fusion inhibits vec).
    assert abs(parsed["vectorization_factor"] - 0.7) < 1e-9


def test_unroll_reduces_cycles_and_boosts_vec() -> None:
    """UNROLL(F=4) on cycles=1000: 1000 // 4 = 250; vec += 0.3."""
    tool = PolyhedralCostModel()
    result = tool.invoke({
        "transform_type": "transform_unroll",
        "params": {"unroll_factor": 4},
        "baseline": _baseline_dict(cycles=1000, cache_misses=100, vectorization_factor=0.0),
    })
    parsed = json.loads(result.text)
    assert parsed["cycles"] == 250
    assert abs(parsed["vectorization_factor"] - 0.3) < 1e-9


def test_unroll_caps_vectorization_at_1() -> None:
    """UNROLL with vec=0.9 -> +0.3 = 1.2 -> clamped to 1.0."""
    tool = PolyhedralCostModel()
    result = tool.invoke({
        "transform_type": "transform_unroll",
        "params": {"unroll_factor": 4},
        "baseline": _baseline_dict(cycles=1000, cache_misses=100, vectorization_factor=0.9),
    })
    parsed = json.loads(result.text)
    assert parsed["vectorization_factor"] == 1.0


# ── Failure modes (D007) ──────────────────────────────────────────────────


def test_missing_transform_type_returns_baseline() -> None:
    tool = PolyhedralCostModel()
    result = tool.invoke({"baseline": _baseline_dict()})
    assert result.success is True
    assert result.evidence_id == "missing_transform"
    parsed = json.loads(result.text)
    assert parsed["cycles"] == 1000


def test_unknown_kind_returns_failure() -> None:
    tool = PolyhedralCostModel()
    result = tool.invoke({
        "transform_type": "transform_bogus",
        "params": {},
        "baseline": _baseline_dict(),
    })
    assert result.success is False


def test_illegal_transform_returns_failure() -> None:
    tool = PolyhedralCostModel()
    result = tool.invoke({
        "transform_type": "transform_tile",
        "params": {"tile_size": 10, "legal": False},
        "baseline": _baseline_dict(),
    })
    assert result.success is False


def test_invalid_param_returns_failure() -> None:
    tool = PolyhedralCostModel()
    result = tool.invoke({
        "transform_type": "transform_tile",
        "params": {"tile_size": 0},
        "baseline": _baseline_dict(),
    })
    assert result.success is False


# ── R002 / module hygiene ────────────────────────────────────────────────


def test_module_infra_free() -> None:
    from active_skill_system.adapters import polyhedral_cost_model
    src = Path(polyhedral_cost_model.__file__).read_text(encoding="utf-8")
    assert "activegraph" not in src
    assert "anthropic" not in src
    assert "openai" not in src


# ── Integration with CompilerMetrics (M019 S01 extension) ────────────────


def test_roundtrip_with_compiler_metrics_invariants() -> None:
    """PolyhedralCostModel output must satisfy CompilerMetrics invariants (R002 contract)."""
    tool = PolyhedralCostModel()
    for kind, params, baseline in [
        ("transform_tile", {"tile_size": 8}, _baseline_dict(cache_misses=50, vectorization_factor=0.5)),
        ("transform_interchange", {}, _baseline_dict(cache_misses=200, vectorization_factor=0.7)),
        ("transform_fusion", {"fused_loops": 1}, _baseline_dict(cache_misses=30, vectorization_factor=0.3)),
        ("transform_unroll", {"unroll_factor": 2}, _baseline_dict(cache_misses=80, vectorization_factor=0.4)),
    ]:
        result = tool.invoke({"transform_type": kind, "params": params, "baseline": baseline})
        assert result.success is True
        parsed = json.loads(result.text)
        # Roundtrip through CompilerMetrics to verify invariants.
        m = CompilerMetrics(
            cycles=parsed["cycles"], reg_pressure=parsed["reg_pressure"],
            spills=parsed["spills"], energy_proxy=parsed["energy_proxy"],
            is_valid=parsed["is_valid"], cache_misses=parsed["cache_misses"],
            vectorization_factor=parsed["vectorization_factor"],
        )
        assert m.cache_misses >= 0
        assert 0.0 <= m.vectorization_factor <= 1.0
