from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CacheNodeKind(StrEnum):
    """Kinds of nodes tracked in the cache metrics domain."""

    ENTRY = "entry"
    EVICTION = "eviction"
    POLICY = "policy"


@dataclass(frozen=True)
class CacheMetrics:
    """Immutable cache metrics snapshot.

    Attributes:
        hit_count: Number of cache hits. This is the primary axis of
            comparison: a higher hit_count is better (inverse metric).
        miss_count: Number of cache misses.
        eviction_count: Number of evicted entries.
        memory_bytes: Memory usage in bytes.
    """

    hit_count: int
    miss_count: int
    eviction_count: int
    memory_bytes: int

    def better_than(self, other: CacheMetrics) -> bool:
        """Return True if this snapshot outperforms ``other``.

        Comparison is driven by ``hit_count`` (the primary axis, where
        higher is better / inverse). On a tie, the snapshot with the
        fewer misses wins.
        """
        if self.hit_count != other.hit_count:
            return self.hit_count > other.hit_count
        return self.miss_count < other.miss_count
