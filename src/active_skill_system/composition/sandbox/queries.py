"""L4 Composition — sandbox queries (M052 S00).

Read-only insight modes: --report, --compare-runs, --recommend.
"""

from __future__ import annotations

from active_skill_system.composition.cli_exit import EX_NOT_FOUND, EX_OK
from active_skill_system.composition.sandbox.helpers import get_sandbox_logger


def run_report(graph_path: str, ratchet_path: str | None, as_json: bool, log_dir: str | None) -> int:
    """Comprehensive insight report from accumulated graph + ratchet (M049 S01)."""
    import json as json_mod
    from pathlib import Path

    from active_skill_system.adapters.ladybug_graph_store import LadybugGraphStore
    from active_skill_system.application.use_cases.sandbox_insight_report import ReportReader
    from harness import RatchetLedger

    graph = LadybugGraphStore(graph_path)
    ratchet = None
    if ratchet_path:
        rp = Path(ratchet_path)
        if rp.exists():
            ratchet = RatchetLedger.load(rp)
    reader = ReportReader(graph=graph, ratchet=ratchet, log_dir=log_dir)
    report = reader.read()

    if as_json:
        print(json_mod.dumps(dict(report.facts()), indent=2, default=str), flush=True)
    else:
        print("=== sandbox insight report ===", flush=True)
        print(f"graph: {graph_path}", flush=True)
        print(f"ratchet: {ratchet_path or '(none)'}", flush=True)
        print(flush=True)
        sections = [
            ("Runs", [
                ("total_loops", report.total_loops),
                ("runs_with_score_1", report.runs_with_score_1),
                ("runs_with_score_lt_1", report.runs_with_score_lt_1),
                ("verifier_pass_rate", f"{report.verifier_pass_rate:.2%}"),
            ]),
            ("Graph", [
                ("total_vertices", report.total_vertices),
                ("total_edges", report.total_edges),
                ("created_edges", report.created_edges),
            ]),
            ("Models", report.model_breakdown),
            ("Trajectory", {
                "trajectory_lengths": list(report.trajectory_lengths),
                "kinds": report.trajectory_kinds,
            }),
            ("Failures", [
                ("executor_failures", report.executor_failures),
                ("ratchet_entries", report.ratchet_entries),
            ]),
            ("Skill usage", report.skill_usage),
            ("Verifier usage", report.verifier_usage),
        ]
        for title, rows in sections:
            print(f"  [{title}]", flush=True)
            if isinstance(rows, dict):
                if not rows:
                    print("    (none)", flush=True)
                for k, v in rows.items():
                    print(f"    {k}: {v}", flush=True)
            elif isinstance(rows, list) and rows and isinstance(rows[0], tuple):
                for k, v in rows:
                    print(f"    {k}: {v}", flush=True)
            else:
                print(f"    {rows}", flush=True)
    return EX_OK


def run_compare_runs(
    graph_path: str, loop_a: str, loop_b: str, as_json: bool, log_dir: str | None,
) -> int:
    """Compare two runs side-by-side (M049 S02)."""
    import json as json_mod

    from active_skill_system.adapters.ladybug_graph_store import LadybugGraphStore
    from active_skill_system.application.use_cases.sandbox_run_diff import SandboxRunDiff

    graph = LadybugGraphStore(graph_path)
    diff = SandboxRunDiff(graph=graph, log_dir=log_dir)
    cmp = diff.compare(loop_a, loop_b)
    if cmp.missing_id:
        print(f"run not found: {cmp.missing_id}", flush=True)
        get_sandbox_logger().warning("compare_runs_missing a=%s b=%s missing=%s", loop_a, loop_b, cmp.missing_id)
        return EX_NOT_FOUND
    if as_json:
        def _s(sum_: object) -> dict:
            return {
                "loop_id": sum_.loop_id,
                "score": sum_.score,
                "trajectory_kinds": sum_.trajectory_kinds,
                "trajectory_length": sum_.trajectory_length,
                "model": sum_.model,
            }
        print(json_mod.dumps({
            "loop_a": _s(cmp.loop_a),
            "loop_b": _s(cmp.loop_b),
            "kinds_only_in_a": list(cmp.kinds_only_in_a),
            "kinds_only_in_b": list(cmp.kinds_only_in_b),
            "kinds_in_both": list(cmp.kinds_in_both),
            "score_delta": cmp.score_delta,
            "length_delta": cmp.length_delta,
            "models_match": cmp.models_match,
        }, indent=2), flush=True)
    else:
        print(cmp.summary(), flush=True)
    return EX_OK


def run_recommend(
    graph_path: str, ratchet_path: str | None, as_json: bool, log_dir: str | None,
) -> int:
    """Actionable recommendations from accumulated state (M049 S03)."""
    import json as json_mod
    from pathlib import Path

    from active_skill_system.adapters.ladybug_graph_store import LadybugGraphStore
    from active_skill_system.application.use_cases.sandbox_recommender import SandboxRecommender
    from harness import RatchetLedger

    graph = LadybugGraphStore(graph_path)
    ratchet = None
    if ratchet_path:
        rp = Path(ratchet_path)
        if rp.exists():
            ratchet = RatchetLedger.load(rp)
    rec = SandboxRecommender(graph=graph, ratchet=ratchet, log_dir=log_dir).recommend()
    if as_json:
        print(json_mod.dumps([r.to_dict() for r in rec], indent=2), flush=True)
    else:
        print(f"=== recommendations ({len(rec)}) ===", flush=True)
        for r in rec:
            print(f"  [{r.confidence.upper()}] {r.kind}: {r.message}", flush=True)
            for ref in r.evidence_refs[:5]:
                print(f"    evidence: {ref}", flush=True)
    return EX_OK
