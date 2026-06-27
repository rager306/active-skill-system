"""Deliberately BROKEN candidate for the cache benchmark (M042 S01 fixture).

Fails multiple verifier axes: wrong field names (missing memory_bytes, has
extra size_bytes), no CacheNodeKind enum, non-frozen dataclass, and an
incorrect better_than (treats hit_count as lower-is-better). Used to prove the
verifier detects defects.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CacheMetrics:
    hit_count: int
    miss_count: int
    eviction_count: int
    size_bytes: int  # wrong name — spec requires memory_bytes

    def better_than(self, other: CacheMetrics) -> bool:
        # WRONG: treats hit_count as lower-is-better (spec is inverse/higher).
        return self.hit_count < other.hit_count
