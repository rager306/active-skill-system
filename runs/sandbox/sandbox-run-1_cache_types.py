from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CacheNodeKind(StrEnum):
    """Discriminator values for the kinds of nodes tracked in cache metrics."""

    ENTRY = "entry"
    EVICTION = "eviction"
    POLICY = "policy"


@dataclass(frozen=True)
class CacheMetrics:
    """Immutable cache performance snapshot.

    The ``hit_count`` field is the primary axis of comparison: it is the
    only field where a higher value is *better* (an inverse relationship
    to the other fields, which represent costs or resource consumption).
    """

    hit_count: int
    miss_count: int
    eviction_count: int
    memory_bytes: int

    def better_than(self, other: CacheMetrics) -> bool:
        return self.hit_count > other.hit_count or (
            self.hit_count == other.hit_count and self.miss_count < other.miss_count
        )
