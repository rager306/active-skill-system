"""L3 Adapter — PolyhedralCostModel (M019 S02).

A more realistic cost model than ``CompilerToolStub`` (M016 S02) for the
loop transform primitives (TILE/INTERCHANGE/FUSION/UNROLL). Uses
analytical models reflecting actual cache hierarchy, vectorization, and
loop fusion effects observed in real polyhedral compilers:

  TILE(size=N)        : cycles //= max(1, N) (more conservative than
                       pedagogical), cache_misses -= 5*N (tiles fit in L1,
                       clamped to >= 0), vectorization_factor += 0.2
                       (tiling enables vectorization, capped at 1.0).
  INTERCHANGE         : cycles unchanged, cache_misses //= max(1, 2)
                       (better locality), reg_pressure -= 1 (clamped).
  FUSION(fused_loops=K): cycles = round(cycles * 0.6**K) (less aggressive
                       than pedagogical 0.7), vectorization_factor *= 0.7
                       (fusion may inhibit vectorization).
  UNROLL(factor=F)    : cycles //= max(1, F), vectorization_factor += 0.3
                       (unroll enables vectorization, capped at 1.0).

A missing transform_type returns the baseline unchanged (the
``MISSING_TRANSFORM`` gap case). An illegal transform or unknown kind
returns ToolResult(success=False) — same D007 uniform failure shape as
CompilerToolStub.

Drop-in replacement for CompilerToolStub: same name+capabilities surface
(``compiler_apply_transform``, {COMPUTE}) so composition/compiler_evolution.py
can route to either via ToolRegistry.get_by_capability.
"""

from __future__ import annotations

import json
from typing import Any

from active_skill_system.application.ports.tool import (
    ToolCapability,
    ToolProfile,
    ToolResult,
)
from active_skill_system.domain.compiler_types import (
    CompilerMetrics,
    CompilerNodeKind,
)


def _metrics_from_dict(d: dict[str, Any]) -> CompilerMetrics:
    if not isinstance(d, dict):
        raise ValueError(f"baseline must be a dict (got {type(d).__name__})")
    try:
        return CompilerMetrics(
            cycles=int(d["cycles"]),
            reg_pressure=int(d["reg_pressure"]),
            spills=int(d["spills"]),
            energy_proxy=float(d["energy_proxy"]),
            is_valid=bool(d.get("is_valid", True)),
            cache_misses=int(d.get("cache_misses", 0)),
            vectorization_factor=float(d.get("vectorization_factor", 0.0)),
        )
    except KeyError as e:
        raise ValueError(f"baseline missing required key: {e.args[0]!r}") from None
    except (TypeError, ValueError) as e:
        raise ValueError(f"baseline has invalid values: {e}") from None


def _apply_transform(
    kind: CompilerNodeKind,
    params: dict[str, Any],
    baseline: CompilerMetrics,
) -> CompilerMetrics:
    """Apply a polyhedral cost model transform to baseline metrics."""
    cycles = baseline.cycles
    reg_pressure = baseline.reg_pressure
    spills = baseline.spills
    energy_proxy = float(baseline.energy_proxy)
    cache_misses = baseline.cache_misses
    vectorization_factor = float(baseline.vectorization_factor)

    if kind is CompilerNodeKind.TRANSFORM_TILE:
        n = int(params.get("tile_size", 32))
        if n <= 0:
            raise ValueError(f"tile_size must be a positive int (got {n!r})")
        cycles = max(1, cycles // n)
        # Tiling puts the working set in L1; cache misses drop per tile.
        cache_misses = max(0, cache_misses - 5 * n)
        # Tiling enables vectorization on the inner loop.
        vectorization_factor = min(1.0, vectorization_factor + 0.2)
        spills = spills + (n + 15) // 16
        reg_pressure = reg_pressure + 2 * n
    elif kind is CompilerNodeKind.TRANSFORM_INTERCHANGE:
        # Interchange improves cache locality for column-major access.
        cache_misses = max(0, cache_misses // 2)
        reg_pressure = max(0, reg_pressure - 1)
    elif kind is CompilerNodeKind.TRANSFORM_FUSION:
        k = int(params.get("fused_loops", 2))
        if k <= 0:
            raise ValueError(f"fused_loops must be a positive int (got {k!r})")
        cycles = max(1, round(cycles * (0.6 ** k)))
        # Fusion may inhibit vectorization if the fused loop is too long.
        vectorization_factor = vectorization_factor * 0.7
        reg_pressure = reg_pressure + 4 * k
        spills = max(0, spills - 1)
    elif kind is CompilerNodeKind.TRANSFORM_UNROLL:
        factor = int(params.get("unroll_factor", 2))
        if factor <= 1:
            raise ValueError(f"unroll_factor must be > 1 (got {factor!r})")
        cycles = max(1, cycles // factor)
        # Unrolling enables vectorization on the unrolled body.
        vectorization_factor = min(1.0, vectorization_factor + 0.3)
        reg_pressure = reg_pressure + factor
        spills = max(0, spills - 1)
    else:
        raise ValueError(f"unsupported transform kind: {kind!r}")

    return CompilerMetrics(
        cycles=cycles,
        reg_pressure=reg_pressure,
        spills=spills,
        energy_proxy=max(0.0, energy_proxy * (cycles / max(1, baseline.cycles))),
        is_valid=True,
        cache_misses=cache_misses,
        vectorization_factor=vectorization_factor,
    )


class PolyhedralCostModel:
    """Realistic cost model for loop transformations.

    capabilities: {compute}
    profile: NORMAL (deterministic, no side effects)
    invoke({"transform_type": "transform_tile", "params": {...}, "baseline": {...}})
        -> ToolResult(text=json.dumps(metrics), success=True)
    """

    name = "compiler_apply_transform"
    capabilities = frozenset({ToolCapability.COMPUTE})
    profile = ToolProfile.NORMAL

    def invoke(self, args: dict[str, Any]) -> ToolResult:
        if not isinstance(args, dict):
            return ToolResult(text="", evidence_id=None, success=False)

        kind_raw = args.get("transform_type")
        params_raw = args.get("params", {})
        baseline_raw = args.get("baseline")

        if kind_raw is None:
            try:
                baseline = _metrics_from_dict(baseline_raw if isinstance(baseline_raw, dict) else {})
            except ValueError:
                return ToolResult(text="", evidence_id=None, success=False)
            return ToolResult(
                text=json.dumps(_metrics_to_dict(baseline), sort_keys=True),
                evidence_id="missing_transform",
                success=True,
            )

        try:
            kind = CompilerNodeKind(kind_raw) if not isinstance(kind_raw, CompilerNodeKind) else kind_raw
        except ValueError:
            return ToolResult(text="", evidence_id=str(kind_raw), success=False)

        try:
            baseline = _metrics_from_dict(baseline_raw if isinstance(baseline_raw, dict) else {})
        except ValueError:
            return ToolResult(text="", evidence_id=str(kind_raw), success=False)

        if not isinstance(params_raw, dict):
            return ToolResult(text="", evidence_id=str(kind_raw), success=False)

        if params_raw.get("legal", True) is False:
            return ToolResult(text="", evidence_id=str(kind_raw), success=False)

        try:
            new_metrics = _apply_transform(kind, params_raw, baseline)
        except ValueError:
            return ToolResult(text="", evidence_id=str(kind_raw), success=False)

        return ToolResult(
            text=json.dumps(_metrics_to_dict(new_metrics), sort_keys=True),
            evidence_id=str(kind_raw),
            success=True,
        )


def _metrics_to_dict(m: CompilerMetrics) -> dict[str, Any]:
    return {
        "cycles": m.cycles,
        "reg_pressure": m.reg_pressure,
        "spills": m.spills,
        "energy_proxy": m.energy_proxy,
        "is_valid": m.is_valid,
        "cache_misses": m.cache_misses,
        "vectorization_factor": m.vectorization_factor,
    }
