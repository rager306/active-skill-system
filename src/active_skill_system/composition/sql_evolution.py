"""L4 Composition — EvolutionEngine wiring for the SQL domain (M018 S03).

Wires the offline ``EvolutionEngine`` (L2 application) with the
``SQLEvolvable`` (L2 application) and the real ``SQLToolStub`` (L3
adapter) so the offline evolution loop can run end-to-end on SQL plan
optimization genomes. Mirrors ``composition/compiler_evolution.py``
(M017 S01) and the MEM019 reusable pattern exactly.

No activegraph. No LLM. No network. Pure deterministic offline evolution
over pedagogical ``SQLMetrics`` produced by the local ``SQLToolStub``.

Composition shape mirrors ``composition/diligence.py`` and
``composition/compiler_evolution.py``:

  - Module-level imports: only stdlib + ``argparse``. (R008 / R009.)
  - All heavy imports deferred into ``_build_*`` helpers / ``main()``.
  - Importing this module is side-effect free.

Usage::

    uv run python -m active_skill_system.composition.sql_evolution \\
        --baseline-rows 1000 --max-iterations 3
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from typing import Any

# ── Helpers (lazy infra imports) ─────────────────────────────────────────


def _build_sql_evolvable() -> Any:
    """Build a fully-wired :class:`SQLEvolvable`.

    Lazy imports: SQLToolStub (L3 adapter) and SQLEvolvable (L2 application)
    are imported only when this helper is called. Mirrors the L4
    composition pattern from M017 S01 (MEM019).
    """
    from active_skill_system.adapters.sql_tool_stub import SQLToolStub
    from active_skill_system.application.evolvable_adapters import SQLEvolvable

    tool = SQLToolStub()

    def _invoker(args: dict[str, Any]) -> tuple[bool, str]:
        result = tool.invoke(args)
        return (result.success, result.text)

    return SQLEvolvable(invoker=_invoker)


def _default_candidates() -> tuple:
    """Pedagogical 3-candidate set: ADD_INDEX / REORDER_JOINS / REWRITE_AS_JOIN."""
    from active_skill_system.domain.sql_types import SQLNodeKind, SQLTransformParams

    return (
        SQLTransformParams(
            transform_type=SQLNodeKind.SQL_TRANSFORM_ADD_INDEX,
            params={"cols": 5},
            legal=True,
        ),
        SQLTransformParams(
            transform_type=SQLNodeKind.SQL_TRANSFORM_REORDER_JOINS,
            params={"order_size": 2},
            legal=True,
        ),
        SQLTransformParams(
            transform_type=SQLNodeKind.SQL_TRANSFORM_REWRITE_AS_JOIN,
            params={"tables": 2},
            legal=True,
        ),
    )


def _default_sql_selector() -> Any:
    """Build a SQLTransformationSelector with 3 default stages (M022 S01).

    Stages:
      - index:     ADD_INDEX only (min_cols=2)
      - join:      REORDER_JOINS + REWRITE_AS_JOIN (min_order_size=2)
      - aggregate: REWRITE_AS_JOIN only
    """
    from active_skill_system.application.sql_transformation_selector import (
        SQLStageRequirements,
        SQLTransformationSelector,
    )
    from active_skill_system.domain.sql_types import SQLNodeKind

    sel = SQLTransformationSelector()
    sel.register_stage(SQLStageRequirements(
        stage_name="index",
        allowed_kinds=frozenset({SQLNodeKind.SQL_TRANSFORM_ADD_INDEX}),
        min_cols=2,
    ))
    sel.register_stage(SQLStageRequirements(
        stage_name="join",
        allowed_kinds=frozenset({
            SQLNodeKind.SQL_TRANSFORM_REORDER_JOINS,
            SQLNodeKind.SQL_TRANSFORM_REWRITE_AS_JOIN,
        }),
        min_cols=2,
    ))
    sel.register_stage(SQLStageRequirements(
        stage_name="aggregate",
        allowed_kinds=frozenset({SQLNodeKind.SQL_TRANSFORM_REWRITE_AS_JOIN}),
    ))
    return sel


def _build_baseline(rows_examined: int) -> Any:
    """Build a deterministic pedagogical baseline :class:`SQLMetrics`."""
    from active_skill_system.domain.sql_types import SQLMetrics

    return SQLMetrics(
        rows_examined=rows_examined,
        rows_returned=10,
        time_ms=100.0,
        plan_cost=50.0,
        is_valid=True,
    )


def _load_candidate_spec(path: str) -> tuple:
    """Load candidate SQLTransformParams from a local JSON file."""
    from active_skill_system.domain.sql_types import SQLNodeKind, SQLTransformParams

    with open(path, encoding="utf-8") as f:  # noqa: PTH123 — composition root, local file is intentional
        raw = json.load(f)
    if not isinstance(raw, list):
        raise ValueError(
            f"candidate-spec must be a JSON list (got {type(raw).__name__})"
        )
    candidates: list[SQLTransformParams] = []
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValueError(f"candidate-spec[{i}] must be a dict (got {type(entry).__name__})")
        try:
            kind = SQLNodeKind(entry["transform_type"])
        except (KeyError, ValueError) as e:
            raise ValueError(f"candidate-spec[{i}].transform_type invalid: {e}") from None
        params = entry.get("params", {})
        if not isinstance(params, dict):
            raise ValueError(f"candidate-spec[{i}].params must be a dict")
        legal = bool(entry.get("legal", True))
        candidates.append(SQLTransformParams(transform_type=kind, params=params, legal=legal))
    return tuple(candidates)


# ── Run API ───────────────────────────────────────────────────────────────


def run_sql_evolution(
    baseline: Any,
    candidates: tuple,
    *,
    dataset: dict | None = None,
    max_iterations: int = 5,
    evolvable: Any = None,
) -> Any:
    """Run the offline evolution loop end-to-end (mirrors compiler_evolution.run_evolution)."""
    from active_skill_system.application.evolution_engine import EvolutionEngine

    if evolvable is None:
        evolvable = _build_sql_evolvable()
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
        "rows_examined": baseline.rows_examined,
        "rows_returned": baseline.rows_returned,
        "time_ms": baseline.time_ms,
        "plan_cost": baseline.plan_cost,
        "is_valid": baseline.is_valid,
    }


# ── CLI entrypoint ────────────────────────────────────────────────────────


def _format_result(result: Any, baseline_rows: int, stage: str | None = None) -> str:
    status = "PROMOTED" if result.promoted else "No improvement"
    lines = [
        f"{status} (iterations_used={result.iterations_used})",
    ]
    if stage is not None:
        lines.append(f"  stage: {stage}")
    lines.extend([
        f"  baseline_fitness:  quality={result.baseline_fitness.quality:.4f} "
        f"cost={result.baseline_fitness.cost:.2f} "
        f"latency={result.baseline_fitness.latency:.2f}ms "
        f"regression={result.baseline_fitness.regression}",
        f"  candidate_fitness: quality={result.candidate_fitness.quality:.4f} "
        f"cost={result.candidate_fitness.cost:.2f} "
        f"latency={result.candidate_fitness.latency:.2f}ms "
        f"regression={result.candidate_fitness.regression}",
        f"  rows_examined reduction (baseline={baseline_rows}): "
        f"{int(baseline_rows * (1 - result.candidate_fitness.quality))} rows",
        f"  reason: {result.reason}",
    ])
    return "\n".join(lines)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="active-skill-sql-evolve",
        description=(
            "Run the offline EvolutionEngine loop on a SQL-plan-optimization genome "
            "(SQLTransformParams candidates) against a pedagogical SQLMetrics baseline. "
            "Deterministic — no network, no LLM."
        ),
    )
    parser.add_argument(
        "--baseline-rows",
        type=int,
        default=1000,
        help="Rows-examined count for the baseline SQLMetrics (default: 1000).",
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
            "Optional path to a JSON file listing candidate SQLTransformParams. "
            "If omitted, uses a pedagogical 3-candidate set (ADD_INDEX/REORDER_JOINS/REWRITE_AS_JOIN)."
        ),
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-candidate trace; only print the final summary.",
    )
    parser.add_argument(
        "--stage",
        type=str,
        default=None,
        choices=("index", "join", "aggregate"),
        help="Filter candidates through SQLTransformationSelector for the given stage (M022).",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)

    if args.baseline_rows < 1:
        print(f"error: --baseline-rows must be >= 1 (got {args.baseline_rows})", flush=True)
        return 2

    if args.max_iterations < 1:
        print(f"error: --max-iterations must be >= 1 (got {args.max_iterations})", flush=True)
        return 2

    baseline = _build_baseline(args.baseline_rows)
    if args.candidate_spec is not None:
        candidates = _load_candidate_spec(args.candidate_spec)
    else:
        candidates = _default_candidates()

    # M022: per-stage filtering via SQLTransformationSelector.
    stage_name: str | None = None
    if args.stage is not None:
        selector = _default_sql_selector()
        filtered = selector.select_for_stage(args.stage, candidates)
        if not filtered:
            print(
                f"warning: stage '{args.stage}' filters out all {len(candidates)} candidates; "
                "EvolutionEngine will receive empty genome",
                flush=True,
            )
        candidates = filtered
        stage_name = args.stage

    evolvable = _build_sql_evolvable()
    from active_skill_system.domain.evolvable import Evolvable

    if not isinstance(evolvable, Evolvable):
        print(
            "error: composition helper did not produce an Evolvable "
            f"(got {type(evolvable).__name__})",
            flush=True,
        )
        return 1

    if not args.quiet:
        print(
            f"baseline: rows_examined={baseline.rows_examined}, "
            f"rows_returned={baseline.rows_returned}, is_valid={baseline.is_valid}",
            flush=True,
        )
        print(
            f"candidates: {len(candidates)} "
            f"(kinds={[c.transform_type.value for c in candidates]})",
            flush=True,
        )
        print(f"max_iterations: {args.max_iterations}", flush=True)
        print("---", flush=True)

    result = run_sql_evolution(
        baseline,
        candidates,
        max_iterations=args.max_iterations,
        evolvable=evolvable,
    )

    print(_format_result(result, args.baseline_rows, stage_name), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
