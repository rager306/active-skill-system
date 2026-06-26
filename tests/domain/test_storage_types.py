"""Tests for domain/storage_types.py (M029 S01)."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from active_skill_system.domain.storage_types import (
    StorageActionType,
    StorageGapClass,
    StorageMetrics,
    StorageNodeKind,
    StorageTransformParams,
)


def test_storage_node_kind_has_plan_kinds() -> None:
    assert StorageNodeKind.TABLE.value == "table"
    assert StorageNodeKind.INDEX.value == "index"
    assert StorageNodeKind.PARTITION.value == "partition"
    assert StorageNodeKind.SHARD.value == "shard"


def test_storage_node_kind_has_transform_kinds() -> None:
    assert StorageNodeKind.STOR_TRANSFORM_COMPRESS.value == "stor_transform_compress"
    assert StorageNodeKind.STOR_TRANSFORM_PARTITION.value == "stor_transform_partition"
    assert StorageNodeKind.STOR_TRANSFORM_SHARD.value == "stor_transform_shard"
    assert StorageNodeKind.STOR_TRANSFORM_REINDEX.value == "stor_transform_reindex"


def test_storage_gap_class_has_five_values() -> None:
    assert len(StorageGapClass) == 5
    assert StorageGapClass.BLOAT.value == "bloat"
    assert StorageGapClass.STORAGE_LEAK.value == "storage_leak"


def test_storage_action_type_has_four_values() -> None:
    assert len(StorageActionType) == 4
    assert StorageActionType.COMPRESS.value == "compress"
    assert StorageActionType.REINDEX.value == "reindex"


def test_storage_transform_params_accepts_valid_kind() -> None:
    p = StorageTransformParams(transform_type=StorageNodeKind.STOR_TRANSFORM_COMPRESS, params={"algo": "zstd"}, legal=True)
    assert p.transform_type is StorageNodeKind.STOR_TRANSFORM_COMPRESS


def test_storage_transform_params_rejects_non_transform_kind() -> None:
    with pytest.raises(ValueError, match="STOR_TRANSFORM"):
        StorageTransformParams(transform_type=StorageNodeKind.TABLE, params={}, legal=True)


def test_storage_transform_params_rejects_non_dict_params() -> None:
    with pytest.raises(ValueError, match="params must be a dict"):
        StorageTransformParams(transform_type=StorageNodeKind.STOR_TRANSFORM_COMPRESS, params=[1], legal=True)  # type: ignore[arg-type]


def _baseline_metrics(bytes_: int = 1000000) -> StorageMetrics:
    return StorageMetrics(storage_bytes=bytes_, query_latency_ms=50.0, index_count=5, is_valid=True)


def test_storage_metrics_rejects_negative_bytes() -> None:
    with pytest.raises(ValueError, match="storage_bytes"):
        StorageMetrics(storage_bytes=-1, query_latency_ms=0.0, index_count=0)


def test_storage_metrics_better_than_strictly_lower_bytes() -> None:
    base = _baseline_metrics(bytes_=1000000)
    better = _baseline_metrics(bytes_=500000)
    assert better.better_than(base)
    assert not base.better_than(better)


def test_storage_metrics_better_than_tie_break_by_query_latency() -> None:
    base = StorageMetrics(storage_bytes=1000000, query_latency_ms=50.0, index_count=5, is_valid=True)
    better = StorageMetrics(storage_bytes=1000000, query_latency_ms=20.0, index_count=5, is_valid=True)
    assert better.better_than(base)


def test_storage_metrics_invalid_never_beats_valid() -> None:
    valid = _baseline_metrics(bytes_=999999999)
    invalid = StorageMetrics(storage_bytes=0, query_latency_ms=0.0, index_count=0, is_valid=False)
    assert not invalid.better_than(valid)
    assert valid.better_than(invalid)


def test_storage_metrics_index_count_does_not_affect_ranking() -> None:
    base = StorageMetrics(storage_bytes=1000000, query_latency_ms=50.0, index_count=5, is_valid=True)
    same_other = StorageMetrics(storage_bytes=1000000, query_latency_ms=50.0, index_count=999, is_valid=True)
    assert not same_other.better_than(base)


def test_storage_metrics_better_than_handles_invalid_input() -> None:
    m = _baseline_metrics()
    assert not m.better_than("not metrics")  # type: ignore[arg-type]


def test_storage_types_module_infra_free() -> None:
    mod = importlib.import_module("active_skill_system.domain.storage_types")
    src = Path(mod.__file__).read_text(encoding="utf-8")
    for forbidden in ("import activegraph", "from activegraph", "import anthropic", "import openai"):
        assert forbidden not in src, f"storage_types.py must not contain '{forbidden}' (R002)"
