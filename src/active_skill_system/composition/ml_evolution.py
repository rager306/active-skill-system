"""L4 Composition — EvolutionEngine wiring for ML domain (M027 S03)."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from typing import Any


def _build_ml_evolvable() -> Any:
    from active_skill_system.adapters.ml_tool_stub import MLToolStub
    from active_skill_system.application.evolvable_adapters import MLEvolvable
    tool = MLToolStub()
    def _invoker(args: dict[str, Any]) -> tuple[bool, str]:
        result = tool.invoke(args)
        return (result.success, result.text)
    return MLEvolvable(invoker=_invoker)


def _default_candidates() -> tuple:
    from active_skill_system.domain.ml_types import MLNodeKind, MLTransformParams
    return (
        MLTransformParams(transform_type=MLNodeKind.ML_TRANSFORM_ADJUST_LR, params={"lr_factor": 0.5}, legal=True),
        MLTransformParams(transform_type=MLNodeKind.ML_TRANSFORM_ADD_REGULARIZATION, params={}, legal=True),
        MLTransformParams(transform_type=MLNodeKind.ML_TRANSFORM_SWITCH_OPTIMIZER, params={}, legal=True),
    )


def _build_baseline(loss: float) -> Any:
    from active_skill_system.domain.ml_types import MLMetrics
    return MLMetrics(loss=loss, accuracy=0.85, epochs=100, convergence_time=3600.0, is_valid=True)


def run_ml_evolution(baseline: Any, candidates: tuple, *, dataset: dict | None = None, max_iterations: int = 5, evolvable: Any = None) -> Any:
    from active_skill_system.application.evolution_engine import EvolutionEngine
    if evolvable is None:
        evolvable = _build_ml_evolvable()
    if dataset is None:
        dataset = {"baseline_metrics": _baseline_to_dict(baseline)}
    engine = EvolutionEngine()
    return engine.run(evolvable=evolvable, baseline_genome=candidates, dataset=dataset, max_iterations=max_iterations)


def _baseline_to_dict(baseline: Any) -> dict[str, Any]:
    return {"loss": baseline.loss, "accuracy": baseline.accuracy, "epochs": baseline.epochs, "convergence_time": baseline.convergence_time, "is_valid": baseline.is_valid}


def _format_result(result: Any, baseline_loss: float) -> str:
    status = "PROMOTED" if result.promoted else "No improvement"
    return (
        f"{status} (iterations_used={result.iterations_used})\n"
        f"  baseline_fitness:  quality={result.baseline_fitness.quality:.4f}\n"
        f"  candidate_fitness: quality={result.candidate_fitness.quality:.4f}\n"
        f"  loss reduction (baseline={baseline_loss}): {baseline_loss * (1 - result.candidate_fitness.quality):.4f}\n"
        f"  reason: {result.reason}"
    )


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="active-skill-ml-evolve")
    parser.add_argument("--baseline-loss", type=float, default=0.5)
    parser.add_argument("--max-iterations", type=int, default=5)
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.baseline_loss < 0:
        print(f"error: --baseline-loss must be >= 0 (got {args.baseline_loss})", flush=True)
        return 2
    if args.max_iterations < 1:
        print(f"error: --max-iterations must be >= 1 (got {args.max_iterations})", flush=True)
        return 2
    baseline = _build_baseline(args.baseline_loss)
    candidates = _default_candidates()
    evolvable = _build_ml_evolvable()
    from active_skill_system.domain.evolvable import Evolvable
    if not isinstance(evolvable, Evolvable):
        return 1
    if not args.quiet:
        print(f"baseline: loss={baseline.loss}, accuracy={baseline.accuracy}, epochs={baseline.epochs}", flush=True)
        print(f"candidates: {len(candidates)} (kinds={[c.transform_type.value for c in candidates]})", flush=True)
        print("---", flush=True)
    result = run_ml_evolution(baseline, candidates, max_iterations=args.max_iterations, evolvable=evolvable)
    print(_format_result(result, args.baseline_loss), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
