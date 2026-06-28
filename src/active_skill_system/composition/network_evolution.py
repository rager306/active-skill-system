"""L4 Composition — EvolutionEngine wiring for network domain (M028 S03)."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from typing import Any


def _build_network_evolvable() -> Any:
    from active_skill_system.adapters.network_tool_stub import NetworkToolStub
    from active_skill_system.application.evolvable_adapters import NetworkEvolvable
    tool = NetworkToolStub()
    def _invoker(args: dict[str, Any]) -> tuple[bool, str]:
        r = tool.invoke(args)
        return (r.success, r.text)
    return NetworkEvolvable(invoker=_invoker)


def _default_candidates() -> tuple:
    from active_skill_system.domain.network_types import NetworkNodeKind, NetworkTransformParams
    return (
        NetworkTransformParams(transform_type=NetworkNodeKind.NET_TRANSFORM_REROUTE, params={"target": "edge1"}, legal=True),
        NetworkTransformParams(transform_type=NetworkNodeKind.NET_TRANSFORM_ADD_CACHE, params={}, legal=True),
        NetworkTransformParams(transform_type=NetworkNodeKind.NET_TRANSFORM_SWITCH_PROTOCOL, params={}, legal=True),
    )


def _build_baseline(latency: float) -> Any:
    from active_skill_system.domain.network_types import NetworkMetrics
    return NetworkMetrics(latency_ms=latency, bandwidth_mbps=100.0, packet_loss_pct=0.5, hop_count=5, is_valid=True)


def run_network_evolution(baseline: Any, candidates: tuple, *, dataset: dict | None = None, max_iterations: int = 5, evolvable: Any = None) -> Any:
    """run_network_evolution implementation."""
    from active_skill_system.application.evolution_engine import EvolutionEngine
    if evolvable is None:
        evolvable = _build_network_evolvable()
    if dataset is None:
        dataset = {"baseline_metrics": _baseline_to_dict(baseline)}
    engine = EvolutionEngine()
    return engine.run(evolvable=evolvable, baseline_genome=candidates, dataset=dataset, max_iterations=max_iterations)


def _baseline_to_dict(baseline: Any) -> dict[str, Any]:
    return {"latency_ms": baseline.latency_ms, "bandwidth_mbps": baseline.bandwidth_mbps, "packet_loss_pct": baseline.packet_loss_pct, "hop_count": baseline.hop_count, "is_valid": baseline.is_valid}


def _format_result(result: Any, baseline_latency: float) -> str:
    status = "PROMOTED" if result.promoted else "No improvement"
    return (
        f"{status} (iterations_used={result.iterations_used})\n"
        f"  baseline_fitness:  quality={result.baseline_fitness.quality:.4f}\n"
        f"  candidate_fitness: quality={result.candidate_fitness.quality:.4f}\n"
        f"  latency reduction (baseline={baseline_latency}ms): {baseline_latency * (1 - result.candidate_fitness.quality):.2f}ms\n"
        f"  reason: {result.reason}"
    )


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="active-skill-network-evolve")
    parser.add_argument("--baseline-latency", type=float, default=50.0)
    parser.add_argument("--max-iterations", type=int, default=5)
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """main implementation."""
    args = _parse_args(argv)
    if args.baseline_latency < 0:
        print(f"error: --baseline-latency must be >= 0 (got {args.baseline_latency})", flush=True)
        return 2
    if args.max_iterations < 1:
        print(f"error: --max-iterations must be >= 1 (got {args.max_iterations})", flush=True)
        return 2
    baseline = _build_baseline(args.baseline_latency)
    candidates = _default_candidates()
    evolvable = _build_network_evolvable()
    from active_skill_system.domain.evolvable import Evolvable
    if not isinstance(evolvable, Evolvable):
        return 1
    if not args.quiet:
        print(f"baseline: latency={baseline.latency_ms}ms, bandwidth={baseline.bandwidth_mbps}Mbps, loss={baseline.packet_loss_pct}%", flush=True)
        print(f"candidates: {len(candidates)} (kinds={[c.transform_type.value for c in candidates]})", flush=True)
        print("---", flush=True)
    result = run_network_evolution(baseline, candidates, max_iterations=args.max_iterations, evolvable=evolvable)
    print(_format_result(result, args.baseline_latency), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
