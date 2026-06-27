"""L3 Adapter — CompilerToolStub (M016 S02 T03).

A deterministic stub tool that simulates applying a loop transformation
to a baseline ``CompilerMetrics`` and returns the resulting metrics. Used
by the compiler optimization loop (S03) to evaluate candidate transforms
without invoking a real compiler. Deterministic, infra-free, and
registered under ``ToolCapability.COMPUTE`` so the RepairLoop can route
APPLY_TRANSFORM actions to it.

Deterministic formulas (chosen so every transform has an observable,
monotone effect on at least one metric, matching typical polyhedral
behaviour):

  TILE(size=N)         : cycles *= 1/N (cap at N=cycles), spills += ceil(N/16),
                         reg_pressure += 2*N  (live tile edges)
  INTERCHANGE          : cycles unchanged (loop order has no total cost),
                         reg_pressure -= 1     (better reuse locality)
  FUSION(fused_loops=K): cycles *= 0.7^K     (less per-iteration overhead),
                         reg_pressure += 4*K    (more live values),
                         spills -= 1           (fewer intermediate stores)
  UNROLL(factor=F)     : cycles /= F, reg_pressure += F,
                         spills -= 1           (more registers absorb work)

A missing transform_type returns the baseline unchanged (the
``MISSING_TRANSFORM`` gap case). An illegal transform
(``legal=False``) or an unknown TRANSFORM_* kind raises ``ValueError``,
which the repair loop catches and surfaces as a ``TRANSFORM_REGRESSION``
gap. Metrics are clamped to >= 0 to keep ``CompilerMetrics`` invariants.
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
from active_skill_system.domain.errors import ToolError


def _metrics_from_dict(d: dict[str, Any]) -> CompilerMetrics:
    """Construct a CompilerMetrics from a dict, validating keys/values."""
    if not isinstance(d, dict):
        raise ValueError(f"baseline must be a dict (got {type(d).__name__})")
    try:
        return CompilerMetrics(
            cycles=int(d["cycles"]),
            reg_pressure=int(d["reg_pressure"]),
            spills=int(d["spills"]),
            energy_proxy=float(d["energy_proxy"]),
            is_valid=bool(d.get("is_valid", True)),
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
    """Apply a deterministic transform to baseline metrics. Returns new CompilerMetrics."""
    cycles = baseline.cycles
    reg_pressure = baseline.reg_pressure
    spills = baseline.spills
    energy_proxy = float(baseline.energy_proxy)

    if kind is CompilerNodeKind.TRANSFORM_TILE:
        n = int(params.get("tile_size", 32))
        if n <= 0:
            raise ValueError(f"tile_size must be a positive int (got {n!r})")
        cycles = max(1, cycles // n)
        spills = spills + (n + 15) // 16  # ceil(n/16)
        reg_pressure = reg_pressure + 2 * n
    elif kind is CompilerNodeKind.TRANSFORM_INTERCHANGE:
        # Order change doesn't affect total cycles; locality reduces register pressure.
        reg_pressure = max(0, reg_pressure - 1)
    elif kind is CompilerNodeKind.TRANSFORM_FUSION:
        k = int(params.get("fused_loops", 2))
        if k <= 0:
            raise ValueError(f"fused_loops must be a positive int (got {k!r})")
        cycles = max(1, round(cycles * (0.7 ** k)))
        reg_pressure = reg_pressure + 4 * k
        spills = max(0, spills - 1)
    elif kind is CompilerNodeKind.TRANSFORM_UNROLL:
        factor = int(params.get("unroll_factor", 2))
        if factor <= 1:
            raise ValueError(f"unroll_factor must be > 1 (got {factor!r})")
        cycles = max(1, cycles // factor)
        reg_pressure = reg_pressure + factor
        spills = max(0, spills - 1)
    else:
        # Defensive: only TRANSFORM_* kinds reach here; TransformParams.__post_init__
        # already enforces this, so reaching here indicates a programming error.
        raise ToolError(f"unsupported transform kind: {kind!r}")

    return CompilerMetrics(
        cycles=cycles,
        reg_pressure=reg_pressure,
        spills=spills,
        energy_proxy=max(0.0, energy_proxy * (cycles / max(1, baseline.cycles))),
        is_valid=True,
    )


class CompilerToolStub:
    """Deterministic tool that simulates applying a loop transformation.

    capabilities: {compute}
    profile: NORMAL (deterministic, no side effects)
    invoke({'transform_type': 'transform_tile', 'params': {...}, 'baseline': {...}})
        → ToolResult(text=json.dumps(metrics), success=True)
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
            # MISSING_TRANSFORM gap case: return baseline unchanged.
            try:
                baseline = _metrics_from_dict(baseline_raw if isinstance(baseline_raw, dict) else {})
            except ValueError:
                return ToolResult(text="", evidence_id=None, success=False)
            return ToolResult(
                text=json.dumps(_metrics_to_dict(baseline), sort_keys=True),
                evidence_id="missing_transform",
                success=True,
            )

        # Validate kind is a TRANSFORM_* CompilerNodeKind.
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
            return ToolResult(
                text="",
                evidence_id=str(kind_raw),
                success=False,
            )

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
    """Serialize a CompilerMetrics to a JSON-friendly dict."""
    return {
        "cycles": m.cycles,
        "reg_pressure": m.reg_pressure,
        "spills": m.spills,
        "energy_proxy": m.energy_proxy,
        "is_valid": m.is_valid,
    }
