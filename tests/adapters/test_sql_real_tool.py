"""Tests for SQLRealTool (M037 S01 T02).

Verifies the real-instrument SQL tool produces source-of-truth fitness from
a live in-memory SQLite database, mirrors the SQLToolStub invoke contract,
and fails gracefully. Also guards the R006 adapter-size limit.
"""

from __future__ import annotations

import json
from pathlib import Path

from active_skill_system.adapters.sql_real_tool import SQLRealTool
from active_skill_system.application.ports.tool import ToolCapability, ToolProfile

_BASELINE = {"rows_examined": 1000, "rows_returned": 10, "time_ms": 100.0, "plan_cost": 50.0}


def _result_dict(result):
    return json.loads(result.text)


def test_capability_and_profile_match_stub_contract():
    tool = SQLRealTool()
    assert tool.capabilities == frozenset({ToolCapability.COMPUTE})
    assert tool.profile is ToolProfile.NORMAL
    assert tool.name == "sql_apply_transform_real"


def test_missing_transform_returns_baseline_unchanged():
    tool = SQLRealTool()
    result = tool.invoke({"baseline": _BASELINE})
    assert result.success is True
    assert result.evidence_id == "missing_transform"
    assert _result_dict(result)["rows_examined"] == 1000


def test_add_index_reduces_rows_examined_against_full_scan():
    """The headline proof: a real CREATE INDEX must lower rows_examined."""
    tool = SQLRealTool()
    baseline = tool.invoke({"baseline": _BASELINE})
    with_index = tool.invoke(
        {"transform_type": "sql_transform_add_index", "params": {"cols": 1}, "baseline": _BASELINE}
    )
    assert baseline.success and with_index.success
    before = _result_dict(baseline)["rows_examined"]
    after = _result_dict(with_index)["rows_examined"]
    assert after < before, f"index did not reduce rows_examined: {before} -> {after}"


def test_add_index_cols_two_still_reduces():
    tool = SQLRealTool()
    result = tool.invoke(
        {"transform_type": "sql_transform_add_index", "params": {"cols": 2}, "baseline": _BASELINE}
    )
    assert result.success
    assert _result_dict(result)["rows_examined"] < 1000


def test_non_dict_args_fail():
    tool = SQLRealTool()
    assert tool.invoke("not a dict").success is False  # type: ignore[arg-type]
    assert tool.invoke(None).success is False  # type: ignore[arg-type]


def test_unknown_transform_kind_fails():
    tool = SQLRealTool()
    result = tool.invoke({"transform_type": "nope", "baseline": _BASELINE})
    assert result.success is False
    assert result.evidence_id == "nope"


def test_illegal_transform_fails():
    tool = SQLRealTool()
    result = tool.invoke(
        {
            "transform_type": "sql_transform_add_index",
            "params": {"legal": False},
            "baseline": _BASELINE,
        }
    )
    assert result.success is False


def test_add_index_non_positive_cols_fails():
    tool = SQLRealTool()
    result = tool.invoke(
        {"transform_type": "sql_transform_add_index", "params": {"cols": 0}, "baseline": _BASELINE}
    )
    assert result.success is False


def test_invalid_baseline_dict_fails():
    tool = SQLRealTool()
    result = tool.invoke({"transform_type": "sql_transform_add_index", "params": {"cols": 1}, "baseline": {}})
    assert result.success is False


def test_result_metrics_are_non_negative_and_valid():
    tool = SQLRealTool()
    result = tool.invoke(
        {"transform_type": "sql_transform_add_index", "params": {"cols": 1}, "baseline": _BASELINE}
    )
    metrics = _result_dict(result)
    assert metrics["rows_examined"] >= 1
    assert metrics["rows_returned"] == 10
    assert metrics["is_valid"] is True


def test_module_under_200_loc_r006():
    """R006: each adapter ≤200 LOC (split into submodules above that)."""
    src = Path("src/active_skill_system/adapters/sql_real_tool.py")
    assert src.exists()
    assert len(src.read_text(encoding="utf-8").splitlines()) <= 200
