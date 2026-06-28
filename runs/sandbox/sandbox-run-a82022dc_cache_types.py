from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CacheNodeKind(StrEnum):
    """Kinds of nodes present within a cache metrics domain."""

    ENTRY = "entry"
    EVICTION = "eviction"
    POLICY = "policy"


@dataclass(frozen=True)
class CacheMetrics:
    """Immutable snapshot of cache operational metrics.

    ``hit_count`` is the primary comparison axis: higher is better, and it
    is the inverse of ``miss_count``. ``eviction_count`` and ``memory_bytes``
    are supporting context axes.
    """

    hit_count: int
    miss_count: int
    eviction_count: int
    memory_bytes: int

    def better_than(self, other: CacheMetrics) -> bool:
        return self.hit_count > other.hit_count or (
            self.hit_count == other.hit_count and self.miss_count < other.miss_count
        )
