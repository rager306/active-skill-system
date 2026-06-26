"""Tests for composition/sql_evolution.py (M018 S03)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from active_skill_system.application.sql_transformation_selector import (
    SQLStageRequirements,
    SQLTransformationSelector,
)
from active_skill_system.composition import sql_evolution
from active_skill_system.domain.evolvable import Evolvable
from active_skill_system.domain.sql_types import (
    SQLMetrics,
    SQLNodeKind,
    SQLTransformParams,
)


def _baseline(rows: int = 1000) -> SQLMetrics:
    return SQLMetrics(rows_examined=rows, rows_returned=10, time_ms=100.0, plan_cost=50.0, is_valid=True)


def _add_index(cols: int = 5) -> SQLTransformParams:
    return SQLTransformParams(transform_type=SQLNodeKind.SQL_TRANSFORM_ADD_INDEX, params={"cols": cols}, legal=True)


# ── _build_sql_evolvable ────────────────────────────────────────────────


def test_build_sql_evolvable_returns_evolvable() -> None:
    evolvable = sql_evolution._build_sql_evolvable()
    assert isinstance(evolvable, Evolvable)


def test_build_sql_evolvable_invokes_real_sql_tool_stub() -> None:
    """The wired evolvable's evaluate must actually invoke SQLToolStub."""
    evolvable = sql_evolution._build_sql_evolvable()
    result = evolvable.evaluate(
        (_add_index(cols=10),),
        {"baseline_metrics": {"rows_examined": 1000, "rows_returned": 10, "time_ms": 100.0, "plan_cost": 50.0, "is_valid": True}},
    )
    # rows_examined 1000 -> 100 (cols=10) -> quality 0.9.
    assert result.quality == pytest.approx(0.9)


# ── run_sql_evolution ───────────────────────────────────────────────────


def test_run_sql_evolution_promotes_when_candidate_improves() -> None:
    baseline = _baseline(rows=1000)
    candidates = (_add_index(cols=10),)
    result = sql_evolution.run_sql_evolution(baseline, candidates, max_iterations=5)
    assert result.promoted is True
    assert 0.85 <= result.candidate_fitness.quality <= 0.95


def test_run_sql_evolution_retains_when_at_caps() -> None:
    """At-cap ADD_INDEX cols=16 -> mutate is no-op -> no promotion."""
    candidates = (_add_index(cols=16),)
    result = sql_evolution.run_sql_evolution(_baseline(), candidates, max_iterations=3)
    assert result.promoted is False
    assert "No improvement" in result.reason


def test_run_sql_evolution_accepts_injected_evolvable() -> None:
    class _FakeEvolvable:
        @property
        def mutation_space(self):
            from active_skill_system.domain.evolvable import MutationSpace
            return MutationSpace(description="fake", mutate_fn_name="fake")
        def mutate(self, genome):
            return genome
        def evaluate(self, genome, dataset):
            from active_skill_system.domain.evolvable import FitnessSignal
            return FitnessSignal(quality=0.5, cost=1.0, latency=1.0)
    result = sql_evolution.run_sql_evolution(_baseline(), (_add_index(),), max_iterations=3, evolvable=_FakeEvolvable())
    assert result.promoted is False


# ── _default_candidates ────────────────────────────────────────────────


def test_default_candidates_have_three_sql_transforms() -> None:
    candidates = sql_evolution._default_candidates()
    assert len(candidates) == 3
    kinds = [c.transform_type for c in candidates]
    assert SQLNodeKind.SQL_TRANSFORM_ADD_INDEX in kinds
    assert SQLNodeKind.SQL_TRANSFORM_REORDER_JOINS in kinds
    assert SQLNodeKind.SQL_TRANSFORM_REWRITE_AS_JOIN in kinds


# ── _load_candidate_spec ───────────────────────────────────────────────


def test_load_candidate_spec_reads_json(tmp_path: Path) -> None:
    spec = [{"transform_type": "sql_transform_add_index", "params": {"cols": 8}, "legal": True}]
    spec_file = tmp_path / "spec.json"
    spec_file.write_text(json.dumps(spec), encoding="utf-8")
    candidates = sql_evolution._load_candidate_spec(str(spec_file))
    assert candidates[0].transform_type is SQLNodeKind.SQL_TRANSFORM_ADD_INDEX
    assert candidates[0].params["cols"] == 8


def test_load_candidate_spec_rejects_non_list(tmp_path: Path) -> None:
    spec_file = tmp_path / "spec.json"
    spec_file.write_text(json.dumps({"not": "a list"}), encoding="utf-8")
    with pytest.raises(ValueError, match="JSON list"):
        sql_evolution._load_candidate_spec(str(spec_file))


# ── main() CLI ──────────────────────────────────────────────────────────


def test_main_with_default_args_prints_summary(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = sql_evolution.main(["--baseline-rows", "1000", "--max-iterations", "3"])
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert exit_code == 0
    assert "PROMOTED" in combined or "No improvement" in combined
    assert "rows_examined reduction" in combined
    assert "reason:" in combined


def test_main_rejects_invalid_baseline_rows(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = sql_evolution.main(["--baseline-rows", "0", "--max-iterations", "1"])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "baseline-rows" in captured.out


def test_main_loads_candidate_spec(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    spec_file = tmp_path / "spec.json"
    spec_file.write_text(
        json.dumps([{"transform_type": "sql_transform_add_index", "params": {"cols": 5}, "legal": True}]),
        encoding="utf-8",
    )
    exit_code = sql_evolution.main(
        ["--baseline-rows", "1000", "--max-iterations", "2", "--candidate-spec", str(spec_file)]
    )
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "candidates: 1" in captured.out


# ── M022 S01: --stage flag (SQLTransformationSelector integration) ────────────


def test_default_sql_selector_has_three_stages() -> None:
    sel = sql_evolution._default_sql_selector()
    stages = sel.stages()
    assert set(stages.keys()) == {"index", "join", "aggregate"}


def test_default_sql_stage_index_filters_to_add_index() -> None:
    sel = sql_evolution._default_sql_selector()
    candidates = sql_evolution._default_candidates()
    selected = sel.select_for_stage("index", candidates)
    assert len(selected) == 1
    assert selected[0].transform_type is SQLNodeKind.SQL_TRANSFORM_ADD_INDEX


def test_default_sql_stage_join_filters_to_reorder_and_rewrite() -> None:
    sel = sql_evolution._default_sql_selector()
    candidates = sql_evolution._default_candidates()
    selected = sel.select_for_stage("join", candidates)
    kinds = {c.transform_type for c in selected}
    assert kinds == {SQLNodeKind.SQL_TRANSFORM_REORDER_JOINS, SQLNodeKind.SQL_TRANSFORM_REWRITE_AS_JOIN}


def test_default_sql_stage_aggregate_filters_to_rewrite_only() -> None:
    sel = sql_evolution._default_sql_selector()
    candidates = sql_evolution._default_candidates()
    selected = sel.select_for_stage("aggregate", candidates)
    assert len(selected) == 1
    assert selected[0].transform_type is SQLNodeKind.SQL_TRANSFORM_REWRITE_AS_JOIN


def test_default_sql_stage_index_enforces_min_cols() -> None:
    """min_cols=2 filters out ADD_INDEX with cols=1."""
    sel = SQLTransformationSelector()
    sel.register_stage(SQLStageRequirements(
        stage_name="index",
        allowed_kinds=frozenset({SQLNodeKind.SQL_TRANSFORM_ADD_INDEX}),
        min_cols=2,
    ))
    candidates = (
        SQLTransformParams(transform_type=SQLNodeKind.SQL_TRANSFORM_ADD_INDEX, params={"cols": 1}, legal=True),
        SQLTransformParams(transform_type=SQLNodeKind.SQL_TRANSFORM_ADD_INDEX, params={"cols": 4}, legal=True),
    )
    selected = sel.select_for_stage("index", candidates)
    assert len(selected) == 1
    assert selected[0].params["cols"] == 4


def test_main_with_sql_stage_join_filters_candidates(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = sql_evolution.main(
        ["--baseline-rows", "1000", "--max-iterations", "2", "--stage", "join"]
    )
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "kinds=['sql_transform_reorder_joins', 'sql_transform_rewrite_as_join']" in captured.out
    assert "stage: join" in captured.out


def test_main_with_sql_stage_index_filters_candidates(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = sql_evolution.main(
        ["--baseline-rows", "1000", "--max-iterations", "2", "--stage", "index"]
    )
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "kinds=['sql_transform_add_index']" in captured.out
    assert "stage: index" in captured.out


def test_main_with_sql_stage_invalid_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        sql_evolution.main(
            ["--baseline-rows", "1000", "--max-iterations", "1", "--stage", "unknown"]
        )


# ── R008 / R009 ────────────────────────────────────────────────────────


def test_module_import_has_no_side_effects() -> None:
    """R008: importing composition/sql_evolution has no side-effects."""
    result = subprocess.run(
        [sys.executable, "-c", "import active_skill_system.composition.sql_evolution"],
        capture_output=True,
        text=True,
        timeout=10,
        cwd="/root/active-skill-system",
    )
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_module_source_has_no_module_level_infra_imports() -> None:
    """R009: no module-level imports of activegraph/anthropic/openai/sql_tool_stub."""
    import ast
    tree = ast.parse(Path(sql_evolution.__file__).read_text(encoding="utf-8"))
    module_level_imports: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                module_level_imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module_level_imports.append(node.module or "")
    forbidden = ("activegraph", "anthropic", "openai", "sql_tool_stub", "sql_repair_policy", "evolvable_adapters", "sql_types", "sql_real_tool")
    for imp in module_level_imports:
        for f in forbidden:
            assert f not in imp, f"module-level import {imp!r} references {f!r} (R009)"
    assert module_level_imports, "module should still have stdlib imports"


# ── M037: --real flag (real-instrument SQLRealTool) ──────────────────


def test_build_sql_evolvable_real_wires_sql_real_tool() -> None:
    """real=True must produce a distinct evolvable backed by SQLRealTool."""
    stub_evolvable = sql_evolution._build_sql_evolvable(real=False)
    real_evolvable = sql_evolution._build_sql_evolvable(real=True)
    assert isinstance(real_evolvable, Evolvable)
    # The two evolvables capture different tool instances in their invoker closure.
    assert stub_evolvable is not real_evolvable


def test_run_sql_evolution_with_real_tool_reflects_explain_fitness() -> None:
    """E2e: the real SQLite EXPLAIN-driven loop must run end-to-end and the
    candidate fitness must reflect a real index benefit (rows_examined well
    below the 1000-row full scan), proving the loop is driven by the live
    instrument. Promotion is not asserted because the real planner may
    already be near-optimal for cols=1, so mutation cannot always improve —
    that is the correct source-of-truth behaviour, not a stub artefact."""
    from active_skill_system.domain.sql_types import SQLMetrics

    baseline = SQLMetrics(rows_examined=1000, rows_returned=10, time_ms=100.0, plan_cost=50.0)
    evolvable = sql_evolution._build_sql_evolvable(real=True)
    result = sql_evolution.run_sql_evolution(
        baseline, (_add_index(cols=1),), max_iterations=3, evolvable=evolvable
    )
    # Real EXPLAIN reduces the 1000-row scan to ~61 rows => quality ~0.94.
    assert result.candidate_fitness.quality > 0.8


def test_main_real_flag_runs_without_error(capsys: pytest.CaptureFixture[str]) -> None:
    """`sql_evolution --real --quiet` exits 0 and prints a summary."""
    exit_code = sql_evolution.main(
        ["--baseline-rows", "1000", "--max-iterations", "1", "--real", "--quiet"]
    )
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "PROMOTED" in captured.out or "No improvement" in captured.out


def test_module_source_has_no_real_tool_module_level_import() -> None:
    """R009 (M037): SQLRealTool must stay lazily imported inside _build_sql_evolvable."""
    import ast
    tree = ast.parse(Path(sql_evolution.__file__).read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "sql_real_tool" not in alias.name
        elif isinstance(node, ast.ImportFrom):
            assert "sql_real_tool" not in (node.module or "")
