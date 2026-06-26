"""L1 Domain — Feature flag domain types (M036 S01).

Domain profile for feature flag optimization (cleaning stale flags,
expanding rollout, reducing blast radius). Primary fitness axis:
active_flags is INVERSE (more is better — more flags actively rolled out
means the flag system is in active use rather than abandoned).

Mirrors the shared shape (compiler_types.py, sql_types.py, iac_types.py,
network_types.py, etc). Pure domain, R002 preserved.

Note on primary axis semantics: active_flags is INVERSE — more is better.
Other domains (compiler cycles, SQL rows_examined, IaC resource_count,
network latency) are lower=better. The feature flag domain is one of
the few where higher=better makes sense (more flags actively used = more
value extracted from the flag system).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class FeatureNodeKind(StrEnum):
    FLAG = "flag"
    ROLLOUT = "rollout"
    SEGMENT = "segment"
    VARIANT = "variant"
    FLAG_TRANSFORM_REMOVE_STALE = "flag_transform_remove_stale"
    FLAG_TRANSFORM_EXPAND_ROLLOUT = "flag_transform_expand_rollout"
    FLAG_TRANSFORM_REDUCE_BLAST = "flag_transform_reduce_blast"
    FLAG_TRANSFORM_SPLIT_VARIANT = "flag_transform_split_variant"


class FeatureGapClass(StrEnum):
    STALE_FLAG = "stale_flag"
    LOW_ROLLOUT = "low_rollout"
    HIGH_BLAST_RADIUS = "high_blast_radius"
    MISSING_SEGMENT = "missing_segment"
    NO_VARIATION = "no_variation"


class FeatureFlagActionType(StrEnum):
    REMOVE_STALE = "remove_stale"
    EXPAND_ROLLOUT = "expand_rollout"
    REDUCE_BLAST = "reduce_blast"
    SPLIT_VARIANT = "split_variant"


@dataclass(frozen=True)
class FeatureFlagTransformParams:
    transform_type: FeatureNodeKind
    params: dict[str, Any]
    legal: bool = True

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.transform_type, FeatureNodeKind):
            errors.append(f"transform_type must be a FeatureNodeKind (got {type(self.transform_type).__name__})")
        transform_kinds = {
            FeatureNodeKind.FLAG_TRANSFORM_REMOVE_STALE,
            FeatureNodeKind.FLAG_TRANSFORM_EXPAND_ROLLOUT,
            FeatureNodeKind.FLAG_TRANSFORM_REDUCE_BLAST,
            FeatureNodeKind.FLAG_TRANSFORM_SPLIT_VARIANT,
        }
        if self.transform_type not in transform_kinds:
            errors.append(f"transform_type must be a FLAG_TRANSFORM_* kind (got {self.transform_type!r})")
        if not isinstance(self.params, dict):
            errors.append(f"params must be a dict (got {type(self.params).__name__})")
        if not isinstance(self.legal, bool):
            errors.append(f"legal must be a bool (got {type(self.legal).__name__})")
        if errors:
            raise ValueError("FeatureFlagTransformParams invariant violation: " + "; ".join(errors))


@dataclass(frozen=True)
class FeatureFlagMetrics:
    """Measured feature flag metrics.

    Carries:
      - active_flags: number of flags actively rolled out (int, >= 0; INVERSE — higher = better).
      - stale_flags: number of flags inactive for > N days (int, >= 0; lower = better).
      - rollout_coverage: fraction of users exposed to at least one flag (float in [0, 1]; higher = better — INVERSE).
      - blast_radius: max number of users any single flag could affect (int, >= 0; lower = better).
      - is_valid: False if the flag system is invalid.
    """

    active_flags: int
    stale_flags: int
    rollout_coverage: float
    blast_radius: int
    is_valid: bool = True

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.active_flags, int) or isinstance(self.active_flags, bool) or self.active_flags < 0:
            errors.append(f"active_flags must be a non-negative int (got {self.active_flags!r})")
        if not isinstance(self.stale_flags, int) or isinstance(self.stale_flags, bool) or self.stale_flags < 0:
            errors.append(f"stale_flags must be a non-negative int (got {self.stale_flags!r})")
        if not isinstance(self.rollout_coverage, (int, float)) or isinstance(self.rollout_coverage, bool) or not (0.0 <= float(self.rollout_coverage) <= 1.0):
            errors.append(f"rollout_coverage must be in [0.0, 1.0] (got {self.rollout_coverage!r})")
        if not isinstance(self.blast_radius, int) or isinstance(self.blast_radius, bool) or self.blast_radius < 0:
            errors.append(f"blast_radius must be a non-negative int (got {self.blast_radius!r})")
        if not isinstance(self.is_valid, bool):
            errors.append(f"is_valid must be a bool (got {type(self.is_valid).__name__})")
        if errors:
            raise ValueError("FeatureFlagMetrics invariant violation: " + "; ".join(errors))

    def better_than(self, other: FeatureFlagMetrics) -> bool:
        """True if strictly better.

        active_flags is INVERSE (higher = better). Primary axis.
        rollout_coverage is INVERSE (higher = better). Tie-breaker.
        stale_flags is lower = better. Secondary tie.
        blast_radius is lower = better. Final tie.
        """
        if not isinstance(other, FeatureFlagMetrics):
            return False
        if not self.is_valid and other.is_valid:
            return False
        if self.is_valid and not other.is_valid:
            return True
        if self.active_flags > other.active_flags:
            return True
        if self.active_flags == other.active_flags:
            if float(self.rollout_coverage) > float(other.rollout_coverage):
                return True
            if (
                float(self.rollout_coverage) == float(other.rollout_coverage)
                and self.stale_flags < other.stale_flags
            ):
                return True
            if (
                float(self.rollout_coverage) == float(other.rollout_coverage)
                and self.stale_flags == other.stale_flags
                and self.blast_radius < other.blast_radius
            ):
                return True
        return False
