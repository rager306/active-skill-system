---
name: sql-plan-opt
description: Optimize SQL query plan optimizations (ADD_INDEX, REORDER_JOINS, REWRITE_AS_JOIN) on a baseline of SQL metrics. Use when the user wants to reduce rows_examined or improve query plan quality.
version: 1.0.0
license: Apache-2.0
allowed-tools:
  - Bash(uv run python -m active_skill_system.composition.sql_evolution *)
---

# sql-plan-opt

This skill runs the offline loop-engineering loop for the SQL query plan optimization domain.
It composes a wired `SQLEvolvable` and runs `EvolutionEngine.run` to find a better SQL transform set.

## When to use this skill

- You have a baseline of `SQLMetrics` (rows_examined, rows_returned, time_ms, plan_cost, is_valid).
- You want to optimize query plans via ADD_INDEX, REORDER_JOINS, REWRITE_AS_JOIN, or REPLAN_PROVIDERS.
- The primary axis is `rows_examined` (lower = better).

## What the skill does

1. Builds a `SQLEvolvable` wired to the real `SQLToolStub` (lazy import).
2. Picks 3 default candidates (ADD_INDEX cols=5, REORDER_JOINS order_size=2, REWRITE_AS_JOIN tables=2).
3. Calls `EvolutionEngine.run` with the baseline + candidates.
4. Returns a `PromotionResult` with the best mutated genome or `promoted=False` if no candidate
   strictly improved the baseline (per `SQLMetrics.better_than`).

## CLI

```bash
uv run python -m active_skill_system.composition.sql_evolution --baseline-rows 1000 --max-iterations 3
uv run python -m active_skill_system.composition.sql_evolution --stage join --baseline-rows 1000
```

Flags:
- `--baseline-rows` (int, default 1000): starting rows_examined.
- `--max-iterations` (int, default 5).
- `--stage` (str, choices: index|join|aggregate): per-stage filtering via `SQLTransformationSelector`.
- `--quiet` (flag).

## Library API

```python
from active_skill_system.composition import sql_evolution
result = sql_evolution.run_sql_evolution(
    baseline=sql_evolution._build_baseline(1000),
    candidates=sql_evolution._default_candidates(),
    max_iterations=5,
)
```

## Inputs

- `baseline`: a `SQLMetrics` namedtuple.
- `candidates`: tuple of `SQLTransformParams` (or `None` for defaults).
- `max_iterations`: int >= 1.

## Outputs

`PromotionResult` with the same fields as `compiler-loop`.

## Acceptance tests

- `tests/composition/test_sql_evolution.py` — CLI + library (21 tests).
- `tests/application/use_cases/test_sql_gap_detector.py` — gap detector invariants.

## Ratchet

Every invocation should append a `RatchetEntry` to `ratchet/ledger.jsonl` with
`area="sql-plan-opt"` and `test_ref="tests/composition/test_sql_evolution.py"`.

## Anti-patterns (do NOT do this)

- Do not delegate gap detection to `SQLMetrics.better_than` — use explicit
  per-axis inspection (`classify_sql_gap` in `sql_gap_detector.py`).
- Do not import `SQLToolStub` at module level.
- Do not couple SQL to compiler patterns (decoupling test enforces this).
