from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CacheNodeKind(StrEnum):
    """Kinds of nodes represented within a cache metrics hierarchy."""

    ENTRY = "entry"
    EVICTION = "eviction"
    POLICY = "policy"


@dataclass(frozen=True)
class CacheMetrics:
    """Immutable snapshot of cache performance counters.

    All fields are non-negative integers. ``hit_count`` is the primary
    comparison axis: higher values are better. The remaining fields
    (``miss_count``, ``eviction_count``, ``memory_bytes``) are inverse
    metrics, where lower values indicate better performance.
    """

    hit_count: int
    miss_count: int
    eviction_count: int
    memory_bytes: int

    def better_than(self, other: CacheMetrics) -> bool:
        """Return True if these metrics are strictly better than ``other``.

        Ranking is determined first by ``hit_count`` (higher wins) and
        then, as a tiebreaker, by ``miss_count`` (lower wins).
        """
        if self.hit_count != other.hit_count:
            return self.hit_count > other.hit_count
        return self.miss_count < other.miss_count
