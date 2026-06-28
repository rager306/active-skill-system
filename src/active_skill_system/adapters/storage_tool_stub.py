"""L3 Adapter — StorageToolStub (M029 S02).

Deterministic stub simulating DB storage transforms. Primary axis: storage_bytes.

  COMPRESS(ratio)    : storage_bytes *= (1 - ratio), query_latency_ms += 1.0
  PARTITION(n)       : query_latency_ms //= n, storage_bytes unchanged
  SHARD(n)           : query_latency_ms //= n, storage_bytes unchanged
  REINDEX            : query_latency_ms *= 0.5, index_count += 1
"""

from __future__ import annotations

import json
from typing import Any

from active_skill_system.application.ports.tool import (
    ToolCapability,
    ToolProfile,
    ToolResult,
)
from active_skill_system.domain.storage_types import StorageMetrics, StorageNodeKind


def _metrics_from_dict(d: dict[str, Any]) -> StorageMetrics:
    if not isinstance(d, dict):
        raise ValueError(f"baseline must be a dict (got {type(d).__name__})")
    try:
        return StorageMetrics(
            storage_bytes=int(d["storage_bytes"]),
            query_latency_ms=float(d["query_latency_ms"]),
            index_count=int(d["index_count"]),
            is_valid=bool(d.get("is_valid", True)),
        )
    except KeyError as e:
        raise ValueError(f"baseline missing required key: {e.args[0]!r}") from None
    except (TypeError, ValueError) as e:
        raise ValueError(f"baseline has invalid values: {e}") from None


def _apply_transform(kind: StorageNodeKind, params: dict[str, Any], baseline: StorageMetrics) -> StorageMetrics:
    storage_bytes = baseline.storage_bytes
    query_latency_ms = float(baseline.query_latency_ms)
    index_count = baseline.index_count

    if kind is StorageNodeKind.STOR_TRANSFORM_COMPRESS:
        ratio = float(params.get("ratio", 0.5))
        if ratio <= 0.0 or ratio >= 1.0:
            raise ValueError(f"ratio must be in (0.0, 1.0) (got {ratio!r})")
        storage_bytes = max(0, int(storage_bytes * (1.0 - ratio)))
        query_latency_ms = query_latency_ms + 1.0
    elif kind is StorageNodeKind.STOR_TRANSFORM_PARTITION:
        n = int(params.get("n_partitions", 2))
        if n < 2:
            raise ValueError(f"n_partitions must be >= 2 (got {n!r})")
        query_latency_ms = max(0.0, query_latency_ms / n)
    elif kind is StorageNodeKind.STOR_TRANSFORM_SHARD:
        n = int(params.get("n_shards", 2))
        if n < 2:
            raise ValueError(f"n_shards must be >= 2 (got {n!r})")
        query_latency_ms = max(0.0, query_latency_ms / n)
    elif kind is StorageNodeKind.STOR_TRANSFORM_REINDEX:
        query_latency_ms = max(0.0, query_latency_ms * 0.5)
        index_count = index_count + 1
    else:
        raise ValueError(f"unsupported storage transform kind: {kind!r}")

    return StorageMetrics(storage_bytes=storage_bytes, query_latency_ms=query_latency_ms, index_count=index_count, is_valid=True)


class StorageToolStub:
    """StorageToolStub class."""
    name = "storage_apply_transform"
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
                evidence_id="missing_transform", success=True,
            )
        try:
            kind = StorageNodeKind(kind_raw) if not isinstance(kind_raw, StorageNodeKind) else kind_raw
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
            evidence_id=str(kind_raw), success=True,
        )


def _metrics_to_dict(m: StorageMetrics) -> dict[str, Any]:
    return {"storage_bytes": m.storage_bytes, "query_latency_ms": m.query_latency_ms, "index_count": m.index_count, "is_valid": m.is_valid}
