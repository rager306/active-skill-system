---
name: iac-plan-opt
description: Optimize Infrastructure-as-Code plan transformations (REMOVE_UNUSED, ADD_OUTPUT, RESTRUCTURE_DEP, REPLAN_PROVIDERS) on a baseline of IaC plan metrics. Use when the user wants to reduce resource_count or improve IaC plan quality.
version: 1.0.0
license: Apache-2.0
allowed-tools:
  - Bash(uv run python -m active_skill_system.composition.iac_evolution *)
---

# iac-plan-opt

This skill runs the offline loop-engineering loop for the Infrastructure-as-Code
plan optimization domain. It composes a wired `IaCEvolvable` and runs `EvolutionEngine.run`
to find a better IaC transform set.

## When to use this skill

- You have a baseline of `IaCPlanMetrics` (resource_count, module_count, variable_count,
  drift_score, is_valid).
- You want to optimize IaC plans via REMOVE_UNUSED, ADD_OUTPUT, RESTRUCTURE_DEP, or
  REPLAN_PROVIDERS.
- The primary axis is `resource_count` (lower = better).

## What the skill does

1. Builds an `IaCEvolvable` wired to the real `IaCToolStub` (lazy import).
2. Picks 3 default candidates (REMOVE_UNUSED variable_name="old_var",
   ADD_OUTPUT, RESTRUCTURE_DEP).
3. Calls `EvolutionEngine.run` with the baseline + candidates.
4. Returns a `PromotionResult` with the best mutated genome or `promoted=False`.

## CLI

```bash
uv run python -m active_skill_system.composition.iac_evolution --baseline-resources 100 --max-iterations 3
uv run python -m active_skill_system.composition.iac_evolution --stage cleanup --baseline-resources 100
```

Flags:
- `--baseline-resources` (int, default 100): starting resource_count.
- `--max-iterations` (int, default 5).
- `--stage` (str, choices: cleanup|observability|restructure): per-stage filtering.
- `--quiet` (flag).

## Library API

```python
from active_skill_system.composition import iac_evolution
result = iac_evolution.run_evolution(
    baseline=iac_evolution._build_baseline(100),
    candidates=iac_evolution._default_candidates(),
    max_iterations=5,
)
```

## Inputs

- `baseline`: an `IaCPlanMetrics` namedtuple.
- `candidates`: tuple of `IaCTransformParams` (or `None` for defaults).
- `max_iterations`: int >= 1.

## Outputs

`PromotionResult` with the same fields as `compiler-loop`.

## Acceptance tests

- `tests/composition/test_iac_evolution.py` — CLI + library (12 tests).

## Ratchet

Every invocation should append a `RatchetEntry` to `ratchet/ledger.jsonl` with
`area="iac-plan-opt"` and `test_ref="tests/composition/test_iac_evolution.py"`.

## Anti-patterns (do NOT do this)

- Do not import `IaCToolStub` at module level.
- Do not couple IaC to compiler patterns.
- Do not use `better_than` for gap detection — use explicit per-axis inspection.
