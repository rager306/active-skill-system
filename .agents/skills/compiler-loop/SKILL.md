---
name: compiler-loop
description: Optimize compiler loop transformations (TILE, INTERCHANGE, FUSION, UNROLL) on a baseline of compiler metrics. Use when the user wants to improve a compiler's cycles, spills, or cache_misses. The output is a PromotionResult with the mutated genome and ranked by the measurable-improvement gate (CompilerMetrics.better_than).
version: 1.0.0
license: Apache-2.0
allowed-tools:
  - Bash(uv run python -m active_skill_system.composition.compiler_evolution *)
---

# compiler-loop

This skill runs the offline loop-engineering loop for the compiler domain.
It composes a wired `TransformationGenomeEvolvable` (a `TransformParams` tuple + the
`CompilerToolStub` invoker) and runs `EvolutionEngine.run` to find a better transform set.

## When to use this skill

- You have a baseline of `CompilerMetrics` (cycles, reg_pressure, spills, energy_proxy,
  cache_misses, vectorization_factor) and want to reduce cycles.
- You want a deterministic, reproducible evolution over a small transform space
  (TILE, INTERCHANGE, FUSION, UNROLL).
- You do NOT need a live compiler driver; the pedagogical `CompilerToolStub` is enough.

## What the skill does

1. Builds a `TransformationGenomeEvolvable` wired to the real `CompilerToolStub` (lazy import).
2. Picks 3 default candidates (TILE tile_size=10, UNROLL factor=4, FUSION k=2).
3. Calls `EvolutionEngine.run` with the baseline + candidates.
4. Returns a `PromotionResult(promoted=..., promoted_genome=..., ...)` with the best mutated
   genome or `promoted=False` if no candidate strictly improved the baseline.

## CLI

```bash
uv run python -m active_skill_system.composition.compiler_evolution --baseline-cycles 1000 --max-iterations 3
uv run python -m active_skill_system.composition.compiler_evolution --stage optimize --baseline-cycles 1000
```

Flags:
- `--baseline-cycles` (int, default 1000): the starting cycles count.
- `--max-iterations` (int, default 5): per-candidate mutation-evaluation budget.
- `--stage` (str, choices: parse|optimize|codegen): per-stage filtering via `TransformationSelector`.
- `--use-polyhedral-model` (flag): use the realistic `PolyhedralCostModel` instead of the
  pedagogical `CompilerToolStub` (cache + vectorization-aware fitness).
- `--candidate-spec` (str, path to JSON file with `[{transform_type, params, legal}, ...]`).
- `--quiet` (flag): suppress per-candidate trace.

## Library API

```python
from active_skill_system.composition import compiler_evolution
result = compiler_evolution.run_evolution(
    baseline=compiler_evolution._build_baseline(1000),
    candidates=compiler_evolution._default_candidates(),
    max_iterations=5,
)
```

## Inputs

- `baseline`: a `CompilerMetrics` namedtuple (or dict).
- `candidates`: tuple of `TransformParams` (or `None` for defaults).
- `max_iterations`: int >= 1.

## Outputs

`PromotionResult` with fields:
- `promoted` (bool)
- `promoted_genome` (tuple of `TransformParams`)
- `baseline_fitness`, `candidate_fitness` (`FitnessSignal`)
- `iterations_used` (int)
- `reason` (str — human-readable)

## Acceptance tests

- `tests/composition/test_compiler_evolution.py` — CLI + library (17 tests).
- `tests/application/test_evolution_engine.py` — engine invariants.

## Ratchet

Every invocation should append a `RatchetEntry` to `ratchet/ledger.jsonl` with
`area="compiler-loop"` and `test_ref="tests/composition/test_compiler_evolution.py"`.

## Anti-patterns (do NOT do this)

- Do not import `CompilerToolStub` at module level — must be lazy inside `_build_*()`.
- Do not use `better_than` for gap detection — use explicit per-axis inspection
  (`classify_gap` in `compiler_gap_detector.py`).
- Do not import L3 adapters from L2 application code (R002/R007 violation).
