from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CacheNodeKind(StrEnum):
    """Kinds of cache nodes that participate in a cache topology."""

    ENTRY = "entry"
    EVICTION = "eviction"
    POLICY = "policy"


@dataclass(frozen=True)
class CacheMetrics:
    """Cache performance metrics snapshot.

    The ``hit_count`` field is the primary axis: higher is better. It is
    the inverse of ``miss_count`` (which is the secondary axis: lower is
    better).
    """

    hit_count: int
    miss_count: int
    eviction_count: int
    memory_bytes: int

    def better_than(self, other: CacheMetrics) -> bool:
        """Return True if self dominates other on the primary/secondary axes."""
        return self.hit_count > other.hit_count or (
            self.hit_count == other.hit_count and self.miss_count < other.miss_count
        )
