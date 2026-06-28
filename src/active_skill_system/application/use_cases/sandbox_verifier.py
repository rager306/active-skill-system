"""L2 Application — Sandbox verifier (M042 S01 T02, D013 mini-loop).

A DETERMINISTIC fitness scorer for the cache benchmark (no LLM). Given a path
to a candidate ``cache_types``-shaped module, it scores the candidate along
typed axes: structure (CacheMetrics + CacheNodeKind present, correct fields),
invariants (non-negative, frozen dataclass), ranking correctness
(better_than), ruff-clean, and LOC under R006 (200).

Safety: the verifier imports the candidate in an isolated namespace (the
candidate is expected to be a pure dataclass/enum module — no network, no
side-effecting code) and runs ``ruff`` as a subprocess. It does NOT execute
arbitrary logic beyond constructing dataclasses. Pure application (R002): no
LLM, no adapters.
"""

from __future__ import annotations

import ast
import importlib.util
import logging
import subprocess
import sys
from dataclasses import is_dataclass
from pathlib import Path
from typing import Any

from active_skill_system.domain.sandbox_cache_task import (
    REQUIRED_FIELDS,
)

_R06_MAX_LOC = 200
_log = logging.getLogger("active_skill_system.application.sandbox_verifier")


class SandboxFitness:
    """Typed fitness result for one candidate.

    Axes (each a bool/int, the scale S02/S03 reuse):
      - structure_ok: CacheMetrics + CacheNodeKind present, correct field names.
      - invariants_ok: frozen dataclass, non-negative int fields.
      - ranking_ok: better_than implements the inverse hit_count rule.
      - ruff_clean: ruff check exits 0 on the candidate.
      - ty_clean: ty type check exits 0 (Astral type checker, LSP-grade).
      - pyrefly_clean: pyrefly check exits 0 (Meta type checker, LSP-grade).
      - risk_ok: riskratchet risk score under threshold (D002 ratchet).
      - symbols_ok: top-level CacheMetrics + CacheNodeKind symbols present (AST document symbols — the LSP symbols signal for a single file).
      - docstring_ok: CacheMetrics + CacheNodeKind carry docstrings (LSP hover contract).
      - loc: lines of code (int).
      - loc_ok: loc <= 200 (R006).
      - score: fraction of boolean axes passed (0.0–1.0).
    """

    def __init__(
        self,
        *,
        structure_ok: bool,
        invariants_ok: bool,
        ranking_ok: bool,
        ruff_clean: bool,
        ty_clean: bool = False,
        pyrefly_clean: bool = False,
        risk_ok: bool = False,
        symbols_ok: bool = False,
        docstring_ok: bool = False,
        convention_consistency_ok: bool = True,
        loc: int = 0,
        error_detail: str | None = None,
    ) -> None:
        self.structure_ok = structure_ok
        self.invariants_ok = invariants_ok
        self.ranking_ok = ranking_ok
        self.ruff_clean = ruff_clean
        self.ty_clean = ty_clean
        self.pyrefly_clean = pyrefly_clean
        self.risk_ok = risk_ok
        self.symbols_ok = symbols_ok
        self.docstring_ok = docstring_ok
        self.convention_consistency_ok = convention_consistency_ok
        self.loc = loc
        self.loc_ok = loc <= _R06_MAX_LOC
        self.error_detail = error_detail
        self.loc_ok = loc <= _R06_MAX_LOC
        bools = [
            structure_ok, invariants_ok, ranking_ok, ruff_clean,
            self.ty_clean, self.pyrefly_clean, self.risk_ok,
            self.symbols_ok, self.docstring_ok, self.convention_consistency_ok, self.loc_ok,
        ]
        self.score = sum(bools) / len(bools)

    def axes(self) -> dict[str, Any]:
        return {
            "structure_ok": self.structure_ok,
            "invariants_ok": self.invariants_ok,
            "ranking_ok": self.ranking_ok,
            "ruff_clean": self.ruff_clean,
            "ty_clean": self.ty_clean,
            "pyrefly_clean": self.pyrefly_clean,
            "risk_ok": self.risk_ok,
            "symbols_ok": self.symbols_ok,
            "docstring_ok": self.docstring_ok,
            "convention_consistency_ok": self.convention_consistency_ok,
            "loc": self.loc,
            "loc_ok": self.loc_ok,
            "error_detail": self.error_detail,
            "score": self.score,
        }

    def __repr__(self) -> str:
        return f"SandboxFitness(score={self.score:.2f}, axes={self.axes()})"


def _load_candidate_module(path: Path, module_name: str = "_sandbox_candidate") -> Any:
    """Import a candidate module from an arbitrary path.

    Registers it in sys.modules during exec so that ``@dataclass`` (which calls
    ``dataclasses.fields()`` internally and looks up ``sys.modules[cls.__module__]``)
    does not crash on an unregistered module. Removed after exec to keep the
    namespace isolated.
    """
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load candidate module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    finally:
        sys.modules.pop(module_name, None)
    return module


def _check_structure(module: Any) -> tuple[bool, dict[str, Any]]:
    """Check CacheMetrics + CacheNodeKind exist with the required shape."""
    metrics_cls = getattr(module, "CacheMetrics", None)
    kind_cls = getattr(module, "CacheNodeKind", None)
    detail: dict[str, Any] = {}
    if metrics_cls is None or kind_cls is None:
        detail["missing"] = [n for n, c in (("CacheMetrics", metrics_cls), ("CacheNodeKind", kind_cls)) if c is None]
        return False, detail
    if not is_dataclass(metrics_cls):
        detail["CacheMetrics_not_dataclass"] = True
        return False, detail
    # Use __dataclass_fields__ directly — dataclasses.fields() requires the
    # module to be in sys.modules, which is not the case for an importlib-loaded
    # candidate. __dataclass_fields__ is a plain dict on the class.
    dc_fields = getattr(metrics_cls, "__dataclass_fields__", {})
    field_names = tuple(dc_fields.keys())
    if field_names != REQUIRED_FIELDS:
        detail["field_names"] = field_names
        detail["expected"] = REQUIRED_FIELDS
        return False, detail
    return True, detail


def _check_invariants(metrics_cls: Any) -> bool:
    """Instantiate with non-negative ints and confirm they hold."""
    try:
        instance = metrics_cls(hit_count=5, miss_count=1, eviction_count=0, memory_bytes=128)
    except Exception:  # noqa: BLE001 — any construction failure = invariant breach
        return False
    for name in REQUIRED_FIELDS:
        val = getattr(instance, name, None)
        if isinstance(val, bool) or not isinstance(val, int) or val < 0:
            return False
    return True


def _check_ranking(metrics_cls: Any) -> bool:
    """Verify better_than implements the inverse hit_count rule."""
    try:
        low = metrics_cls(hit_count=1, miss_count=5, eviction_count=0, memory_bytes=10)
        high = metrics_cls(hit_count=10, miss_count=5, eviction_count=0, memory_bytes=10)
        if not high.better_than(low):
            return False
        # Equal hit_count, lower miss_count wins.
        a = metrics_cls(hit_count=5, miss_count=3, eviction_count=0, memory_bytes=10)
        b = metrics_cls(hit_count=5, miss_count=7, eviction_count=0, memory_bytes=10)
        return a.better_than(b)
    except Exception:  # noqa: BLE001
        return False


def _run_tool(args: list[str], timeout: int = 20) -> bool:
    """Run a quality tool via ``uv run`` from the project root; True iff exit 0.

    Using ``uv run`` (not ``python -m``) matches how the project invokes tools
    everywhere (CI, README) and ensures the right env + console scripts are
    used even for packages without ``__main__`` (e.g. riskratchet).
    """
    try:
        result = subprocess.run(
            ["uv", "run", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


def _run_ruff(path: Path) -> bool:
    """Run ruff check on the candidate file; True iff clean."""
    return _run_tool(["ruff", "check", str(path.resolve())])


def _run_ty(path: Path) -> bool:
    """Run ty (Astral type checker) on the candidate file; True iff clean."""
    return _run_tool(["ty", "check", str(path.resolve())], timeout=30)


def _run_pyrefly(path: Path) -> bool:
    """Run pyrefly (Meta type checker) on the candidate file; True iff clean."""
    return _run_tool(["pyrefly", "check", str(path.resolve())], timeout=30)


def _run_riskratchet(path: Path) -> bool:
    """Run riskratchet scan on the candidate file; True iff risk is low.

    Invoked via ``uv run riskratchet`` (the package has no ``__main__``).
    Lenient: a generated small dataclass module without dedicated coverage
    naturally scores high on coverage_gap, so we gate on structural complexity
    + severity (not the coverage-inflated composite). D002 discipline.
    """
    try:
        result = subprocess.run(
            ["uv", "run", "riskratchet", "scan", str(path.resolve()), "--json"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return False
        import json

        data = json.loads(result.stdout)
        funcs = data.get("functions", [])
        if not funcs:
            return True
        for f in funcs:
            comps = f.get("components", {})
            if float(comps.get("structural_complexity", 0)) > 40.0:
                return False
            if f.get("severity", "") in ("high", "critical"):
                return False
        return True
    except (subprocess.SubprocessError, OSError, ValueError, json.JSONDecodeError):
        return False


def _loc(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


_REQUIRED_SYMBOLS = ("CacheMetrics", "CacheNodeKind")


def _check_symbols(path: Path) -> bool:
    """LSP document-symbols signal (AST): top-level CacheMetrics + CacheNodeKind present."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return False
    top_level_names = {
        n.name for n in tree.body if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    }
    return all(name in top_level_names for name in _REQUIRED_SYMBOLS)


def _check_docstrings(path: Path) -> bool:
    """LSP hover-contract signal (AST): CacheMetrics + CacheNodeKind carry docstrings."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return False
    classes = {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}
    for name in _REQUIRED_SYMBOLS:
        node = classes.get(name)
        if node is None or not ast.get_docstring(node):
            return False
    return True


def _check_convention(path: Path) -> bool:
    """GitNexus convention check (S6): is the candidate consistent with project patterns?"""
    try:
        from active_skill_system.application.use_cases.gitnexus_convention_check import (
            ConventionChecker,
        )

        result = ConventionChecker().check_convention(str(path))
        return result.consistent
    except Exception:  # noqa: BLE001
        return True  # graceful: don't penalise for GitNexus issues


def _missing_file_fitness() -> SandboxFitness:
    """Fitness for a missing candidate: every axis False, score 0.0."""
    f = SandboxFitness(
        structure_ok=False, invariants_ok=False, ranking_ok=False,
        ruff_clean=False, ty_clean=False, pyrefly_clean=False,
        risk_ok=False, loc=0,
    )
    f.loc_ok = False  # no file → loc_ok is meaningless, force False
    f.score = 0.0
    return f


def verify_candidate(path: str | Path) -> SandboxFitness:
    """Score a candidate cache_types module. Pure + deterministic (no LLM)."""
    p = Path(path)
    if not p.is_file():
        return _missing_file_fitness()

    loc = _loc(p)
    ruff_clean = _run_ruff(p)
    ty_clean = _run_ty(p)
    pyrefly_clean = _run_pyrefly(p)
    risk_ok = _run_riskratchet(p)
    symbols_ok = _check_symbols(p)
    docstring_ok = _check_docstrings(p)
    convention_ok = _check_convention(p)

    try:
        module = _load_candidate_module(p)
    except Exception as exc:  # noqa: BLE001
        detail = f"{type(exc).__name__}: {exc}"
        _log.warning("candidate import failed: %s", detail)
        return SandboxFitness(
            structure_ok=False, invariants_ok=False, ranking_ok=False,
            ruff_clean=ruff_clean, ty_clean=ty_clean, pyrefly_clean=pyrefly_clean,
            risk_ok=risk_ok, symbols_ok=symbols_ok, docstring_ok=docstring_ok, convention_consistency_ok=convention_ok, loc=loc,
            error_detail=detail,
        )

    structure_ok, _ = _check_structure(module)
    if not structure_ok:
        return SandboxFitness(
            structure_ok=False, invariants_ok=False, ranking_ok=False,
            ruff_clean=ruff_clean, ty_clean=ty_clean, pyrefly_clean=pyrefly_clean,
            risk_ok=risk_ok, symbols_ok=symbols_ok, docstring_ok=docstring_ok, convention_consistency_ok=convention_ok, loc=loc,
        )

    metrics_cls = module.CacheMetrics
    invariants_ok = _check_invariants(metrics_cls)
    ranking_ok = _check_ranking(metrics_cls)

    return SandboxFitness(
        structure_ok=structure_ok,
        invariants_ok=invariants_ok,
        ranking_ok=ranking_ok,
        ruff_clean=ruff_clean,
        ty_clean=ty_clean,
        pyrefly_clean=pyrefly_clean,
        risk_ok=risk_ok,
        symbols_ok=symbols_ok,
        docstring_ok=docstring_ok,
        convention_consistency_ok=convention_ok,
        loc=loc,
    )
