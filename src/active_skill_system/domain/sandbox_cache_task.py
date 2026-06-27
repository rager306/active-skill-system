"""L1 Domain — Sandbox cache benchmark SPEC (M042 S01, D013 mini-loop).

This is the BENCHMARK a sandbox agent must satisfy — not a production domain
profile. It defines the "known answer" the project has implemented 12 times
(the MEM019 shape): a frozen CacheMetrics dataclass + a CacheNodeKind StrEnum +
a better_than ranking where the primary axis (hit_count) is INVERSE
(higher-is-better, mirroring feature_flag active_flags).

The sandbox verifier (application/sandbox_verifier.py) scores a candidate
module against this spec WITHOUT an LLM, giving objective fitness that S02/S03
use to compare models. Pure domain, stdlib only (R002/R003).

Why a cache domain: it is small, self-contained, has a natural inverse axis
(more cache hits = better), and the project has no cache_types yet — so a model
must genuinely generate it, not copy an existing module.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from enum import StrEnum


class CacheNodeKind(StrEnum):
    """Node kinds for the cache benchmark (>=3 required by the spec)."""

    ENTRY = "entry"
    EVICTION = "eviction"
    POLICY = "policy"


@dataclass(frozen=True)
class CacheMetrics:
    """Cache metrics for the benchmark.

    Required fields (all non-negative ints):
      - hit_count: cache hits (INVERSE primary axis — higher is better).
      - miss_count: cache misses.
      - eviction_count: entries evicted.
      - memory_bytes: memory in use.

    Invariants (the verifier checks these on candidate instances):
      - frozen dataclass.
      - all four fields present, int-typed, non-negative.
      - better_than: hit_count higher wins (inverse axis).
    """

    hit_count: int
    miss_count: int
    eviction_count: int
    memory_bytes: int

    def better_than(self, other: CacheMetrics) -> bool:
        """True if self is strictly better: higher hit_count, or equal hit_count
        with lower miss_count (fewer misses at the same hit level)."""
        if not isinstance(other, CacheMetrics):
            return False
        if self.hit_count > other.hit_count:
            return True
        if self.hit_count == other.hit_count:
            return self.miss_count < other.miss_count
        return False


# ── Spec contract (consumed by the verifier) ─────────────────────────────


REQUIRED_FIELDS: tuple[str, ...] = ("hit_count", "miss_count", "eviction_count", "memory_bytes")
"""Exact field names a candidate CacheMetrics must declare, in order."""


def is_valid_candidate_metrics(obj: object) -> bool:
    """Check an instantiated candidate CacheMetrics against the spec invariants.

    Pure, no I/O: used by the verifier to score the 'invariants_ok' axis.
    """
    if not isinstance(obj, object):
        return False
    # Must have all required attributes.
    for name in REQUIRED_FIELDS:
        if not hasattr(obj, name):
            return False
    # All required fields must be non-negative ints.
    for name in REQUIRED_FIELDS:
        val = getattr(obj, name)
        if isinstance(val, bool) or not isinstance(val, int) or val < 0:
            return False
    return True


def candidate_field_names(obj: object) -> tuple[str, ...]:
    """Return the candidate dataclass's field names (for structural check)."""
    try:
        return tuple(f.name for f in fields(obj))  # type: ignore[arg-type]
    except TypeError:
        return ()


__all__ = [
    "CacheMetrics",
    "CacheNodeKind",
    "REQUIRED_FIELDS",
    "is_valid_candidate_metrics",
    "candidate_field_names",
]
