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
    """Immutable snapshot of cache performance counters.

    ``hit_count`` is the primary comparison axis: higher is better
    (the inverse axis). ``miss_count`` is the inverse axis: lower is
    better. ``eviction_count`` and ``memory_bytes`` are recorded but
    not used by the default comparison. All fields are non-negative
    integers.
    """

    hit_count: int
    miss_count: int
    eviction_count: int
    memory_bytes: int

    def better_than(self, other: CacheMetrics) -> bool:
        """Return True when this cache strictly outperforms ``other``.

        Ordering is: higher ``hit_count`` wins; if ``hit_count`` ties,
        the lower ``miss_count`` wins.
        """
        if self.hit_count != other.hit_count:
            return self.hit_count > other.hit_count
        return self.miss_count < other.miss_count
