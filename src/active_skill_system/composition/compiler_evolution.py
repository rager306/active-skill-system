"""L4 Composition — EvolutionEngine wiring for the compiler domain (M017 S01).

Wires the offline ``EvolutionEngine`` (L2 application) with the
``TransformationGenomeEvolvable`` (L2 application) and the real
``CompilerToolStub`` (L3 adapter) so the offline evolution loop can run
end-to-end on compiler-domain genomes. Closes the M016 S03 T03 deviation:
production wiring is the L4 composition-layer responsibility — L2 stays
free of L3 imports (R002 / R007, enforced by ``uv run lint-imports``).

No activegraph. No LLM. No network. Pure deterministic offline evolution
over pedagogical ``CompilerMetrics`` produced by the local
``CompilerToolStub``.

Composition shape mirrors ``composition/diligence.py``:

  - Module-level imports: only stdlib + ``argparse``. No ``activegraph``,
    no ``anthropic``, no ``openai``, no L3 adapters. (R008 / R009.)
  - All heavy imports (``CompilerToolStub``, ``EvolutionEngine``,
    ``TransformationGenomeEvolvable``, ``CompilerMetrics``, ``TransformParams``,
    ``CompilerNodeKind``) are deferred into ``_build_*`` helpers / ``main()``.
  - Importing this module is side-effect free: ``uv run python -c
    "import active_skill_system.composition.compiler_evolution"`` exits 0
    and produces no stdout / stderr output.

Usage:

    uv run python -m active_skill_system.composition.compiler_evolution \\
        --baseline-cycles 1000 --max-iterations 3

    # Or with a custom candidate spec:
    uv run python -m active_skill_system.composition.compiler_evolution \\
        --candidate-spec ./my_candidates.json
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from typing import Any

# Module-level imports are intentionally restricted to stdlib + argparse.
# All domain / application / adapter types are imported inside _build_*
# helpers and main() so the module can be imported without side-effects
# (R008) and without forcing heavy deps to load (R009).


# ── Helpers (lazy infra imports) ─────────────────────────────────────────


def _build_transformation_evolvable() -> Any:
    """Build a fully-wired :class:`TransformationGenomeEvolvable`.

    Lazy imports: CompilerToolStub (L3 adapter) and
    TransformationGenomeEvolvable (L2 application) are imported only when
    this helper is called. The returned evolvable closes the M016 S03 T03
    deviation: production wiring is composition-layer (L4) responsibility,
    not an L2 default.
    """
    from active_skill_system.adapters.compiler_tool_stub import CompilerToolStub
    from active_skill_system.application.evolvable_adapters import (
        TransformationGenomeEvolvable,
    )

    tool = CompilerToolStub()

    def _invoker(args: dict[str, Any]) -> tuple[bool, str]:
        # Adapter-bridge seam: CompilerToolStub.invoke(args) returns a
        # ToolResult; the evolvable contract is (success: bool, text: str).
        result = tool.invoke(args)
        return (result.success, result.text)

    return TransformationGenomeEvolvable(invoker=_invoker)


def _default_candidates() -> tuple:
    """Pedagogical 3-candidate set: TILE / UNROLL / FUSION with moderate sizes.

    Mirrors the test fixture set used in M016 S03 T03 + UAT-S03-e2e so the
    default CLI behaviour is predictable and reproducible.
    """
    from active_skill_system.domain.compiler_types import CompilerNodeKind, TransformParams

    return (
        TransformParams(
            transform_type=CompilerNodeKind.TRANSFORM_TILE,
            params={"tile_size": 10},
            legal=True,
        ),
        TransformParams(
            transform_type=CompilerNodeKind.TRANSFORM_UNROLL,
            params={"unroll_factor": 4},
            legal=True,
        ),
        TransformParams(
            transform_type=CompilerNodeKind.TRANSFORM_FUSION,
            params={"fused_loops": 2},
            legal=True,
        ),
    )


def _build_baseline(cycles: int) -> Any:
    """Build a deterministic pedagogical baseline :class:`CompilerMetrics`."""
    from active_skill_system.domain.compiler_types import CompilerMetrics

    return CompilerMetrics(
        cycles=cycles,
        reg_pressure=10,
        spills=2,
        energy_proxy=1.0,
        is_valid=True,
    )


def _load_candidate_spec(path: str) -> tuple:
    """Load candidate TransformParams from a local JSON file.

    Schema (list of objects)::
        [
          {"transform_type": "transform_tile",      "params": {"tile_size": 10}, "legal": true},
          {"transform_type": "transform_unroll",    "params": {"unroll_factor": 4}, "legal": true},
          {"transform_type": "transform_fusion",    "params": {"fused_loops": 2}, "legal": true},
          {"transform_type": "transform_interchange","params": {}, "legal": true}
        ]
    """
    from active_skill_system.domain.compiler_types import CompilerNodeKind, TransformParams

    with open(path, encoding="utf-8") as f:  # noqa: PTH123 — composition root, local file is intentional
        raw = json.load(f)
    if not isinstance(raw, list):
        raise ValueError(
            f"candidate-spec must be a JSON list (got {type(raw).__name__})"
        )
    candidates: list[TransformParams] = []
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValueError(f"candidate-spec[{i}] must be a dict (got {type(entry).__name__})")
        try:
            kind = CompilerNodeKind(entry["transform_type"])
        except (KeyError, ValueError) as e:
            raise ValueError(f"candidate-spec[{i}].transform_type invalid: {e}") from None
        params = entry.get("params", {})
        if not isinstance(params, dict):
            raise ValueError(f"candidate-spec[{i}].params must be a dict")
        legal = bool(entry.get("legal", True))
        candidates.append(
            TransformParams(transform_type=kind, params=params, legal=legal)
        )
    return tuple(candidates)


# ── Run API (callable from tests + main) ──────────────────────────────────


def run_evolution(
    baseline: Any,
    candidates: tuple,
    *,
    dataset: dict | None = None,
    max_iterations: int = 5,
    evolvable: Any = None,
) -> Any:
    """Run the offline evolution loop end-to-end.

    Args:
        baseline: the :class:`CompilerMetrics` to improve.
        candidates: tuple of :class:`TransformParams` candidates to seed the genome.
        dataset: optional dict with ``baseline_metrics`` mirroring the baseline
            (defaults to ``_metrics_to_dict(baseline)``).
        max_iterations: max mutation-evaluation cycles for EvolutionEngine.
        evolvable: optional pre-built :class:`TransformationGenomeEvolvable`
            (default: builds a fresh one via ``_build_transformation_evolvable``).
            Tests inject a fake evolvable here.
    """
    from active_skill_system.application.evolution_engine import EvolutionEngine

    if evolvable is None:
        evolvable = _build_transformation_evolvable()
    if dataset is None:
        dataset = {"baseline_metrics": _baseline_to_dict(baseline)}

    engine = EvolutionEngine()
    return engine.run(
        evolvable=evolvable,
        baseline_genome=candidates,
        dataset=dataset,
        max_iterations=max_iterations,
    )


def _baseline_to_dict(baseline: Any) -> dict[str, Any]:
    return {
        "cycles": baseline.cycles,
        "reg_pressure": baseline.reg_pressure,
        "spills": baseline.spills,
        "energy_proxy": baseline.energy_proxy,
        "is_valid": baseline.is_valid,
    }


# ── CLI entrypoint ────────────────────────────────────────────────────────


def _format_result(result: Any, baseline_cycles: int) -> str:
    """Format a PromotionResult as a single-line CLI summary + a detail block."""
    status = "PROMOTED" if result.promoted else "No improvement"
    lines = [
        f"{status} (iterations_used={result.iterations_used})",
        f"  baseline_fitness:  quality={result.baseline_fitness.quality:.4f} "
        f"cost={result.baseline_fitness.cost:.2f} "
        f"latency={result.baseline_fitness.latency:.2f}ms "
        f"regression={result.baseline_fitness.regression}",
        f"  candidate_fitness: quality={result.candidate_fitness.quality:.4f} "
        f"cost={result.candidate_fitness.cost:.2f} "
        f"latency={result.candidate_fitness.latency:.2f}ms "
        f"regression={result.candidate_fitness.regression}",
        f"  cycles reduction (baseline={baseline_cycles}): "
        f"{int(baseline_cycles * (1 - result.candidate_fitness.quality))} cycles",
        f"  reason: {result.reason}",
    ]
    return "\n".join(lines)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="active-skill-compiler-evolve",
        description=(
            "Run the offline EvolutionEngine loop on a compiler-domain genome "
            "(TransformParams candidates) against a pedagogical CompilerMetrics baseline. "
            "Deterministic — no network, no LLM."
        ),
    )
    parser.add_argument(
        "--baseline-cycles",
        type=int,
        default=1000,
        help="Cycles count for the baseline CompilerMetrics (default: 1000).",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=5,
        help="Max mutation-evaluation cycles for EvolutionEngine (default: 5).",
    )
    parser.add_argument(
        "--candidate-spec",
        type=str,
        default=None,
        help=(
            "Optional path to a JSON file listing candidate TransformParams. "
            "If omitted, uses a pedagogical 3-candidate set (TILE/UNROLL/FUSION)."
        ),
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-candidate trace; only print the final summary.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint. Returns process exit code."""
    args = _parse_args(argv)

    # Lazy L3 / L2 imports — module-level import must remain side-effect free.
    from active_skill_system.application.evolvable_adapters import (
        TransformationGenomeEvolvable,
    )

    if args.baseline_cycles < 1:
        print(f"error: --baseline-cycles must be >= 1 (got {args.baseline_cycles})", flush=True)
        return 2

    if args.max_iterations < 1:
        print(f"error: --max-iterations must be >= 1 (got {args.max_iterations})", flush=True)
        return 2

    baseline = _build_baseline(args.baseline_cycles)
    if args.candidate_spec is not None:
        candidates = _load_candidate_spec(args.candidate_spec)
    else:
        candidates = _default_candidates()

    evolvable = _build_transformation_evolvable()
    # Defensive runtime type check: helper should always return an Evolvable.
    from active_skill_system.domain.evolvable import Evolvable

    if not isinstance(evolvable, Evolvable):
        print(
            "error: composition helper did not produce an Evolvable "
            f"(got {type(evolvable).__name__})",
            flush=True,
        )
        return 1
    # Defensive unused-name: silence linters — TransformationGenomeEvolvable
    # import is needed to type-check the helper output contract.
    _ = TransformationGenomeEvolvable

    if not args.quiet:
        print(
            f"baseline: cycles={baseline.cycles}, spills={baseline.spills}, "
            f"is_valid={baseline.is_valid}",
            flush=True,
        )
        print(f"candidates: {len(candidates)} (kinds={[c.transform_type.value for c in candidates]})", flush=True)
        print(f"max_iterations: {args.max_iterations}", flush=True)
        print("---", flush=True)

    result = run_evolution(
        baseline,
        candidates,
        max_iterations=args.max_iterations,
        evolvable=evolvable,
    )

    print(_format_result(result, args.baseline_cycles), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
