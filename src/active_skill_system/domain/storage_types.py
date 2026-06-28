"""L1 Domain — DB storage optimization types (M029 S01).

Domain profile for DB storage optimization (compression, partitioning,
sharding, reindexing). Mirrors compiler/SQL/IaC/security/ML/network types
shape. Primary fitness axis: storage_bytes (lower = better).

Pure domain. NO I/O, NO infrastructure imports (R002). stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class StorageNodeKind(StrEnum):
    """StorageNodeKind class."""
    TABLE = "table"
    INDEX = "index"
    PARTITION = "partition"
    SHARD = "shard"
    STOR_TRANSFORM_COMPRESS = "stor_transform_compress"
    STOR_TRANSFORM_PARTITION = "stor_transform_partition"
    STOR_TRANSFORM_SHARD = "stor_transform_shard"
    STOR_TRANSFORM_REINDEX = "stor_transform_reindex"


class StorageGapClass(StrEnum):
    """StorageGapClass class."""
    BLOAT = "bloat"
    MISSING_INDEX = "missing_index"
    SLOW_QUERY = "slow_query"
    UNBALANCED_SHARD = "unbalanced_shard"
    STORAGE_LEAK = "storage_leak"


class StorageActionType(StrEnum):
    """StorageActionType class."""
    COMPRESS = "compress"
    PARTITION = "partition"
    SHARD = "shard"
    REINDEX = "reindex"


@dataclass(frozen=True)
class StorageTransformParams:
    """StorageTransformParams class."""
    transform_type: StorageNodeKind
    params: dict[str, Any]
    legal: bool = True

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.transform_type, StorageNodeKind):
            errors.append(f"transform_type must be a StorageNodeKind (got {type(self.transform_type).__name__})")
        transform_kinds = {
            StorageNodeKind.STOR_TRANSFORM_COMPRESS,
            StorageNodeKind.STOR_TRANSFORM_PARTITION,
            StorageNodeKind.STOR_TRANSFORM_SHARD,
            StorageNodeKind.STOR_TRANSFORM_REINDEX,
        }
        if self.transform_type not in transform_kinds:
            errors.append(f"transform_type must be a STOR_TRANSFORM_* kind (got {self.transform_type!r})")
        if not isinstance(self.params, dict):
            errors.append(f"params must be a dict (got {type(self.params).__name__})")
        if not isinstance(self.legal, bool):
            errors.append(f"legal must be a bool (got {type(self.legal).__name__})")
        if errors:
            raise ValueError("StorageTransformParams invariant violation: " + "; ".join(errors))


@dataclass(frozen=True)
class StorageMetrics:
    """Measured DB storage metrics.

    Carries:
      - storage_bytes: total storage consumed (int, >= 0; lower = better).
      - query_latency_ms: average query latency (float, >= 0.0; lower = better).
      - index_count: number of indexes (int, >= 0; reported but not in ranking).
      - is_valid: False if the storage plan is invalid.
    """

    storage_bytes: int
    query_latency_ms: float
    index_count: int
    is_valid: bool = True

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.storage_bytes, int) or isinstance(self.storage_bytes, bool) or self.storage_bytes < 0:
            errors.append(f"storage_bytes must be a non-negative int (got {self.storage_bytes!r})")
        if not isinstance(self.query_latency_ms, (int, float)) or isinstance(self.query_latency_ms, bool) or float(self.query_latency_ms) < 0.0:
            errors.append(f"query_latency_ms must be a non-negative number (got {self.query_latency_ms!r})")
        if not isinstance(self.index_count, int) or isinstance(self.index_count, bool) or self.index_count < 0:
            errors.append(f"index_count must be a non-negative int (got {self.index_count!r})")
        if not isinstance(self.is_valid, bool):
            errors.append(f"is_valid must be a bool (got {type(self.is_valid).__name__})")
        if errors:
            raise ValueError("StorageMetrics invariant violation: " + "; ".join(errors))

    def better_than(self, other: StorageMetrics) -> bool:
        """True if this metrics is strictly better than other.

        Invalid never beats valid. Among valid: strictly lower storage_bytes wins,
        OR same storage_bytes with strictly lower query_latency_ms.
        index_count is reported but not in the ranking.
        """
        if not isinstance(other, StorageMetrics):
            return False
        if not self.is_valid and other.is_valid:
            return False
        if self.is_valid and not other.is_valid:
            return True
        if self.storage_bytes < other.storage_bytes:
            return True
        return self.storage_bytes == other.storage_bytes and float(self.query_latency_ms) < float(other.query_latency_ms)
