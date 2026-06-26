"""L2 Application — StorageRepairPolicy (M029 S02)."""

from __future__ import annotations

from dataclasses import dataclass, field

from active_skill_system.domain.storage_types import StorageActionType, StorageGapClass


@dataclass(frozen=True)
class StorageRepairPolicy:
    mapping: dict[StorageGapClass, StorageActionType] = field(default_factory=dict)

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.mapping, dict):
            errors.append("mapping must be a dict")
        elif not self.mapping:
            errors.append("mapping must be non-empty")
        else:
            for gap, action in self.mapping.items():
                if not isinstance(gap, StorageGapClass):
                    errors.append("keys must be StorageGapClass")
                if not isinstance(action, StorageActionType):
                    errors.append("values must be StorageActionType")
        if errors:
            raise ValueError("StorageRepairPolicy invariant violation: " + "; ".join(errors))

    def action_for(self, gap: StorageGapClass) -> StorageActionType:
        return self.mapping.get(gap, StorageActionType.REINDEX)

    def covers(self, gap: StorageGapClass) -> bool:
        return gap in self.mapping

    @staticmethod
    def default_policy() -> StorageRepairPolicy:
        return StorageRepairPolicy(mapping={
            StorageGapClass.BLOAT: StorageActionType.COMPRESS,
            StorageGapClass.MISSING_INDEX: StorageActionType.REINDEX,
            StorageGapClass.SLOW_QUERY: StorageActionType.PARTITION,
            StorageGapClass.UNBALANCED_SHARD: StorageActionType.SHARD,
            StorageGapClass.STORAGE_LEAK: StorageActionType.COMPRESS,
        })
