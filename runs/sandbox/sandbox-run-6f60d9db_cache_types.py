from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CacheNodeKind(StrEnum):
    """Kinds of nodes surfaced by the cache metrics domain."""

    ENTRY = "entry"
    EVICTION = "eviction"
    POLICY = "policy"


@dataclass(frozen=True)
class CacheMetrics:
    """Immutable snapshot of cache performance counters.

    All fields are non-negative ints. ``hit_count`` is the primary axis:
    higher is better (an inverse axis), so comparisons favor larger
    ``hit_count`` values first.
    """

    hit_count: int
    miss_count: int
    eviction_count: int
    memory_bytes: int

    def better_than(self, other: CacheMetrics) -> bool:
        """Return True if ``self`` dominates ``other`` on the primary axis.

        A metrics snapshot is better when its ``hit_count`` is strictly
        greater, or when ``hit_count`` is equal and ``miss_count`` is
        strictly lower.
        """
        if self.hit_count != other.hit_count:
            return self.hit_count > other.hit_count
        return self.miss_count < other.miss_count
