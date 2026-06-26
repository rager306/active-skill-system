"""Tests for domain/security_types.py (M026 S01)."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from active_skill_system.domain.security_types import (
    SecurityActionType,
    SecurityGapClass,
    SecurityMetrics,
    SecurityNodeKind,
    SecurityTransformParams,
)

# ── SecurityNodeKind ─────────────────────────────────────────────────────


def test_security_node_kind_has_plan_kinds() -> None:
    assert SecurityNodeKind.VULNERABILITY.value == "vulnerability"
    assert SecurityNodeKind.ATTACK_VECTOR.value == "attack_vector"
    assert SecurityNodeKind.MITIGATION.value == "mitigation"
    assert SecurityNodeKind.CONTROL.value == "control"


def test_security_node_kind_has_transform_kinds() -> None:
    assert SecurityNodeKind.SEC_TRANSFORM_PATCH.value == "sec_transform_patch"
    assert SecurityNodeKind.SEC_TRANSFORM_ADD_CONTROL.value == "sec_transform_add_control"
    assert SecurityNodeKind.SEC_TRANSFORM_ISOLATE.value == "sec_transform_isolate"
    assert SecurityNodeKind.SEC_TRANSFORM_QUARANTINE.value == "sec_transform_quarantine"


# ── SecurityGapClass ─────────────────────────────────────────────────────


def test_security_gap_class_has_five_values() -> None:
    assert len(SecurityGapClass) == 5
    assert SecurityGapClass.UNPATCHED_VULN.value == "unpatched_vuln"
    assert SecurityGapClass.MISSING_CONTROL.value == "missing_control"
    assert SecurityGapClass.LATERAL_MOVEMENT.value == "lateral_movement"
    assert SecurityGapClass.PRIVILEGE_ESCALATION.value == "privilege_escalation"
    assert SecurityGapClass.EXPOSURE_REGRESSION.value == "exposure_regression"


# ── SecurityActionType ───────────────────────────────────────────────────


def test_security_action_type_has_four_values() -> None:
    assert len(SecurityActionType) == 4
    assert SecurityActionType.PATCH.value == "patch"
    assert SecurityActionType.ADD_CONTROL.value == "add_control"
    assert SecurityActionType.ISOLATE.value == "isolate"
    assert SecurityActionType.QUARANTINE.value == "quarantine"


# ── SecurityTransformParams ──────────────────────────────────────────────


def _patch(cve_id: str = "CVE-2024-1234") -> SecurityTransformParams:
    return SecurityTransformParams(
        transform_type=SecurityNodeKind.SEC_TRANSFORM_PATCH,
        params={"cve_id": cve_id},
        legal=True,
    )


def test_security_transform_params_accepts_valid_kind() -> None:
    p = _patch()
    assert p.transform_type is SecurityNodeKind.SEC_TRANSFORM_PATCH


def test_security_transform_params_rejects_non_transform_kind() -> None:
    with pytest.raises(ValueError, match="SEC_TRANSFORM"):
        SecurityTransformParams(
            transform_type=SecurityNodeKind.VULNERABILITY,
            params={},
            legal=True,
        )


def test_security_transform_params_rejects_non_dict_params() -> None:
    with pytest.raises(ValueError, match="params must be a dict"):
        SecurityTransformParams(
            transform_type=SecurityNodeKind.SEC_TRANSFORM_PATCH,
            params=["not", "a", "dict"],  # type: ignore[arg-type]
            legal=True,
        )


# ── SecurityMetrics ──────────────────────────────────────────────────────


def _baseline_metrics(threats: int = 50) -> SecurityMetrics:
    return SecurityMetrics(
        threat_count=threats, risk_score=7.5, coverage_ratio=0.6, exposure_time=100.0, is_valid=True,
    )


def test_security_metrics_rejects_negative_threat_count() -> None:
    with pytest.raises(ValueError, match="threat_count"):
        SecurityMetrics(threat_count=-1, risk_score=0.0, coverage_ratio=0.0, exposure_time=0.0)


def test_security_metrics_rejects_coverage_ratio_out_of_range() -> None:
    with pytest.raises(ValueError, match="coverage_ratio"):
        SecurityMetrics(threat_count=0, risk_score=0.0, coverage_ratio=1.5, exposure_time=0.0)


def test_security_metrics_better_than_strictly_lower_threat_count() -> None:
    base = _baseline_metrics(threats=50)
    better = _baseline_metrics(threats=20)
    assert better.better_than(base)
    assert not base.better_than(better)


def test_security_metrics_better_than_tie_break_by_risk_score() -> None:
    base = SecurityMetrics(threat_count=50, risk_score=7.5, coverage_ratio=0.6, exposure_time=100.0, is_valid=True)
    better = SecurityMetrics(threat_count=50, risk_score=5.0, coverage_ratio=0.6, exposure_time=100.0, is_valid=True)
    assert better.better_than(base)


def test_security_metrics_better_than_tie_break_by_coverage_ratio_higher() -> None:
    """coverage_ratio is inverse axis — higher is better."""
    base = SecurityMetrics(threat_count=50, risk_score=7.5, coverage_ratio=0.6, exposure_time=100.0, is_valid=True)
    better = SecurityMetrics(threat_count=50, risk_score=7.5, coverage_ratio=0.9, exposure_time=100.0, is_valid=True)
    assert better.better_than(base)


def test_security_metrics_invalid_never_beats_valid() -> None:
    valid = _baseline_metrics(threats=1000)
    invalid = SecurityMetrics(threat_count=0, risk_score=0.0, coverage_ratio=1.0, exposure_time=0.0, is_valid=False)
    assert not invalid.better_than(valid)
    assert valid.better_than(invalid)


def test_security_metrics_exposure_time_does_not_affect_ranking() -> None:
    """exposure_time is reported but not in the ranking (side diagnostic)."""
    base = SecurityMetrics(threat_count=50, risk_score=7.5, coverage_ratio=0.6, exposure_time=100.0, is_valid=True)
    same_other = SecurityMetrics(threat_count=50, risk_score=7.5, coverage_ratio=0.6, exposure_time=999.0, is_valid=True)
    assert not same_other.better_than(base)
    assert not base.better_than(same_other)


def test_security_metrics_better_than_handles_invalid_input() -> None:
    m = _baseline_metrics()
    assert not m.better_than("not metrics")  # type: ignore[arg-type]


# ── R002 ────────────────────────────────────────────────────────────────


def test_security_types_module_infra_free() -> None:
    mod = importlib.import_module("active_skill_system.domain.security_types")
    src = Path(mod.__file__).read_text(encoding="utf-8")
    for forbidden in ("import activegraph", "from activegraph", "import anthropic", "import openai"):
        assert forbidden not in src, f"security_types.py must not contain '{forbidden}' (R002)"
