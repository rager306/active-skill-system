"""L1 Domain — Security audit optimization types (M026 S01).

Domain profile for security audit optimization. Mirrors compiler_types.py
(M016), sql_types.py (M018), iac_types.py (M023) shape on a different
problem class: declarative security audit plans (patch, isolate,
quarantine). Primary fitness axis: threat_count (lower = better).

Pure domain. NO I/O, NO infrastructure imports (R002). stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class SecurityNodeKind(StrEnum):
    """Node types for security audit optimization."""

    VULNERABILITY = "vulnerability"
    ATTACK_VECTOR = "attack_vector"
    MITIGATION = "mitigation"
    CONTROL = "control"
    # ── Security plan transforms ───────────────────────────────────────
    SEC_TRANSFORM_PATCH = "sec_transform_patch"
    SEC_TRANSFORM_ADD_CONTROL = "sec_transform_add_control"
    SEC_TRANSFORM_ISOLATE = "sec_transform_isolate"
    SEC_TRANSFORM_QUARANTINE = "sec_transform_quarantine"


class SecurityGapClass(StrEnum):
    """Classification of security audit gaps."""

    UNPATCHED_VULN = "unpatched_vuln"
    MISSING_CONTROL = "missing_control"
    LATERAL_MOVEMENT = "lateral_movement"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    EXPOSURE_REGRESSION = "exposure_regression"


class SecurityActionType(StrEnum):
    """Type of repair action for a security gap."""

    PATCH = "patch"
    ADD_CONTROL = "add_control"
    ISOLATE = "isolate"
    QUARANTINE = "quarantine"


@dataclass(frozen=True)
class SecurityTransformParams:
    """Parameters for a specific security transform.

    Carries:
      - transform_type: one of SecurityNodeKind (SEC_TRANSFORM_* kind).
      - params: transform parameters (e.g. {"cve_id": "CVE-2024-1234"}).
      - legal: whether the transform is legal given current environment.
    """

    transform_type: SecurityNodeKind
    params: dict[str, Any]
    legal: bool = True

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.transform_type, SecurityNodeKind):
            errors.append(
                f"transform_type must be a SecurityNodeKind (got {type(self.transform_type).__name__})"
            )
        transform_kinds = {
            SecurityNodeKind.SEC_TRANSFORM_PATCH,
            SecurityNodeKind.SEC_TRANSFORM_ADD_CONTROL,
            SecurityNodeKind.SEC_TRANSFORM_ISOLATE,
            SecurityNodeKind.SEC_TRANSFORM_QUARANTINE,
        }
        if self.transform_type not in transform_kinds:
            errors.append(
                f"transform_type must be a SEC_TRANSFORM_* kind (got {self.transform_type!r})"
            )
        if not isinstance(self.params, dict):
            errors.append(f"params must be a dict (got {type(self.params).__name__})")
        if not isinstance(self.legal, bool):
            errors.append(f"legal must be a bool (got {type(self.legal).__name__})")
        if errors:
            raise ValueError("SecurityTransformParams invariant violation: " + "; ".join(errors))


# ── Security metrics (M026 S01) ──────────────────────────────────────────


@dataclass(frozen=True)
class SecurityMetrics:
    """Measured security metrics after applying (or not) a transform.

    Carries:
      - threat_count: total open threats (int, >= 0; lower = better).
      - risk_score: aggregate risk score (float, >= 0.0; lower = better).
      - coverage_ratio: fraction of attack surface covered (float in [0, 1]; higher = better).
      - exposure_time: total exposure time in hours (float, >= 0.0; lower = better).
      - is_valid: False if the audit plan is invalid.
    """

    threat_count: int
    risk_score: float
    coverage_ratio: float
    exposure_time: float
    is_valid: bool = True

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.threat_count, int) or isinstance(self.threat_count, bool) or self.threat_count < 0:
            errors.append(f"threat_count must be a non-negative int (got {self.threat_count!r})")
        if not isinstance(self.risk_score, (int, float)) or isinstance(self.risk_score, bool) or float(self.risk_score) < 0.0:
            errors.append(f"risk_score must be a non-negative number (got {self.risk_score!r})")
        if not isinstance(self.coverage_ratio, (int, float)) or isinstance(self.coverage_ratio, bool) or not (0.0 <= float(self.coverage_ratio) <= 1.0):
            errors.append(f"coverage_ratio must be in [0.0, 1.0] (got {self.coverage_ratio!r})")
        if not isinstance(self.exposure_time, (int, float)) or isinstance(self.exposure_time, bool) or float(self.exposure_time) < 0.0:
            errors.append(f"exposure_time must be a non-negative number (got {self.exposure_time!r})")
        if not isinstance(self.is_valid, bool):
            errors.append(f"is_valid must be a bool (got {type(self.is_valid).__name__})")
        if errors:
            raise ValueError("SecurityMetrics invariant violation: " + "; ".join(errors))

    def better_than(self, other: SecurityMetrics) -> bool:
        """True if this metrics is strictly better than other.

        An invalid audit is never better than a valid one. Among valid
        audits, better means strictly lower threat_count, OR same
        threat_count with strictly lower risk_score, OR same
        threat_count+risk_score with strictly higher coverage_ratio
        (coverage is the inverse axis — higher is better).
        exposure_time is reported but not in the ranking.
        """
        if not isinstance(other, SecurityMetrics):
            return False
        if not self.is_valid and other.is_valid:
            return False
        if self.is_valid and not other.is_valid:
            return True
        if self.threat_count < other.threat_count:
            return True
        if self.threat_count == other.threat_count:
            if float(self.risk_score) < float(other.risk_score):
                return True
            if (
                float(self.risk_score) == float(other.risk_score)
                and float(self.coverage_ratio) > float(other.coverage_ratio)
            ):
                return True
        return False
