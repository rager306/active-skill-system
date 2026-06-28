"""L4 Composition — EvolutionEngine wiring for the IaC domain (M023 S03).

Mirrors composition/compiler_evolution.py (M017 S01) and
composition/sql_evolution.py (M018 S03). R008/R009 compliant.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from typing import Any


def _build_iac_evolvable() -> Any:
    from active_skill_system.adapters.iac_tool_stub import IaCToolStub
    from active_skill_system.application.evolvable_adapters import IaCEvolvable

    tool = IaCToolStub()

    def _invoker(args: dict[str, Any]) -> tuple[bool, str]:
        result = tool.invoke(args)
        return (result.success, result.text)

    return IaCEvolvable(invoker=_invoker)


def _default_candidates() -> tuple:
    from active_skill_system.domain.iac_types import (
        IaCNodeKind,
        IaCTransformParams,
    )

    return (
        IaCTransformParams(transform_type=IaCNodeKind.IA_TRANSFORM_REMOVE_UNUSED, params={"variable_name": "old_var"}, legal=True),
        IaCTransformParams(transform_type=IaCNodeKind.IA_TRANSFORM_ADD_OUTPUT, params={}, legal=True),
        IaCTransformParams(transform_type=IaCNodeKind.IA_TRANSFORM_RESTRUCTURE_DEP, params={}, legal=True),
    )


def _build_baseline(resources: int) -> Any:
    from active_skill_system.domain.iac_types import IaCPlanMetrics
    return IaCPlanMetrics(
        resource_count=resources, module_count=10, variable_count=20, drift_score=0.5, is_valid=True,
    )


def _load_candidate_spec(path: str) -> tuple:
    from active_skill_system.domain.iac_types import IaCNodeKind, IaCTransformParams

    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, list):
        raise ValueError("candidate-spec must be a JSON list")
    out: list[IaCTransformParams] = []
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValueError(f"candidate-spec[{i}] must be a dict")
        try:
            kind = IaCNodeKind(entry["transform_type"])  # ty:ignore[invalid-argument-type]
        except (KeyError, ValueError) as e:
            raise ValueError(f"candidate-spec[{i}].transform_type invalid: {e}") from None
        params = entry.get("params", {})
        if not isinstance(params, dict):
            raise ValueError(f"candidate-spec[{i}].params must be a dict")
        legal = bool(entry.get("legal", True))
        out.append(IaCTransformParams(transform_type=kind, params=params, legal=legal))  # ty:ignore[invalid-argument-type]
    return tuple(out)


def run_iac_evolution(
    baseline: Any,
    candidates: tuple,
    *,
    dataset: dict | None = None,
    max_iterations: int = 5,
    evolvable: Any = None,
) -> Any:
    """run_iac_evolution implementation."""
    from active_skill_system.application.evolution_engine import EvolutionEngine
    if evolvable is None:
        evolvable = _build_iac_evolvable()
    if dataset is None:
        dataset = {"baseline_metrics": _baseline_to_dict(baseline)}
    engine = EvolutionEngine()
    return engine.run(evolvable=evolvable, baseline_genome=candidates, dataset=dataset, max_iterations=max_iterations)


def _baseline_to_dict(baseline: Any) -> dict[str, Any]:
    return {
        "resource_count": baseline.resource_count,
        "module_count": baseline.module_count,
        "variable_count": baseline.variable_count,
        "drift_score": baseline.drift_score,
        "is_valid": baseline.is_valid,
    }


def _format_result(result: Any, baseline_resources: int, stage: str | None = None) -> str:
    status = "PROMOTED" if result.promoted else "No improvement"
    lines = [
        f"{status} (iterations_used={result.iterations_used})",
    ]
    if stage is not None:
        lines.append(f"  stage: {stage}")
    lines.extend([
        f"  baseline_fitness:  quality={result.baseline_fitness.quality:.4f}",
        f"  candidate_fitness: quality={result.candidate_fitness.quality:.4f}",
        f"  resource reduction (baseline={baseline_resources}): {int(baseline_resources * (1 - result.candidate_fitness.quality))} resources",
        f"  reason: {result.reason}",
    ])
    return "\n".join(lines)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="active-skill-iac-evolve")
    parser.add_argument("--baseline-resources", type=int, default=100)
    parser.add_argument("--max-iterations", type=int, default=5)
    parser.add_argument("--candidate-spec", type=str, default=None)
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--stage", type=str, default=None, choices=("cleanup", "observability", "restructure"))
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """main implementation."""
    args = _parse_args(argv)
    if args.baseline_resources < 1:
        print(f"error: --baseline-resources must be >= 1 (got {args.baseline_resources})", flush=True)
        return 2
    if args.max_iterations < 1:
        print(f"error: --max-iterations must be >= 1 (got {args.max_iterations})", flush=True)
        return 2
    baseline = _build_baseline(args.baseline_resources)
    if args.candidate_spec is not None:
        candidates = _load_candidate_spec(args.candidate_spec)
    else:
        candidates = _default_candidates()
    stage_name: str | None = None
    if args.stage is not None:
        from active_skill_system.application.iac_transformation_selector import (
            IaCStageRequirements,
            IaCTransformationSelector,
        )
        from active_skill_system.domain.iac_types import IaCNodeKind
        sel = IaCTransformationSelector()
        sel.register_stage(IaCStageRequirements(
            stage_name="cleanup",
            allowed_kinds=frozenset({IaCNodeKind.IA_TRANSFORM_REMOVE_UNUSED}),
        ))
        sel.register_stage(IaCStageRequirements(
            stage_name="observability",
            allowed_kinds=frozenset({IaCNodeKind.IA_TRANSFORM_ADD_OUTPUT}),
        ))
        sel.register_stage(IaCStageRequirements(
            stage_name="restructure",
            allowed_kinds=frozenset({IaCNodeKind.IA_TRANSFORM_RESTRUCTURE_DEP, IaCNodeKind.IA_TRANSFORM_REPLAN_PROVIDERS}),
        ))
        filtered = sel.select_for_stage(args.stage, candidates)
        candidates = filtered
        stage_name = args.stage
    evolvable = _build_iac_evolvable()
    from active_skill_system.domain.evolvable import Evolvable
    if not isinstance(evolvable, Evolvable):
        return 1
    if not args.quiet:
        print(
            f"baseline: resources={baseline.resource_count}, modules={baseline.module_count}, "
            f"vars={baseline.variable_count}, drift={baseline.drift_score}",
            flush=True,
        )
        print(
            f"candidates: {len(candidates)} (kinds={[c.transform_type.value for c in candidates]})",
            flush=True,
        )
        print("---", flush=True)
    result = run_iac_evolution(baseline, candidates, max_iterations=args.max_iterations, evolvable=evolvable)
    print(_format_result(result, args.baseline_resources, stage_name), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
