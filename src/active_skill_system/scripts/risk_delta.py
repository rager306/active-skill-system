"""Risk-delta utility (R013).

Computes the per-function risk-score delta between a committed baseline
(``.riskratchet.json``) and a fresh ``riskratchet scan --json`` run, so the
slice/milestone-completion process can record a reproducible maintainability
signal in ``SUMMARY.md``.

Split into two layers so the core is unit-testable without subprocess/CLI:

  * ``compute_risk_delta(baseline, scan, top_n=3)`` — pure function
    (dict-in, dict-out, stdlib only). Matches functions by ``(path, qualname)``
    and classifies each as an increase, a decrease, added, or removed.
  * ``run_risk_delta(...)`` — thin orchestrator: reads the baseline file, runs
    ``riskratchet scan --json`` via subprocess, parses JSON, and delegates to
    the pure function. Intended for CI / completion hooks.

Returned shape::

    {
      "increases": [{"path","qualname","before","after","delta"}, ...],  # delta>0
      "decreases": [...],                                                 # delta<0
      "added":    [{"path","qualname","score"}, ...],                     # in scan, not baseline
      "removed":  [{"path","qualname","score"}, ...],                     # in baseline, not scan
    }

Each list is sorted by absolute magnitude (worst first) and truncated to
``top_n``.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


def _key(entry: dict) -> tuple[str, str]:
    """Identity key for a function entry: (path, qualname)."""
    return (entry.get("path", ""), entry.get("qualname", ""))


def compute_risk_delta(
    baseline: list[dict],
    scan: list[dict],
    *,
    top_n: int = 3,
) -> dict[str, list[dict]]:
    """Compare baseline vs scan risk-score entries by (path, qualname).

    Args:
        baseline: list of baseline entries (each needs path/qualname/score).
        scan: list of fresh-scan entries (each needs path/qualname/score).
        top_n: cap each result list to this many entries (worst first).

    Returns:
        ``{"increases": [...], "decreases": [...], "added": [...], "removed": [...]}``.
        Increases/decreases carry before/after/delta; added/removed carry score.
    """
    base_map = {_key(e): e for e in baseline}
    scan_map = {_key(e): e for e in scan}

    increases: list[dict] = []
    decreases: list[dict] = []
    for key, s_entry in scan_map.items():
        b_entry = base_map.get(key)
        if b_entry is None:
            continue  # handled as "added"
        before = float(b_entry.get("score", 0.0))
        after = float(s_entry.get("score", 0.0))
        delta = after - before
        if delta == 0:
            continue
        record = {
            "path": key[0],
            "qualname": key[1],
            "before": round(before, 2),
            "after": round(after, 2),
            "delta": round(delta, 2),
        }
        (increases if delta > 0 else decreases).append(record)

    added = [
        {"path": k[0], "qualname": k[1], "score": round(float(s.get("score", 0.0)), 2)}
        for k, s in scan_map.items()
        if k not in base_map
    ]
    removed = [
        {"path": k[0], "qualname": k[1], "score": round(float(b.get("score", 0.0)), 2)}
        for k, b in base_map.items()
        if k not in scan_map
    ]

    # Sort by magnitude (worst first) and truncate.
    increases.sort(key=lambda r: r["delta"], reverse=True)
    decreases.sort(key=lambda r: r["delta"])  # most negative first
    added.sort(key=lambda r: r["score"], reverse=True)
    removed.sort(key=lambda r: r["score"], reverse=True)

    return {
        "increases": increases[:top_n],
        "decreases": decreases[:top_n],
        "added": added[:top_n],
        "removed": removed[:top_n],
    }


def run_risk_delta(
    *,
    baseline_path: Path | str = ".riskratchet.json",
    coverage_path: Path | str = "coverage.json",
    root: Path | str = "src",
    top_n: int = 3,
    runner: list[str] | None = None,
) -> dict[str, list[dict]]:
    """Read the baseline, run ``riskratchet scan --json``, return the delta.

    Args:
        baseline_path: path to the committed ``.riskratchet.json``.
        coverage_path: path to ``coverage.json`` (written by pytest-cov).
        root: scan root passed to ``riskratchet scan``.
        top_n: cap each result list.
        runner: command prefix to invoke riskratchet (default ``["uv","run","riskratchet"]``);
            injectable for deterministic testing.

    Returns:
        The ``compute_risk_delta`` result.
    """
    cmd = list(runner) if runner is not None else ["uv", "run", "riskratchet"]
    cmd += ["scan", str(root), "--coverage", str(coverage_path), "--json"]
    proc = subprocess.run(  # noqa: S603 - argv is controlled by the caller
        cmd, capture_output=True, text=True
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"riskratchet scan failed (exit {proc.returncode}): {proc.stderr.strip()[:500]}"
        )
    report = json.loads(proc.stdout)
    scan_entries = report.get("functions", [])

    baseline = json.loads(Path(baseline_path).read_text()).get("entries", [])
    return compute_risk_delta(baseline, scan_entries, top_n=top_n)
