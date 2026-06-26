"""L2 Application — SecurityRepairPolicy (M026 S02).

Maps security audit gaps to repair actions. Mirrors compiler/sql/iac
RepairPolicy shape. Default 5→4 mapping. QUARANTINE fallback (most
conservative action — isolates the threat completely).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from active_skill_system.domain.security_types import (
    SecurityActionType,
    SecurityGapClass,
)


@dataclass(frozen=True)
class SecurityRepairPolicy:
    mapping: dict[SecurityGapClass, SecurityActionType] = field(default_factory=dict)

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.mapping, dict):
            errors.append(f"mapping must be a dict (got {type(self.mapping).__name__})")
        elif not self.mapping:
            errors.append("mapping must be non-empty")
        else:
            for gap, action in self.mapping.items():
                if not isinstance(gap, SecurityGapClass):
                    errors.append(f"mapping key must be a SecurityGapClass (got {type(gap).__name__})")
                if not isinstance(action, SecurityActionType):
                    errors.append(f"mapping value must be a SecurityActionType (got {type(action).__name__})")
        if errors:
            raise ValueError("SecurityRepairPolicy invariant violation: " + "; ".join(errors))

    def action_for(self, gap: SecurityGapClass) -> SecurityActionType:
        return self.mapping.get(gap, SecurityActionType.QUARANTINE)

    def covers(self, gap: SecurityGapClass) -> bool:
        return gap in self.mapping

    @staticmethod
    def default_policy() -> "SecurityRepairPolicy":
        return SecurityRepairPolicy(
            mapping={
                SecurityGapClass.UNPATCHED_VULN: SecurityActionType.PATCH,
                SecurityGapClass.MISSING_CONTROL: SecurityActionType.ADD_CONTROL,
                SecurityGapClass.LATERAL_MOVEMENT: SecurityActionType.ISOLATE,
                SecurityGapClass.PRIVILEGE_ESCALATION: SecurityActionType.ISOLATE,
                SecurityGapClass.EXPOSURE_REGRESSION: SecurityActionType.QUARANTINE,
            },
        )