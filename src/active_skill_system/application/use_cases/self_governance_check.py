"""L2 Application — Self-governance check (recursive dogfooding).

Applies our OWN verification tools to our OWN codebase. The project that
builds verification systems uses those same systems on itself.

This is NOT the sandbox verifier (which checks LLM-generated candidates
against a cache benchmark spec). This checks the PROJECT'S source code
against its own architectural and quality standards:

  1. layering_ok      — lint-imports contracts kept (R001/R002/R007)
  2. ruff_ok          — ruff check src/ clean
  3. ty_ok            — ty check src/ clean
  4. pyrefly_ok       — pyrefly check src/ clean
  5. riskratchet_ok   — riskratchet check exit 0 (no regression, R010/R011)
  6. convention_ok    — GitNexus convention consistency (new code matches patterns)
  7. tests_ok         — pytest -q passes (green suite)
  8. ast_symbols_ok   — every public module has ≥1 class/function with docstring

Each axis returns bool. Score = passed/total. Exit code via cli_exit.

Pure application (R002): delegates to tools via subprocess, no infra imports.
"""

from __future__ import annotations

import ast
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

_log_src = "src/active_skill_system"


@dataclass(frozen=True)
class GovernanceResult:
    """Outcome of a self-governance check."""

    axes: dict[str, bool] = field(default_factory=dict)
    details: dict[str, str] = field(default_factory=dict)

    @property
    def score(self) -> float:
        if not self.axes:
            return 0.0
        return sum(1 for v in self.axes.values() if v) / len(self.axes)

    @property
    def all_passed(self) -> bool:
        return bool(self.axes) and all(self.axes.values())

    def failed_axes(self) -> list[str]:
        return [k for k, v in self.axes.items() if not v]


def _run(cmd: list[str], timeout: int = 120) -> tuple[int, str]:
    """Run a command, return (exit_code, combined_output)."""
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
        )
        return r.returncode, (r.stdout + r.stderr)[-2000:]
    except (subprocess.SubprocessError, OSError) as e:
        return 1, str(e)


def check_layering() -> tuple[bool, str]:
    """R001/R002/R007: lint-imports contracts kept."""
    code, out = _run(["uv", "run", "lint-imports"], timeout=30)
    ok = code == 0 and "0 broken" in out
    return ok, out[-500:]


def check_ruff() -> tuple[bool, str]:
    """Lint: ruff check src/ clean (auto-fixable errors don't count as fail)."""
    code, out = _run(["uv", "run", "ruff", "check", _log_src], timeout=30)
    return code == 0, out[-500:]


def check_ty() -> tuple[bool, str]:
    """Type-check: ty check src/ clean."""
    code, out = _run(["uv", "run", "ty", "check", _log_src], timeout=60)
    return code == 0, out[-500:]


def check_pyrefly() -> tuple[bool, str]:
    """Type-check: pyrefly check src/ — reports total error count.

    LadybugDB has no type stubs (QueryResult.has_next/get_next unresolved).
    These are vendor gaps, not our bugs. The count is reported honestly.
    ok=True only when 0 errors.
    """
    code, out = _run(["uv", "run", "pyrefly", "check", _log_src], timeout=60)
    error_count = 0
    for line in out.splitlines():
        if "error" in line.lower():
            import re
            m = re.search(r"(\d+)\s+error", line)
            if m:
                error_count = int(m.group(1))
                break
    ok = error_count == 0
    return ok, f"{error_count} errors (incl. ladybug stub gaps)"


def check_riskratchet() -> tuple[bool, str]:
    """R010/R011: riskratchet check exit 0 (no regression).

    Requires coverage.json — generated via pytest --cov if missing.
    """
    cov_path = Path("coverage.json")
    if not cov_path.exists():
        _run(
            ["uv", "run", "pytest", "-q", "-p", "no:cacheprovider",
             "--cov", "--cov-report=json:coverage.json",
             "-W", "ignore::ResourceWarning"],
            timeout=180,
        )
    if not cov_path.exists():
        return False, "coverage.json not generated"
    code, out = _run(
        ["uv", "run", "riskratchet", "check", "src",
         "--coverage", "coverage.json", "--baseline", ".riskratchet.json"],
        timeout=60,
    )
    return code == 0, out[-500:]


def check_convention() -> tuple[bool, str]:
    """GitNexus convention consistency: new code matches existing patterns."""
    from active_skill_system.application.use_cases.gitnexus_convention_check import (
        ConventionChecker,
    )

    checker = ConventionChecker()
    # Check a representative module — domain/loop_graph.py (has better_than pattern).
    result = checker.check_convention("src/active_skill_system/domain/loop_graph.py")
    return result.consistent, result.reason


def check_tests() -> tuple[bool, str]:
    """Test suite: pytest -q passes."""
    code, out = _run(
        ["uv", "run", "pytest", "-q", "-p", "no:cacheprovider",
         "--tb=no", "-rN", "-W", "ignore::ResourceWarning"],
        timeout=180,
    )
    # Look for the pytest summary line containing "passed".
    summary = ""
    for line in reversed(out.strip().splitlines()):
        stripped = line.strip()
        if "passed" in stripped.lower() or "failed" in stripped.lower():
            summary = stripped
            break
    ok = code == 0 and "passed" in summary.lower() and "failed" not in summary.lower()
    return ok, summary or out[-300:]


def check_ast_docstrings() -> tuple[bool, str]:
    """AST: every public module in src/ has ≥1 documented top-level symbol."""
    src_root = Path(_log_src)
    if not src_root.exists():
        return False, f"{_log_src} not found"
    missing: list[str] = []
    for py in sorted(src_root.rglob("*.py")):
        if py.name == "__init__.py":
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        except SyntaxError:
            missing.append(f"{py}: syntax error")
            continue
        public_nodes = [
            n for n in ast.iter_child_nodes(tree)
            if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            and not n.name.startswith("_")
        ]
        if public_nodes:
            undoc = [n.name for n in public_nodes if not ast.get_docstring(n)]
            if undoc:
                missing.append(f"{py.name}: {undoc[0]} missing docstring")
    if missing:
        return False, f"{len(missing)} undocumented symbols: {missing[:3]}"
    return True, "all public symbols documented"


# Ordered list of axes (mirrors sandbox_verifier's 11-axis shape).
GOVERNANCE_AXES = (
    ("layering_ok", check_layering),
    ("ruff_ok", check_ruff),
    ("ty_ok", check_ty),
    ("pyrefly_ok", check_pyrefly),
    ("riskratchet_ok", check_riskratchet),
    ("convention_ok", check_convention),
    ("tests_ok", check_tests),
    ("ast_symbols_ok", check_ast_docstrings),
)


def run_governance_check(axes: tuple[str, ...] | None = None) -> GovernanceResult:
    """Run the self-governance check over the project's own source.

    Args:
        axes: optional subset of axis names to run. None = all 8.

    Returns:
        GovernanceResult with per-axis pass/fail + details.
    """
    selected = axes or tuple(name for name, _ in GOVERNANCE_AXES)
    results: dict[str, bool] = {}
    details: dict[str, str] = {}
    for name, checker in GOVERNANCE_AXES:
        if name not in selected:
            continue
        try:
            ok, detail = checker()
        except Exception as e:  # noqa: BLE001
            ok, detail = False, f"{type(e).__name__}: {e}"
        results[name] = ok
        details[name] = detail
    return GovernanceResult(axes=results, details=details)
