"""L4 Composition — EvolutionEngine wiring for storage domain (M029 S03)."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from typing import Any


def _build_storage_evolvable() -> Any:
    from active_skill_system.adapters.storage_tool_stub import StorageToolStub
    from active_skill_system.application.evolvable_adapters import StorageEvolvable
    tool = StorageToolStub()
    def _invoker(args: dict[str, Any]) -> tuple[bool, str]:
        r = tool.invoke(args)
        return (r.success, r.text)
    return StorageEvolvable(invoker=_invoker)


def _default_candidates() -> tuple:
    from active_skill_system.domain.storage_types import StorageNodeKind, StorageTransformParams
    return (
        StorageTransformParams(transform_type=StorageNodeKind.STOR_TRANSFORM_COMPRESS, params={"ratio": 0.3}, legal=True),
        StorageTransformParams(transform_type=StorageNodeKind.STOR_TRANSFORM_REINDEX, params={}, legal=True),
        StorageTransformParams(transform_type=StorageNodeKind.STOR_TRANSFORM_PARTITION, params={"n_partitions": 2}, legal=True),
    )


def _build_baseline(storage_bytes: int) -> Any:
    from active_skill_system.domain.storage_types import StorageMetrics
    return StorageMetrics(storage_bytes=storage_bytes, query_latency_ms=50.0, index_count=5, is_valid=True)


def run_storage_evolution(baseline: Any, candidates: tuple, *, dataset: dict | None = None, max_iterations: int = 5, evolvable: Any = None) -> Any:
    from active_skill_system.application.evolution_engine import EvolutionEngine
    if evolvable is None:
        evolvable = _build_storage_evolvable()
    if dataset is None:
        dataset = {"baseline_metrics": _baseline_to_dict(baseline)}
    engine = EvolutionEngine()
    return engine.run(evolvable=evolvable, baseline_genome=candidates, dataset=dataset, max_iterations=max_iterations)


def _baseline_to_dict(baseline: Any) -> dict[str, Any]:
    return {"storage_bytes": baseline.storage_bytes, "query_latency_ms": baseline.query_latency_ms, "index_count": baseline.index_count, "is_valid": baseline.is_valid}


def _format_result(result: Any, baseline_bytes: int) -> str:
    status = "PROMOTED" if result.promoted else "No improvement"
    return (
        f"{status} (iterations_used={result.iterations_used})\n"
        f"  baseline_fitness:  quality={result.baseline_fitness.quality:.4f}\n"
        f"  candidate_fitness: quality={result.candidate_fitness.quality:.4f}\n"
        f"  storage reduction (baseline={baseline_bytes}): {int(baseline_bytes * (1 - result.candidate_fitness.quality))} bytes\n"
        f"  reason: {result.reason}"
    )


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="active-skill-storage-evolve")
    parser.add_argument("--baseline-bytes", type=int, default=1000000)
    parser.add_argument("--max-iterations", type=int, default=5)
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.baseline_bytes < 0:
        print(f"error: --baseline-bytes must be >= 0 (got {args.baseline_bytes})", flush=True)
        return 2
    if args.max_iterations < 1:
        print(f"error: --max-iterations must be >= 1 (got {args.max_iterations})", flush=True)
        return 2
    baseline = _build_baseline(args.baseline_bytes)
    candidates = _default_candidates()
    evolvable = _build_storage_evolvable()
    from active_skill_system.domain.evolvable import Evolvable
    if not isinstance(evolvable, Evolvable):
        return 1
    if not args.quiet:
        print(f"baseline: bytes={baseline.storage_bytes}, latency={baseline.query_latency_ms}ms, indexes={baseline.index_count}", flush=True)
        print(f"candidates: {len(candidates)} (kinds={[c.transform_type.value for c in candidates]})", flush=True)
        print("---", flush=True)
    result = run_storage_evolution(baseline, candidates, max_iterations=args.max_iterations, evolvable=evolvable)
    print(_format_result(result, args.baseline_bytes), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
