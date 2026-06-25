"""L1 Domain - Compiler optimization types (M016 S01).

Domain profile for compiler loop optimization (ComPilot-like). These types
extend the generic Task Graph with compiler-specific node/edge kinds for
representing loop nests, data dependencies, and transformation schedules.

Pure domain. NO I/O, NO infrastructure imports (R002). stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class CompilerNodeKind(StrEnum):
    """Node types for compiler optimization domain."""

    LOOP_NEST = "loop_nest"
    STATEMENT = "statement"
    ARRAY_REF = "array_ref"
    TRANSFORM_TILE = "transform_tile"
    TRANSFORM_INTERCHANGE = "transform_interchange"
    TRANSFORM_FUSION = "transform_fusion"
    TRANSFORM_UNROLL = "transform_unroll"


class CompilerEdgeKind(StrEnum):
    """Edge types for compiler dependency analysis."""

    FLOW_DEP = "flow_dep"  # true dependence (read-after-write)
    ANTI_DEP = "anti_dep"  # anti dependence (write-after-read)
    OUTPUT_DEP = "output_dep"  # output dependence (write-after-write)
    LEGAL_TRANSFORM = "legal_transform"  # transformation is legal given deps
    ENABLES = "enables"  # one transform enables another


@dataclass(frozen=True)
class DependencyDistance:
    """A data dependence between two loop indices with distance vector.

    Carries:
      - source: the source statement/loop index (e.g. "i").
      - target: the target statement/loop index (e.g. "j").
      - dep_type: one of CompilerEdgeKind (FLOW_DEP, ANTI_DEP, OUTPUT_DEP).
      - distance: tuple of ints representing the dependence distance
        (e.g. (1, 0) means source is 1 iteration before target in dim 0).
    """

    source: str
    target: str
    dep_type: CompilerEdgeKind
    distance: tuple[int, ...]

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.source, str) or not self.source.strip():
            errors.append(f"source must be non-empty (got {self.source!r})")
        if not isinstance(self.target, str) or not self.target.strip():
            errors.append(f"target must be non-empty (got {self.target!r})")
        if self.dep_type not in (CompilerEdgeKind.FLOW_DEP, CompilerEdgeKind.ANTI_DEP, CompilerEdgeKind.OUTPUT_DEP):
            errors.append(
                f"dep_type must be FLOW_DEP, ANTI_DEP, or OUTPUT_DEP (got {self.dep_type!r})"
            )
        if not isinstance(self.distance, tuple) or len(self.distance) == 0:
            errors.append(f"distance must be a non-empty tuple (got {self.distance!r})")
        if errors:
            raise ValueError("DependencyDistance invariant violation: " + "; ".join(errors))

    def is_loop_carried(self) -> bool:
        """True if any distance component is non-zero (loop-carried dependence)."""
        return any(d != 0 for d in self.distance)


@dataclass(frozen=True)
class TransformParams:
    """Parameters for a specific loop transformation.

    Carries:
      - transform_type: one of CompilerNodeKind (TRANSFORM_TILE, etc.).
      - params: transformation parameters (e.g. {"tile_size": 32}).
      - legal: whether the transformation is legal given current dependencies.
    """

    transform_type: CompilerNodeKind
    params: dict[str, Any]
    legal: bool = True

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.transform_type, CompilerNodeKind):
            errors.append(f"transform_type must be a CompilerNodeKind (got {type(self.transform_type).__name__})")
        transform_kinds = {
            CompilerNodeKind.TRANSFORM_TILE,
            CompilerNodeKind.TRANSFORM_INTERCHANGE,
            CompilerNodeKind.TRANSFORM_FUSION,
            CompilerNodeKind.TRANSFORM_UNROLL,
        }
        if self.transform_type not in transform_kinds:
            errors.append(
                f"transform_type must be a TRANSFORM_* kind (got {self.transform_type!r})"
            )
        if not isinstance(self.params, dict):
            errors.append(f"params must be a dict (got {type(self.params).__name__})")
        if not isinstance(self.legal, bool):
            errors.append(f"legal must be a bool (got {type(self.legal).__name__})")
        if errors:
            raise ValueError("TransformParams invariant violation: " + "; ".join(errors))


# ── compiler metrics (M016 S02) ───────────────────────────────────────────


@dataclass(frozen=True)
class CompilerMetrics:
    """Measured compiler metrics after applying (or not) a transformation.

    Carries:
      - cycles: total executed cycles (int, >= 0; lower = better).
      - reg_pressure: peak live register count (int, >= 0; lower = better).
      - spills: number of register spills to memory (int, >= 0; lower = better).
      - energy_proxy: rough energy estimate (float, >= 0.0; lower = better).
      - is_valid: False if the schedule is invalid (e.g. illegal transform
        was applied and produced an unschedulable loop).
    """

    cycles: int
    reg_pressure: int
    spills: int
    energy_proxy: float
    is_valid: bool = True

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.cycles, int) or isinstance(self.cycles, bool) or self.cycles < 0:
            errors.append(f"cycles must be a non-negative int (got {self.cycles!r})")
        if not isinstance(self.reg_pressure, int) or isinstance(self.reg_pressure, bool) or self.reg_pressure < 0:
            errors.append(f"reg_pressure must be a non-negative int (got {self.reg_pressure!r})")
        if not isinstance(self.spills, int) or isinstance(self.spills, bool) or self.spills < 0:
            errors.append(f"spills must be a non-negative int (got {self.spills!r})")
        if not isinstance(self.energy_proxy, (int, float)) or isinstance(self.energy_proxy, bool) or float(self.energy_proxy) < 0.0:
            errors.append(f"energy_proxy must be a non-negative number (got {self.energy_proxy!r})")
        if not isinstance(self.is_valid, bool):
            errors.append(f"is_valid must be a bool (got {type(self.is_valid).__name__})")
        if errors:
            raise ValueError("CompilerMetrics invariant violation: " + "; ".join(errors))

    def better_than(self, other: CompilerMetrics) -> bool:
        """True if this metrics is strictly better than other.

        An invalid schedule is never better than a valid one. Among valid
        schedules, better means strictly lower cycles, OR same cycles with
        strictly lower spills, OR same cycles+spills with strictly lower
        energy_proxy. reg_pressure is reported but not in the ranking
        (carried as a side observation for diagnostics).
        """
        if not isinstance(other, CompilerMetrics):
            return False
        if not self.is_valid and other.is_valid:
            return False
        if self.is_valid and not other.is_valid:
            return True
        if self.cycles < other.cycles:
            return True
        if self.cycles == other.cycles:
            if self.spills < other.spills:
                return True
            if self.spills == other.spills and float(self.energy_proxy) < float(other.energy_proxy):
                return True
        return False


# ── compiler gap & action taxonomy (M016 S02) ────────────────────────────


class CompilerGapClass(StrEnum):
    """Classification of compiler optimization gaps.

    Mirrors the reasoning-domain GapClass taxonomy (concept.md §7) but
    scoped to the compiler profile. The RepairPolicy maps each gap class
    to a CompilerActionType.
    """

    MISSING_TRANSFORM = "missing_transform"  # no candidate transform tried yet
    TRANSFORM_REGRESSION = "transform_regression"  # candidate transform hurt metrics
    LOOP_CARRIED_DEP = "loop_carried_dep"  # dependency blocks naive vectorization
    REGISTER_SPILL = "register_spill"  # transform caused register pressure / spills
    PERF_REGRESSION = "perf_regression"  # overall cycles/energy regressed


class CompilerActionType(StrEnum):
    """Type of repair action for a compiler gap."""

    APPLY_TRANSFORM = "apply_transform"  # try the candidate transform
    REVERT_TRANSFORM = "revert_transform"  # undo the last transform
    PICK_ALTERNATIVE = "pick_alternative"  # choose a different transform from the space
    LOWERING_REPLAN = "lowering_replan"  # replan the lowering strategy
