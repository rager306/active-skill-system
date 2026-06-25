"""Unit tests for CompilerToolStub (M016 S02 T03)."""

from __future__ import annotations

import json

import pytest

from active_skill_system.adapters.compiler_tool_stub import (
    CompilerToolStub,
    _apply_transform,
    _metrics_from_dict,
    _metrics_to_dict,
)
from active_skill_system.application.ports.tool import ToolCapability, ToolProfile
from active_skill_system.application.tools.registry import ToolRegistry
from active_skill_system.domain.compiler_types import CompilerMetrics, CompilerNodeKind


def _baseline() -> dict:
    return {"cycles": 1000, "reg_pressure": 16, "spills": 4, "energy_proxy": 2.5}


# ── transform formulas ────────────────────────────────────────────────────


def test_tile_reduces_cycles() -> None:
    base = CompilerMetrics(cycles=1000, reg_pressure=16, spills=4, energy_proxy=2.5)
    m = _apply_transform(CompilerNodeKind.TRANSFORM_TILE, {"tile_size": 10}, base)
    assert m.cycles == 100  # 1000 // 10
    assert m.is_valid is True


def test_tile_increases_reg_pressure_and_spills() -> None:
    base = CompilerMetrics(cycles=1000, reg_pressure=16, spills=4, energy_proxy=2.5)
    m = _apply_transform(CompilerNodeKind.TRANSFORM_TILE, {"tile_size": 16}, base)
    assert m.reg_pressure == 16 + 2 * 16
    assert m.spills == 4 + 1  # ceil(16/16)


def test_tile_rejects_non_positive_size() -> None:
    base = CompilerMetrics(cycles=1000, reg_pressure=16, spills=4, energy_proxy=2.5)
    with pytest.raises(ValueError, match="tile_size"):
        _apply_transform(CompilerNodeKind.TRANSFORM_TILE, {"tile_size": 0}, base)


def test_interchange_reduces_reg_pressure() -> None:
    base = CompilerMetrics(cycles=1000, reg_pressure=16, spills=4, energy_proxy=2.5)
    m = _apply_transform(CompilerNodeKind.TRANSFORM_INTERCHANGE, {}, base)
    assert m.cycles == 1000
    assert m.reg_pressure == 15


def test_interchange_clamps_reg_pressure_at_zero() -> None:
    base = CompilerMetrics(cycles=100, reg_pressure=0, spills=0, energy_proxy=1.0)
    m = _apply_transform(CompilerNodeKind.TRANSFORM_INTERCHANGE, {}, base)
    assert m.reg_pressure == 0


def test_fusion_reduces_cycles_grows_pressure() -> None:
    base = CompilerMetrics(cycles=1000, reg_pressure=16, spills=4, energy_proxy=2.5)
    m = _apply_transform(CompilerNodeKind.TRANSFORM_FUSION, {"fused_loops": 2}, base)
    # 1000 * 0.7^2 = 490 (int)
    assert m.cycles == 490
    assert m.reg_pressure == 16 + 8
    assert m.spills == 3


def test_unroll_reduces_cycles_grows_pressure() -> None:
    base = CompilerMetrics(cycles=1000, reg_pressure=16, spills=4, energy_proxy=2.5)
    m = _apply_transform(CompilerNodeKind.TRANSFORM_UNROLL, {"unroll_factor": 4}, base)
    assert m.cycles == 250  # 1000 // 4
    assert m.reg_pressure == 16 + 4
    assert m.spills == 3


def test_unroll_rejects_factor_le_one() -> None:
    base = CompilerMetrics(cycles=1000, reg_pressure=16, spills=4, energy_proxy=2.5)
    with pytest.raises(ValueError, match="unroll_factor"):
        _apply_transform(CompilerNodeKind.TRANSFORM_UNROLL, {"unroll_factor": 1}, base)


# ── tool surface ──────────────────────────────────────────────────────────


def test_tool_name_and_capabilities() -> None:
    tool = CompilerToolStub()
    assert tool.name == "compiler_apply_transform"
    assert ToolCapability.COMPUTE in tool.capabilities
    assert tool.profile is ToolProfile.NORMAL


def test_tool_tile_returns_serialized_metrics() -> None:
    tool = CompilerToolStub()
    result = tool.invoke({"transform_type": "transform_tile", "params": {"tile_size": 10}, "baseline": _baseline()})
    assert result.success is True
    parsed = json.loads(result.text)
    assert parsed["cycles"] == 100
    assert parsed["is_valid"] is True
    assert result.evidence_id == "transform_tile"


def test_tool_missing_transform_returns_baseline_unchanged() -> None:
    tool = CompilerToolStub()
    result = tool.invoke({"baseline": _baseline()})
    assert result.success is True
    parsed = json.loads(result.text)
    assert parsed["cycles"] == 1000
    assert result.evidence_id == "missing_transform"


def test_tool_illegal_transform_fails() -> None:
    tool = CompilerToolStub()
    result = tool.invoke({
        "transform_type": "transform_tile",
        "params": {"tile_size": 10, "legal": False},
        "baseline": _baseline(),
    })
    assert result.success is False


def test_tool_unknown_transform_kind_fails() -> None:
    tool = CompilerToolStub()
    result = tool.invoke({"transform_type": "loop_nest", "baseline": _baseline()})
    assert result.success is False


def test_tool_bad_baseline_fails() -> None:
    tool = CompilerToolStub()
    result = tool.invoke({"transform_type": "transform_tile", "params": {}, "baseline": {"cycles": -1}})
    assert result.success is False


def test_tool_non_dict_args_fails() -> None:
    tool = CompilerToolStub()
    result = tool.invoke("not a dict")  # type: ignore[arg-type]
    assert result.success is False


# ── registry integration ─────────────────────────────────────────────────


def test_tool_registers_in_registry() -> None:
    reg = ToolRegistry()
    tool = CompilerToolStub()
    reg.register(tool)
    found = reg.get_by_capability(ToolCapability.COMPUTE)
    assert found is tool


def test_tool_idempotent_register() -> None:
    reg = ToolRegistry()
    tool = CompilerToolStub()
    reg.register(tool)
    reg.register(tool)
    assert len(reg.list_tools()) == 1


def test_tool_visible_at_normal_profile() -> None:
    reg = ToolRegistry()
    reg.register(CompilerToolStub())
    assert any(t.name == "compiler_apply_transform" for t in reg.list_by_profile(ToolProfile.NORMAL))


# ── module hygiene ───────────────────────────────────────────────────────


def test_metrics_helpers_roundtrip() -> None:
    m = CompilerMetrics(cycles=10, reg_pressure=4, spills=0, energy_proxy=1.0)
    assert _metrics_from_dict(_metrics_to_dict(m)) == m


def test_module_infra_free() -> None:
    import importlib
    from pathlib import Path

    mod = importlib.import_module("active_skill_system.adapters.compiler_tool_stub")
    src = Path(mod.__file__).read_text()
    # Adapter layer CAN import from application. It must NOT import infra.
    for forbidden in ("import activegraph", "from activegraph", "import anthropic", "import openai"):
        assert forbidden not in src, f"compiler_tool_stub.py must not contain '{forbidden}' (R002)"
