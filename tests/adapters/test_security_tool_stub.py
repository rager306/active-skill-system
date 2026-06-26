"""Tests for SecurityToolStub + SecurityRepairPolicy (M026 S02)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from active_skill_system.adapters.security_tool_stub import SecurityToolStub
from active_skill_system.application.use_cases.security_repair_policy import SecurityRepairPolicy
from active_skill_system.domain.security_types import (
    SecurityActionType,
    SecurityGapClass,
    SecurityMetrics,
)


def _baseline_dict(threats: int = 50, risk: float = 7.5, coverage: float = 0.6, exposure: float = 100.0) -> dict:
    return {"threat_count": threats, "risk_score": risk, "coverage_ratio": coverage, "exposure_time": exposure, "is_valid": True}


# ── SecurityToolStub ─────────────────────────────────────────────────────


def test_tool_name_and_capabilities() -> None:
    tool = SecurityToolStub()
    assert tool.name == "security_apply_transform"


def test_patch_reduces_threats_and_risk() -> None:
    tool = SecurityToolStub()
    result = tool.invoke({
        "transform_type": "sec_transform_patch", "params": {"cve_count": 5}, "baseline": _baseline_dict(threats=50),
    })
    assert result.success is True
    parsed = json.loads(result.text)
    assert parsed["threat_count"] == 45
    assert abs(parsed["risk_score"] - 3.75) < 1e-9


def test_add_control_increases_coverage_and_reduces_risk() -> None:
    tool = SecurityToolStub()
    result = tool.invoke({
        "transform_type": "sec_transform_add_control", "params": {"controls": 2}, "baseline": _baseline_dict(coverage=0.6),
    })
    assert result.success is True
    parsed = json.loads(result.text)
    assert abs(parsed["coverage_ratio"] - 0.8) < 1e-9
    assert abs(parsed["risk_score"] - 6.0) < 1e-9


def test_isolate_halves_threats() -> None:
    tool = SecurityToolStub()
    result = tool.invoke({
        "transform_type": "sec_transform_isolate", "params": {}, "baseline": _baseline_dict(threats=50, exposure=100.0),
    })
    assert result.success is True
    parsed = json.loads(result.text)
    assert parsed["threat_count"] == 25
    assert abs(parsed["exposure_time"] - 30.0) < 1e-9


def test_quarantine_reduces_threats_to_quarter() -> None:
    tool = SecurityToolStub()
    result = tool.invoke({
        "transform_type": "sec_transform_quarantine", "params": {}, "baseline": _baseline_dict(threats=50),
    })
    assert result.success is True
    parsed = json.loads(result.text)
    assert parsed["threat_count"] == 12  # 50 // 4 = 12
    assert parsed["exposure_time"] == 0.0


def test_missing_transform_type_returns_baseline() -> None:
    tool = SecurityToolStub()
    result = tool.invoke({"baseline": _baseline_dict()})
    assert result.success is True
    assert result.evidence_id == "missing_transform"


def test_illegal_transform_returns_failure() -> None:
    tool = SecurityToolStub()
    result = tool.invoke({
        "transform_type": "sec_transform_patch", "params": {"legal": False}, "baseline": _baseline_dict(),
    })
    assert result.success is False


def test_unknown_kind_returns_failure() -> None:
    tool = SecurityToolStub()
    result = tool.invoke({"transform_type": "sec_transform_bogus", "params": {}, "baseline": _baseline_dict()})
    assert result.success is False


def test_module_infra_free() -> None:
    from active_skill_system.adapters import security_tool_stub
    src = Path(security_tool_stub.__file__).read_text(encoding="utf-8")
    assert "activegraph" not in src
    assert "anthropic" not in src
    assert "openai" not in src


# ── SecurityRepairPolicy ─────────────────────────────────────────────────


def test_default_policy_maps_every_gap() -> None:
    policy = SecurityRepairPolicy.default_policy()
    for gap in SecurityGapClass:
        assert policy.covers(gap)


def test_default_policy_specific_mappings() -> None:
    policy = SecurityRepairPolicy.default_policy()
    assert policy.action_for(SecurityGapClass.UNPATCHED_VULN) is SecurityActionType.PATCH
    assert policy.action_for(SecurityGapClass.MISSING_CONTROL) is SecurityActionType.ADD_CONTROL
    assert policy.action_for(SecurityGapClass.LATERAL_MOVEMENT) is SecurityActionType.ISOLATE
    assert policy.action_for(SecurityGapClass.PRIVILEGE_ESCALATION) is SecurityActionType.ISOLATE
    assert policy.action_for(SecurityGapClass.EXPOSURE_REGRESSION) is SecurityActionType.QUARANTINE


def test_action_for_falls_back_to_quarantine() -> None:
    policy = SecurityRepairPolicy(mapping={SecurityGapClass.UNPATCHED_VULN: SecurityActionType.PATCH})
    assert policy.action_for(SecurityGapClass.EXPOSURE_REGRESSION) is SecurityActionType.QUARANTINE


def test_empty_mapping_rejected() -> None:
    with pytest.raises(ValueError, match="mapping must be non-empty"):
        SecurityRepairPolicy(mapping={})


def test_covers_returns_false_for_missing_mappings() -> None:
    policy = SecurityRepairPolicy(mapping={SecurityGapClass.UNPATCHED_VULN: SecurityActionType.PATCH})
    assert policy.covers(SecurityGapClass.EXPOSURE_REGRESSION) is False


def test_module_infra_free_repair_policy() -> None:
    from active_skill_system.application.use_cases import security_repair_policy
    src = Path(security_repair_policy.__file__).read_text(encoding="utf-8")
    for forbidden in ("import activegraph", "from activegraph", "import anthropic", "import openai"):
        assert forbidden not in src