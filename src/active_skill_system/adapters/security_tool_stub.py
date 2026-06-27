"""L3 Adapter — SecurityToolStub (M026 S02).

Deterministic stub tool simulating security audit transforms.
Mirrors compiler_tool_stub.py / sql_tool_stub.py / iac_tool_stub.py shape.

Formulae (threat_count is the primary axis — lower = better):

  PATCH(cve_count=N)      : threat_count -= N, risk_score *= 0.5
  ADD_CONTROL(controls=N) : coverage_ratio += 0.1*N (capped 1.0), risk_score *= 0.8
  ISOLATE                 : threat_count //= 2, exposure_time *= 0.3
  QUARANTINE              : threat_count //= 4, exposure_time = 0
"""

from __future__ import annotations

import json
from typing import Any

from active_skill_system.application.ports.tool import (
    ToolCapability,
    ToolProfile,
    ToolResult,
)
from active_skill_system.domain.security_types import SecurityMetrics, SecurityNodeKind


def _metrics_from_dict(d: dict[str, Any]) -> SecurityMetrics:
    if not isinstance(d, dict):
        raise ValueError(f"baseline must be a dict (got {type(d).__name__})")
    try:
        return SecurityMetrics(
            threat_count=int(d["threat_count"]),
            risk_score=float(d["risk_score"]),
            coverage_ratio=float(d["coverage_ratio"]),
            exposure_time=float(d["exposure_time"]),
            is_valid=bool(d.get("is_valid", True)),
        )
    except KeyError as e:
        raise ValueError(f"baseline missing required key: {e.args[0]!r}") from None
    except (TypeError, ValueError) as e:
        raise ValueError(f"baseline has invalid values: {e}") from None


def _apply_transform(kind: SecurityNodeKind, params: dict[str, Any], baseline: SecurityMetrics) -> SecurityMetrics:
    threat_count = baseline.threat_count
    risk_score = float(baseline.risk_score)
    coverage_ratio = float(baseline.coverage_ratio)
    exposure_time = float(baseline.exposure_time)

    if kind is SecurityNodeKind.SEC_TRANSFORM_PATCH:
        n = int(params.get("cve_count", 1))
        if n < 1:
            raise ValueError(f"cve_count must be >= 1 (got {n!r})")
        threat_count = max(0, threat_count - n)
        risk_score = max(0.0, risk_score * 0.5)
    elif kind is SecurityNodeKind.SEC_TRANSFORM_ADD_CONTROL:
        n = int(params.get("controls", 1))
        if n < 1:
            raise ValueError(f"controls must be >= 1 (got {n!r})")
        coverage_ratio = min(1.0, coverage_ratio + 0.1 * n)
        risk_score = max(0.0, risk_score * 0.8)
    elif kind is SecurityNodeKind.SEC_TRANSFORM_ISOLATE:
        threat_count = max(0, threat_count // 2)
        exposure_time = max(0.0, exposure_time * 0.3)
    elif kind is SecurityNodeKind.SEC_TRANSFORM_QUARANTINE:
        threat_count = max(0, threat_count // 4)
        exposure_time = 0.0
    else:
        raise ValueError(f"unsupported security transform kind: {kind!r}")

    return SecurityMetrics(
        threat_count=threat_count,
        risk_score=risk_score,
        coverage_ratio=coverage_ratio,
        exposure_time=exposure_time,
        is_valid=True,
    )


class SecurityToolStub:
    name = "security_apply_transform"
    capabilities = frozenset({ToolCapability.COMPUTE})
    profile = ToolProfile.NORMAL

    def invoke(self, args: dict[str, Any]) -> ToolResult:
        if not isinstance(args, dict):
            return ToolResult(text="", evidence_id=None, success=False)
        kind_raw = args.get("transform_type")
        params_raw = args.get("params", {})
        baseline_raw = args.get("baseline")
        if kind_raw is None:
            try:
                baseline = _metrics_from_dict(baseline_raw if isinstance(baseline_raw, dict) else {})
            except ValueError:
                return ToolResult(text="", evidence_id=None, success=False)
            return ToolResult(
                text=json.dumps(_metrics_to_dict(baseline), sort_keys=True),
                evidence_id="missing_transform",
                success=True,
            )
        try:
            kind = SecurityNodeKind(kind_raw) if not isinstance(kind_raw, SecurityNodeKind) else kind_raw
        except ValueError:
            return ToolResult(text="", evidence_id=str(kind_raw), success=False)
        try:
            baseline = _metrics_from_dict(baseline_raw if isinstance(baseline_raw, dict) else {})
        except ValueError:
            return ToolResult(text="", evidence_id=str(kind_raw), success=False)
        if not isinstance(params_raw, dict):
            return ToolResult(text="", evidence_id=str(kind_raw), success=False)
        if params_raw.get("legal", True) is False:
            return ToolResult(text="", evidence_id=str(kind_raw), success=False)
        try:
            new_metrics = _apply_transform(kind, params_raw, baseline)
        except ValueError:
            return ToolResult(text="", evidence_id=str(kind_raw), success=False)
        return ToolResult(
            text=json.dumps(_metrics_to_dict(new_metrics), sort_keys=True),
            evidence_id=str(kind_raw),
            success=True,
        )


def _metrics_to_dict(m: SecurityMetrics) -> dict[str, Any]:
    return {
        "threat_count": m.threat_count,
        "risk_score": m.risk_score,
        "coverage_ratio": m.coverage_ratio,
        "exposure_time": m.exposure_time,
        "is_valid": m.is_valid,
    }
