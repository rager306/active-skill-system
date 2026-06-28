from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CacheNodeKind(StrEnum):
    """Kinds of nodes represented in cache metrics."""

    ENTRY = "entry"
    EVICTION = "eviction"
    POLICY = "policy"


@dataclass(frozen=True)
class CacheMetrics:
    """Cache performance metrics.

    The hit_count is the primary axis: higher is better (inverse of misses).
    All counts are non-negative integers; memory_bytes is the resident size.
    """

    hit_count: int
    miss_count: int
    eviction_count: int
    memory_bytes: int

    def better_than(self, other: CacheMetrics) -> bool:
        return self.hit_count > other.hit_count or (
            self.hit_count == other.hit_count and self.miss_count < other.miss_count
        )
