"""L3 Adapter — IaCToolStub (M023 S02).

Deterministic stub tool that simulates applying an IaC plan transform
to a baseline ``IaCPlanMetrics`` and returns the resulting metrics. Used
by the IaC plan optimization loop (S03) to evaluate candidate transforms
without invoking a real IaC engine. Deterministic, infra-free, registered
under ``ToolCapability.COMPUTE``.

Formulae (chosen so every transform has an observable, monotone effect
on the primary axis ``resource_count``):

  REMOVE_UNUSED       : variable_count -= 1 (cleans up the plan).
  ADD_OUTPUT          : resource_count += 1, module_count += 1 (adds
                        observability via a new output reference).
  RESTRUCTURE_DEP     : module_count //= 2 (flattens dependency graph).
  REPLAN_PROVIDERS    : resource_count //= 2, drift_score *= 0.5
                        (re-provisions with fewer providers, less drift).

A missing transform_type returns the baseline unchanged (the
``UNUSED_VARIABLE`` gap case). An illegal transform (``legal=False``) or
an unknown ``IA_TRANSFORM_*`` kind raises ``ValueError``, which the loop
catches and surfaces as a ``COST_REGRESSION`` gap. Metrics are clamped
to >= 0 to keep ``IaCPlanMetrics`` invariants.

Mirrors ``adapters/sql_tool_stub.py`` (M018 S02) but on IaC primitives
and ``adapters/compiler_tool_stub.py`` (M016 S02) — same D007 uniform
failure shape (ToolResult(success=False), no exceptions).
"""

from __future__ import annotations

import json
from typing import Any

from active_skill_system.application.ports.tool import (
    ToolCapability,
    ToolProfile,
    ToolResult,
)
from active_skill_system.domain.iac_types import IaCNodeKind, IaCPlanMetrics


def _metrics_from_dict(d: dict[str, Any]) -> IaCPlanMetrics:
    if not isinstance(d, dict):
        raise ValueError(f"baseline must be a dict (got {type(d).__name__})")
    try:
        return IaCPlanMetrics(
            resource_count=int(d["resource_count"]),
            module_count=int(d["module_count"]),
            variable_count=int(d["variable_count"]),
            drift_score=float(d["drift_score"]),
            is_valid=bool(d.get("is_valid", True)),
        )
    except KeyError as e:
        raise ValueError(f"baseline missing required key: {e.args[0]!r}") from None
    except (TypeError, ValueError) as e:
        raise ValueError(f"baseline has invalid values: {e}") from None


def _apply_transform(
    kind: IaCNodeKind,
    params: dict[str, Any],
    baseline: IaCPlanMetrics,
) -> IaCPlanMetrics:
    resource_count = baseline.resource_count
    module_count = baseline.module_count
    variable_count = baseline.variable_count
    drift_score = float(baseline.drift_score)

    if kind is IaCNodeKind.IA_TRANSFORM_REMOVE_UNUSED:
        variable_count = max(0, variable_count - 1)
    elif kind is IaCNodeKind.IA_TRANSFORM_ADD_OUTPUT:
        resource_count = resource_count + 1
        module_count = module_count + 1
    elif kind is IaCNodeKind.IA_TRANSFORM_RESTRUCTURE_DEP:
        module_count = max(0, module_count // 2)
    elif kind is IaCNodeKind.IA_TRANSFORM_REPLAN_PROVIDERS:
        resource_count = max(0, resource_count // 2)
        drift_score = max(0.0, drift_score * 0.5)
    else:
        raise ValueError(f"unsupported IaC transform kind: {kind!r}")

    return IaCPlanMetrics(
        resource_count=resource_count,
        module_count=module_count,
        variable_count=variable_count,
        drift_score=drift_score,
        is_valid=True,
    )


class IaCToolStub:
    """Deterministic tool that simulates applying an IaC plan transform."""

    name = "iac_apply_transform"
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
            kind = IaCNodeKind(kind_raw) if not isinstance(kind_raw, IaCNodeKind) else kind_raw
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


def _metrics_to_dict(m: IaCPlanMetrics) -> dict[str, Any]:
    return {
        "resource_count": m.resource_count,
        "module_count": m.module_count,
        "variable_count": m.variable_count,
        "drift_score": m.drift_score,
        "is_valid": m.is_valid,
    }
