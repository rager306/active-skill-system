"""L4 Composition — EvolutionEngine wiring for log domain (M030 S03)."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from typing import Any


def _build_log_evolvable() -> Any:
    from active_skill_system.adapters.log_tool_stub import LogToolStub
    from active_skill_system.application.evolvable_adapters import LogEvolvable
    tool = LogToolStub()
    def _invoker(args: dict[str, Any]) -> tuple[bool, str]:
        r = tool.invoke(args)
        return (r.success, r.text)
    return LogEvolvable(invoker=_invoker)


def _default_candidates() -> tuple:
    from active_skill_system.domain.log_types import LogNodeKind, LogTransformParams
    return (
        LogTransformParams(transform_type=LogNodeKind.LOG_TRANSFORM_FILTER, params={"level": "ERROR"}, legal=True),
        LogTransformParams(transform_type=LogNodeKind.LOG_TRANSFORM_SAMPLE, params={"rate": 0.1}, legal=True),
        LogTransformParams(transform_type=LogNodeKind.LOG_TRANSFORM_AGGREGATE, params={}, legal=True),
    )


def _build_baseline(error_rate: float) -> Any:
    from active_skill_system.domain.log_types import LogMetrics
    return LogMetrics(error_rate=error_rate, log_volume_mb=500.0, parse_time_ms=1000.0, is_valid=True)


def run_log_evolution(baseline: Any, candidates: tuple, *, dataset: dict | None = None, max_iterations: int = 5, evolvable: Any = None) -> Any:
    from active_skill_system.application.evolution_engine import EvolutionEngine
    if evolvable is None:
        evolvable = _build_log_evolvable()
    if dataset is None:
        dataset = {"baseline_metrics": _baseline_to_dict(baseline)}
    engine = EvolutionEngine()
    return engine.run(evolvable=evolvable, baseline_genome=candidates, dataset=dataset, max_iterations=max_iterations)


def _baseline_to_dict(baseline: Any) -> dict[str, Any]:
    return {"error_rate": baseline.error_rate, "log_volume_mb": baseline.log_volume_mb, "parse_time_ms": baseline.parse_time_ms, "is_valid": baseline.is_valid}


def _format_result(result: Any, baseline_error_rate: float) -> str:
    status = "PROMOTED" if result.promoted else "No improvement"
    return (
        f"{status} (iterations_used={result.iterations_used})\n"
        f"  baseline_fitness:  quality={result.baseline_fitness.quality:.4f}\n"
        f"  candidate_fitness: quality={result.candidate_fitness.quality:.4f}\n"
        f"  error_rate reduction (baseline={baseline_error_rate}): {baseline_error_rate * (1 - result.candidate_fitness.quality):.4f}\n"
        f"  reason: {result.reason}"
    )


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="active-skill-log-evolve")
    parser.add_argument("--baseline-error-rate", type=float, default=0.1)
    parser.add_argument("--max-iterations", type=int, default=5)
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    if not (0.0 <= args.baseline_error_rate <= 1.0):
        print(f"error: --baseline-error-rate must be in [0, 1] (got {args.baseline_error_rate})", flush=True)
        return 2
    if args.max_iterations < 1:
        print(f"error: --max-iterations must be >= 1 (got {args.max_iterations})", flush=True)
        return 2
    baseline = _build_baseline(args.baseline_error_rate)
    candidates = _default_candidates()
    evolvable = _build_log_evolvable()
    from active_skill_system.domain.evolvable import Evolvable
    if not isinstance(evolvable, Evolvable):
        return 1
    if not args.quiet:
        print(f"baseline: error_rate={baseline.error_rate}, volume={baseline.log_volume_mb}MB, parse={baseline.parse_time_ms}ms", flush=True)
        print(f"candidates: {len(candidates)} (kinds={[c.transform_type.value for c in candidates]})", flush=True)
        print("---", flush=True)
    result = run_log_evolution(baseline, candidates, max_iterations=args.max_iterations, evolvable=evolvable)
    print(_format_result(result, args.baseline_error_rate), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
