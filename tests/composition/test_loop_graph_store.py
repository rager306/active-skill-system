"""Tests for the RGLA composition loop_graph_store (M041 S02)."""

from __future__ import annotations

import ast
import contextlib
import io
import subprocess
import sys
from pathlib import Path

from active_skill_system.composition import loop_graph_store


def _run_main(argv: list[str] | None = None) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = loop_graph_store.main(argv)
    return code, out.getvalue()


# ── Composition e2e ───────────────────────────────────────────────────


def test_main_exits_zero_and_prints_provenance():
    code, out = _run_main(["--db", ":memory:"])
    assert code == 0
    assert "stored:" in out
    assert "neighbours of loop:sample-loop-1:" in out
    assert "skill:sql-plan-opt" in out
    assert "verifier:gap-detector" in out


def test_main_stores_vertex_and_edge_counts_match_projection():
    code, out = _run_main(["--db", ":memory:"])
    assert code == 0
    # 5 vertices: loop, intent, 2 skills, verifier. 4 edges: created, 2 uses, verified_by.
    assert "5 vertices, 4 edges" in out


def test_main_demonstrates_typed_sub_loop_contract():
    code, out = _run_main(["--db", ":memory:"])
    assert code == 0
    assert "typed contract" in out
    assert "VERIFIED_BY" in out
    assert "confidence" in out


# ── R008 / R009 ───────────────────────────────────────────────────────


def test_module_import_has_no_side_effects():
    """R008: importing the composition module has no side effects."""
    result = subprocess.run(
        [sys.executable, "-c", "import active_skill_system.composition.loop_graph_store"],
        capture_output=True,
        text=True,
        timeout=10,
        cwd="/root/active-skill-system",
    )
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def _module_level_imports() -> list[str]:
    tree = ast.parse(Path(loop_graph_store.__file__).read_text(encoding="utf-8"))
    mods: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            mods += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            mods.append(node.module or "")
    return mods


def test_no_module_level_infra_imports():
    """R009: no module-level imports of ladybug/domain-loop/adapters/activegraph."""
    forbidden = ("ladybug", "domain.loop", "domain.loop_graph", "adapters", "activegraph")
    for imp in _module_level_imports():
        for f in forbidden:
            assert f not in imp, f"module-level import {imp!r} references {f!r} (R009)"
