"""Full-mark candidate for the cache benchmark (M042 S01 fixture).

A correct CacheMetrics + CacheNodeKind that should score 100% on every
verifier axis: structure, invariants, ranking, ruff-clean, LOC<=200.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CacheNodeKind(StrEnum):
    """Node kinds for the cache benchmark."""

    ENTRY = "entry"
    EVICTION = "eviction"
    POLICY = "policy"


@dataclass(frozen=True)
class CacheMetrics:
    """Cache metrics; hit_count is the inverse primary axis (higher is better)."""

    hit_count: int
    miss_count: int
    eviction_count: int
    memory_bytes: int

    def better_than(self, other: CacheMetrics) -> bool:
        if not isinstance(other, CacheMetrics):
            return False
        if self.hit_count > other.hit_count:
            return True
        if self.hit_count == other.hit_count:
            return self.miss_count < other.miss_count
        return False
