"""L4 Composition — EvolutionEngine wiring for the security domain (M026 S03).

Mirrors composition/compiler_evolution.py (M017) and composition/sql_evolution.py (M018).
R008/R009 compliant.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from typing import Any


def _build_security_evolvable() -> Any:
    from active_skill_system.adapters.security_tool_stub import SecurityToolStub
    from active_skill_system.application.evolvable_adapters import SecurityEvolvable

    tool = SecurityToolStub()

    def _invoker(args: dict[str, Any]) -> tuple[bool, str]:
        result = tool.invoke(args)
        return (result.success, result.text)

    return SecurityEvolvable(invoker=_invoker)


def _default_candidates() -> tuple:
    from active_skill_system.domain.security_types import (
        SecurityNodeKind,
        SecurityTransformParams,
    )

    return (
        SecurityTransformParams(transform_type=SecurityNodeKind.SEC_TRANSFORM_PATCH, params={"cve_count": 5}, legal=True),
        SecurityTransformParams(transform_type=SecurityNodeKind.SEC_TRANSFORM_ADD_CONTROL, params={"controls": 2}, legal=True),
        SecurityTransformParams(transform_type=SecurityNodeKind.SEC_TRANSFORM_ISOLATE, params={}, legal=True),
    )


def _build_baseline(threats: int) -> Any:
    from active_skill_system.domain.security_types import SecurityMetrics
    return SecurityMetrics(threat_count=threats, risk_score=7.5, coverage_ratio=0.6, exposure_time=100.0, is_valid=True)


def run_security_evolution(
    baseline: Any, candidates: tuple, *, dataset: dict | None = None, max_iterations: int = 5, evolvable: Any = None,
) -> Any:
    """run_security_evolution implementation."""
    from active_skill_system.application.evolution_engine import EvolutionEngine
    if evolvable is None:
        evolvable = _build_security_evolvable()
    if dataset is None:
        dataset = {"baseline_metrics": _baseline_to_dict(baseline)}
    engine = EvolutionEngine()
    return engine.run(evolvable=evolvable, baseline_genome=candidates, dataset=dataset, max_iterations=max_iterations)


def _baseline_to_dict(baseline: Any) -> dict[str, Any]:
    return {
        "threat_count": baseline.threat_count, "risk_score": baseline.risk_score,
        "coverage_ratio": baseline.coverage_ratio, "exposure_time": baseline.exposure_time,
        "is_valid": baseline.is_valid,
    }


def _format_result(result: Any, baseline_threats: int) -> str:
    status = "PROMOTED" if result.promoted else "No improvement"
    return (
        f"{status} (iterations_used={result.iterations_used})\n"
        f"  baseline_fitness:  quality={result.baseline_fitness.quality:.4f}\n"
        f"  candidate_fitness: quality={result.candidate_fitness.quality:.4f}\n"
        f"  threat reduction (baseline={baseline_threats}): "
        f"{int(baseline_threats * (1 - result.candidate_fitness.quality))} threats\n"
        f"  reason: {result.reason}"
    )


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="active-skill-security-evolve")
    parser.add_argument("--baseline-threats", type=int, default=50)
    parser.add_argument("--max-iterations", type=int, default=5)
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """main implementation."""
    args = _parse_args(argv)
    if args.baseline_threats < 1:
        print(f"error: --baseline-threats must be >= 1 (got {args.baseline_threats})", flush=True)
        return 2
    if args.max_iterations < 1:
        print(f"error: --max-iterations must be >= 1 (got {args.max_iterations})", flush=True)
        return 2
    baseline = _build_baseline(args.baseline_threats)
    candidates = _default_candidates()
    evolvable = _build_security_evolvable()
    from active_skill_system.domain.evolvable import Evolvable
    if not isinstance(evolvable, Evolvable):
        return 1
    if not args.quiet:
        print(f"baseline: threats={baseline.threat_count}, risk={baseline.risk_score}, coverage={baseline.coverage_ratio}", flush=True)
        print(f"candidates: {len(candidates)} (kinds={[c.transform_type.value for c in candidates]})", flush=True)
        print("---", flush=True)
    result = run_security_evolution(baseline, candidates, max_iterations=args.max_iterations, evolvable=evolvable)
    print(_format_result(result, args.baseline_threats), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
