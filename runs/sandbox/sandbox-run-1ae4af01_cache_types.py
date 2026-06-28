from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CacheNodeKind(StrEnum):
    """Enumeration of cache node kinds used to categorize metrics sources."""

    ENTRY = "entry"
    EVICTION = "eviction"
    POLICY = "policy"


@dataclass(frozen=True)
class CacheMetrics:
    """Immutable cache performance metrics.

    The primary axis is ``hit_count``: higher values indicate better cache
    performance (an inverse relationship to cache misses). All fields are
    non-negative integers.

    Attributes:
        hit_count: Number of cache hits (higher = better, inverse).
        miss_count: Number of cache misses.
        eviction_count: Number of cache evictions.
        memory_bytes: Memory footprint of the cache in bytes.
    """

    hit_count: int
    miss_count: int
    eviction_count: int
    memory_bytes: int

    def better_than(self, other: CacheMetrics) -> bool:
        """Return True if this cache's metrics are better than ``other``'s.

        Comparison rule: a strictly greater ``hit_count`` wins; ties on
        ``hit_count`` are broken by a strictly lower ``miss_count``.
        """
        if self.hit_count != other.hit_count:
            return self.hit_count > other.hit_count
        return self.miss_count < other.miss_count
