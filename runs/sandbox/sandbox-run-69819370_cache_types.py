from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CacheNodeKind(StrEnum):
    """Categorizes nodes participating in cache metric aggregation."""

    ENTRY = "entry"
    EVICTION = "eviction"
    POLICY = "policy"


@dataclass(frozen=True)
class CacheMetrics:
    """Immutable snapshot of cache performance counters.

    All fields are non-negative integers. ``hit_count`` is the primary
    axis: higher is better (inverse metric — more hits relative to
    misses indicate a healthier cache).
    """

    hit_count: int
    miss_count: int
    eviction_count: int
    memory_bytes: int

    def better_than(self, other: CacheMetrics) -> bool:
        return self.hit_count > other.hit_count or (
            self.hit_count == other.hit_count and self.miss_count < other.miss_count
        )
