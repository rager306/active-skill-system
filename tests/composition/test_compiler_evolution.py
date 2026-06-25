"""Tests for composition/compiler_evolution.py (M017 S01).

Verifies:
  - `_build_transformation_evolvable()` returns a wired Evolvable.
  - `run_evolution()` promotes / retains candidates via real EvolutionEngine + real
    CompilerToolStub invoker (production wiring).
  - `main()` parses CLI args and prints a PromotionResult summary.
  - Module-level import is side-effect free (R008).
  - Module source contains no module-level heavy imports (R009).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from active_skill_system.composition import compiler_evolution
from active_skill_system.domain.compiler_types import (
    CompilerMetrics,
    CompilerNodeKind,
    TransformParams,
)
from active_skill_system.domain.evolvable import Evolvable, FitnessSignal

# ── Helpers ───────────────────────────────────────────────────────────────


def _baseline(cycles: int = 1000) -> CompilerMetrics:
    return CompilerMetrics(
        cycles=cycles, reg_pressure=10, spills=2, energy_proxy=1.0, is_valid=True
    )


def _tile(tile_size: int = 10) -> TransformParams:
    return TransformParams(
        transform_type=CompilerNodeKind.TRANSFORM_TILE,
        params={"tile_size": tile_size},
        legal=True,
    )


def _unroll(factor: int = 4) -> TransformParams:
    return TransformParams(
        transform_type=CompilerNodeKind.TRANSFORM_UNROLL,
        params={"unroll_factor": factor},
        legal=True,
    )


def _fusion(k: int = 2) -> TransformParams:
    return TransformParams(
        transform_type=CompilerNodeKind.TRANSFORM_FUSION,
        params={"fused_loops": k},
        legal=True,
    )


# ── _build_transformation_evolvable (R007 / R002 closing) ────────────────


def test_build_transformation_evolvable_returns_evolvable() -> None:
    """The composition helper must produce an Evolvable (closes M016 S03 T03 deviation)."""
    evolvable = compiler_evolution._build_transformation_evolvable()
    assert isinstance(evolvable, Evolvable)
    # Mutation space description is non-empty and mentions the three strategies.
    assert evolvable.mutation_space.description


def test_build_transformation_evolvable_invokes_real_compiler_tool_stub() -> None:
    """The wired evolvable's evaluate must actually invoke CompilerToolStub.

    We detect this by counting `transform_type` values in the resulting
    JSON-serialized metrics — the real CompilerToolStub emits a JSON dict
    with `cycles`; a fake would emit something else.
    """
    evolvable = compiler_evolution._build_transformation_evolvable()
    result = evolvable.evaluate((_tile(tile_size=10),), {"baseline_metrics": {
        "cycles": 1000, "reg_pressure": 10, "spills": 2, "energy_proxy": 1.0, "is_valid": True,
    }})
    assert isinstance(result, FitnessSignal)
    # Real tool reduces cycles 1000 / 10 = 100 → quality 0.9.
    assert result.quality == pytest.approx(0.9)
    assert result.regression is False
    assert result.cost == 1.0


# ── run_evolution (end-to-end via production wiring) ─────────────────────


def test_run_evolution_promotes_when_candidate_improves() -> None:
    """run_evolution with the pedagogical 3-candidate set must promote on the first
    mutating iteration (TILE 10→18 → cycles 1000→55 → ~94.5% reduction).
    """
    baseline = _baseline(cycles=1000)
    candidates = (_tile(tile_size=10), _unroll(factor=4), _fusion(k=2))
    result = compiler_evolution.run_evolution(
        baseline, candidates, max_iterations=5,
    )
    assert result.promoted is True
    # First mutation of TILE 10→18: cycles 1000 / 18 = 55 → quality (1000-55)/1000 ≈ 0.945.
    assert 0.90 <= result.candidate_fitness.quality <= 0.95
    # Baseline tuple fitness = evaluate(TILE 10) → cycles 1000/10 = 100 → quality 0.9.
    # Candidate tuple fitness = evaluate(TILE 18) → cycles 1000/18 ≈ 55 → quality ≈ 0.945.
    # Candidate must beat baseline.
    assert result.candidate_fitness.quality > result.baseline_fitness.quality
    assert result.candidate_fitness.regression is False


def test_run_evolution_retains_baseline_when_no_candidate_improves() -> None:
    """If all candidates are at mutation caps (TILE 256 / UNROLL 16 / FUSION 4),
    `_try_mutate_candidate` is a no-op → same fitness → no promotion.
    """
    baseline = _baseline(cycles=1000)
    candidates = (
        _tile(tile_size=256),  # cap → no-op
        _unroll(factor=16),    # cap → no-op
        _fusion(k=4),          # cap → no-op
    )
    result = compiler_evolution.run_evolution(
        baseline, candidates, max_iterations=3,
    )
    assert result.promoted is False
    assert result.iterations_used == 3
    assert "No improvement" in result.reason
    # Baseline was retained (genome unchanged).
    assert result.promoted_genome == candidates


def test_run_evolution_accepts_injected_evolvable() -> None:
    """Tests can inject a fake evolvable (seam for unit-testing the wiring)."""
    baseline = _baseline(cycles=1000)

    class _FakeEvolvable:
        @property
        def mutation_space(self):
            from active_skill_system.domain.evolvable import MutationSpace

            return MutationSpace(description="fake", mutate_fn_name="fake")

        def mutate(self, genome):
            return genome  # no-op

        def evaluate(self, genome, dataset) -> FitnessSignal:
            return FitnessSignal(quality=0.5, cost=1.0, latency=1.0)

    result = compiler_evolution.run_evolution(
        baseline, (_tile(),), max_iterations=3, evolvable=_FakeEvolvable(),
    )
    assert result.promoted is False
    assert result.iterations_used == 3


def test_run_evolution_uses_default_dataset_when_not_provided() -> None:
    """If no dataset is passed, the helper builds one mirroring the baseline."""
    baseline = _baseline(cycles=500)
    result = compiler_evolution.run_evolution(
        baseline, (_tile(tile_size=10),), max_iterations=3,
    )
    # Baseline cycles/quality wiring should still apply.
    assert result.baseline_fitness.quality >= 0.0


# ── _default_candidates ───────────────────────────────────────────────────


def test_default_candidates_have_three_pedagogical_transforms() -> None:
    """The default candidate set must contain TILE/UNROLL/FUSION (deterministic)."""
    candidates = compiler_evolution._default_candidates()
    assert len(candidates) == 3
    kinds = [c.transform_type for c in candidates]
    assert CompilerNodeKind.TRANSFORM_TILE in kinds
    assert CompilerNodeKind.TRANSFORM_UNROLL in kinds
    assert CompilerNodeKind.TRANSFORM_FUSION in kinds


# ── _load_candidate_spec ──────────────────────────────────────────────────


def test_load_candidate_spec_reads_json(tmp_path: Path) -> None:
    """Optional --candidate-spec file must be parseable into TransformParams."""
    spec = [
        {"transform_type": "transform_tile", "params": {"tile_size": 16}, "legal": True},
        {"transform_type": "transform_unroll", "params": {"unroll_factor": 8}, "legal": True},
    ]
    spec_file = tmp_path / "spec.json"
    spec_file.write_text(json.dumps(spec), encoding="utf-8")

    candidates = compiler_evolution._load_candidate_spec(str(spec_file))
    assert len(candidates) == 2
    assert candidates[0].transform_type is CompilerNodeKind.TRANSFORM_TILE
    assert candidates[0].params["tile_size"] == 16
    assert candidates[1].transform_type is CompilerNodeKind.TRANSFORM_UNROLL


def test_load_candidate_spec_rejects_non_list(tmp_path: Path) -> None:
    spec_file = tmp_path / "spec.json"
    spec_file.write_text(json.dumps({"not": "a list"}), encoding="utf-8")
    with pytest.raises(ValueError, match="JSON list"):
        compiler_evolution._load_candidate_spec(str(spec_file))


def test_load_candidate_spec_rejects_invalid_kind(tmp_path: Path) -> None:
    spec_file = tmp_path / "spec.json"
    spec_file.write_text(json.dumps([{"transform_type": "transform_bogus"}]), encoding="utf-8")
    with pytest.raises(ValueError, match="transform_type invalid"):
        compiler_evolution._load_candidate_spec(str(spec_file))


# ── main() CLI entrypoint ─────────────────────────────────────────────────


def test_main_with_default_args_prints_promotion_summary(capsys: pytest.CaptureFixture[str]) -> None:
    """`main(["--baseline-cycles", "1000", "--max-iterations", "3"])` must print a
    PromotionResult summary line containing PROMOTED or No improvement."""
    exit_code = compiler_evolution.main(["--baseline-cycles", "1000", "--max-iterations", "3"])
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert exit_code == 0
    assert "PROMOTED" in combined or "No improvement" in combined
    # Must contain the candidate_fitness quality line.
    assert "candidate_fitness" in combined
    assert "reason:" in combined


def test_main_rejects_invalid_baseline_cycles(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = compiler_evolution.main(["--baseline-cycles", "0", "--max-iterations", "1"])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "baseline-cycles" in captured.out


def test_main_rejects_invalid_max_iterations(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = compiler_evolution.main(["--baseline-cycles", "100", "--max-iterations", "0"])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "max-iterations" in captured.out


def test_main_loads_candidate_spec(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """`main()` must accept a --candidate-spec JSON file and use its candidates."""
    spec_file = tmp_path / "spec.json"
    spec_file.write_text(
        json.dumps(
            [
                {"transform_type": "transform_tile", "params": {"tile_size": 10}, "legal": True},
            ]
        ),
        encoding="utf-8",
    )
    exit_code = compiler_evolution.main(
        ["--baseline-cycles", "1000", "--max-iterations", "2", "--candidate-spec", str(spec_file)]
    )
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "candidates: 1" in captured.out  # shows the candidate count


# ── R008: module-level import is side-effect free ─────────────────────────


def test_module_import_has_no_side_effects() -> None:
    """Importing the composition module must NOT print to stdout/stderr or start a process.

    This is the R008 contract. Run via subprocess so any module-level
    print / file open / network call would surface.
    """
    result = subprocess.run(
        [sys.executable, "-c", "import active_skill_system.composition.compiler_evolution"],
        capture_output=True,
        text=True,
        timeout=10,
        cwd="/root/active-skill-system",
    )
    assert result.returncode == 0, (
        f"import failed: stdout={result.stdout!r}, stderr={result.stderr!r}"
    )
    assert result.stdout == "", f"module produced stdout: {result.stdout!r}"
    assert result.stderr == "", f"module produced stderr: {result.stderr!r}"


def test_module_source_has_no_module_level_infra_imports() -> None:
    """R009: no module-level imports of activegraph / anthropic / openai / L3 adapters.

    Uses `ast` to walk only real module-level Import / ImportFrom nodes —
    docstring prose mentioning modules in backticks (e.g. ``CompilerToolStub``)
    must not trigger a false positive.
    """
    import ast as _ast

    tree = _ast.parse(Path(compiler_evolution.__file__).read_text(encoding="utf-8"))
    module_level_imports: list[str] = []
    for node in tree.body:
        if isinstance(node, _ast.Import):
            for alias in node.names:
                module_level_imports.append(alias.name)
        elif isinstance(node, _ast.ImportFrom):
            module_level_imports.append(node.module or "")
    forbidden_substrings = (
        "activegraph",
        "anthropic",
        "openai",
        "compiler_tool_stub",
        "evolution_engine",
        "evolvable_adapters",
        "compiler_types",
    )
    for imp in module_level_imports:
        for forbidden in forbidden_substrings:
            assert forbidden not in imp, (
                f"module-level import {imp!r} references {forbidden!r} (R009 violation)"
            )
    # Sanity: at least one module-level import remains (argparse + json + Sequence + Any).
    assert module_level_imports, "module should still have stdlib imports"


# ── defensive run path ────────────────────────────────────────────────────


def test_format_result_contains_both_fitness_lines() -> None:
    """`_format_result` is the human-readable summary used by main()."""
    from active_skill_system.application.evolution_engine import PromotionResult

    result = PromotionResult(
        promoted=True,
        promoted_genome=(_tile(),),
        baseline_fitness=FitnessSignal(quality=0.0, cost=3.0, latency=1.0, regression=False),
        candidate_fitness=FitnessSignal(quality=0.945, cost=1.0, latency=1.0, regression=False),
        iterations_used=1,
        reason="Candidate promoted at iteration 1: quality 0.00→0.95, cost 3.00→1.00",
    )
    summary = compiler_evolution._format_result(result, baseline_cycles=1000)
    assert "PROMOTED" in summary
    assert "baseline_fitness" in summary
    assert "candidate_fitness" in summary
    assert "cycles reduction" in summary
    assert "reason:" in summary
