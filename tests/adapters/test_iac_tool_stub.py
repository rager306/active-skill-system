"""Tests for IaCToolStub (M023 S02)."""

from __future__ import annotations

import json
from pathlib import Path

from active_skill_system.adapters.iac_tool_stub import IaCToolStub
from active_skill_system.application.ports.tool import ToolCapability


def _baseline_dict(
    resources: int = 100, modules: int = 10, vars_: int = 20, drift: float = 0.5
) -> dict:
    return {
        "resource_count": resources, "module_count": modules,
        "variable_count": vars_, "drift_score": drift, "is_valid": True,
    }


# ── Tool surface ──────────────────────────────────────────────────────────


def test_tool_name_and_capabilities() -> None:
    tool = IaCToolStub()
    assert tool.name == "iac_apply_transform"
    assert ToolCapability.COMPUTE in tool.capabilities


# ── Transform formulas ────────────────────────────────────────────────────


def test_remove_unused_decrements_variable_count() -> None:
    """REMOVE_UNUSED: variable_count -= 1."""
    tool = IaCToolStub()
    result = tool.invoke({
        "transform_type": "ia_transform_remove_unused",
        "params": {"variable_name": "old_var"},
        "baseline": _baseline_dict(vars_=20),
    })
    assert result.success is True
    parsed = json.loads(result.text)
    assert parsed["variable_count"] == 19
    assert parsed["resource_count"] == 100  # unchanged


def test_add_output_increments_resource_and_module() -> None:
    """ADD_OUTPUT: resource_count += 1, module_count += 1."""
    tool = IaCToolStub()
    result = tool.invoke({
        "transform_type": "ia_transform_add_output",
        "params": {},
        "baseline": _baseline_dict(resources=100, modules=10),
    })
    assert result.success is True
    parsed = json.loads(result.text)
    assert parsed["resource_count"] == 101
    assert parsed["module_count"] == 11


def test_restructure_dep_halves_module_count() -> None:
    """RESTRUCTURE_DEP: module_count //= 2."""
    tool = IaCToolStub()
    result = tool.invoke({
        "transform_type": "ia_transform_restructure_dep",
        "params": {},
        "baseline": _baseline_dict(modules=10),
    })
    assert result.success is True
    parsed = json.loads(result.text)
    assert parsed["module_count"] == 5


def test_replan_providers_halves_resources_and_drift() -> None:
    """REPLAN_PROVIDERS: resource_count //= 2, drift_score *= 0.5."""
    tool = IaCToolStub()
    result = tool.invoke({
        "transform_type": "ia_transform_replan_providers",
        "params": {},
        "baseline": _baseline_dict(resources=100, drift=0.5),
    })
    assert result.success is True
    parsed = json.loads(result.text)
    assert parsed["resource_count"] == 50
    assert abs(parsed["drift_score"] - 0.25) < 1e-9


# ── Failure modes (D007) ──────────────────────────────────────────────────


def test_missing_transform_type_returns_baseline() -> None:
    tool = IaCToolStub()
    result = tool.invoke({"baseline": _baseline_dict()})
    assert result.success is True
    assert result.evidence_id == "missing_transform"


def test_unknown_kind_returns_failure() -> None:
    tool = IaCToolStub()
    result = tool.invoke({
        "transform_type": "ia_transform_bogus",
        "params": {},
        "baseline": _baseline_dict(),
    })
    assert result.success is False


def test_illegal_transform_returns_failure() -> None:
    tool = IaCToolStub()
    result = tool.invoke({
        "transform_type": "ia_transform_remove_unused",
        "params": {"legal": False},
        "baseline": _baseline_dict(),
    })
    assert result.success is False


def test_non_dict_args_returns_failure() -> None:
    tool = IaCToolStub()
    result = tool.invoke("not a dict")  # type: ignore[arg-type]
    assert result.success is False


def test_baseline_missing_key_returns_failure() -> None:
    tool = IaCToolStub()
    result = tool.invoke({
        "transform_type": "ia_transform_remove_unused",
        "params": {},
        "baseline": {"resource_count": 100},  # missing other keys
    })
    assert result.success is False


# ── R002 / module hygiene ────────────────────────────────────────────────


def test_module_infra_free() -> None:
    from active_skill_system.adapters import iac_tool_stub
    src = Path(iac_tool_stub.__file__).read_text(encoding="utf-8")
    assert "activegraph" not in src
    assert "anthropic" not in src
    assert "openai" not in src
