"""L2 Application — LogRepairPolicy (M030 S02)."""

from __future__ import annotations

from dataclasses import dataclass, field

from active_skill_system.domain.log_types import LogActionType, LogGapClass


@dataclass(frozen=True)
class LogRepairPolicy:
    mapping: dict[LogGapClass, LogActionType] = field(default_factory=dict)

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.mapping, dict):
            errors.append("mapping must be a dict")
        elif not self.mapping:
            errors.append("mapping must be non-empty")
        else:
            for gap, action in self.mapping.items():
                if not isinstance(gap, LogGapClass):
                    errors.append("keys must be LogGapClass")
                if not isinstance(action, LogActionType):
                    errors.append("values must be LogActionType")
        if errors:
            raise ValueError("LogRepairPolicy invariant violation: " + "; ".join(errors))

    def action_for(self, gap: LogGapClass) -> LogActionType:
        return self.mapping.get(gap, LogActionType.ROTATE)

    def covers(self, gap: LogGapClass) -> bool:
        return gap in self.mapping

    @staticmethod
    def default_policy() -> LogRepairPolicy:
        return LogRepairPolicy(mapping={
            LogGapClass.HIGH_ERROR_RATE: LogActionType.FILTER,
            LogGapClass.LOG_BLOAT: LogActionType.SAMPLE,
            LogGapClass.SLOW_PARSE: LogActionType.AGGREGATE,
            LogGapClass.MISSING_CONTEXT: LogActionType.AGGREGATE,
            LogGapClass.RETENTION_VIOLATION: LogActionType.ROTATE,
        })
