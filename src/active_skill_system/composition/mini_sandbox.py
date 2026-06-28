"""L4 Composition — mini sandbox entrypoint (M042, D013 mini-loop).

Three modes:
  --check <path>     : score a candidate module deterministically (no LLM).
  --model <name>     : run ONE model on the benchmark, verify, record Loop+LoopGraph.
  --models a,b,c     : (S03) multi-model comparative run.

R008/R009: stdlib-only module-level imports; heavy imports (provider, verifier,
GraphStore) are lazy inside ``main``. Importing this module is side-effect free.

Usage::

    uv run python -m active_skill_system.composition.mini_sandbox --check \\
        tests/fixtures/sandbox/cache_full.py
    uv run python -m active_skill_system.composition.mini_sandbox --model \\
        minimax/MiniMax-M3
"""

from __future__ import annotations

import argparse
import logging
import os
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from active_skill_system.composition.cli_exit import (
    EX_NOT_FOUND,
    EX_OK,
    EX_PARTIAL,
    EX_USAGE,
)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="active-skill-mini-sandbox",
        description=(
            "D013 mini-loop sandbox. --check scores deterministically; "
            "--model runs one LLM; --models runs many (S03)."
        ),
    )
    parser.add_argument("--check", type=str, default=None, help="Score a candidate module (no LLM).")
    parser.add_argument("--model", type=str, default=None, help="Run ONE model on the benchmark.")
    parser.add_argument("--models", type=str, default=None, help="(S03) Comma-separated model list.")
    parser.add_argument("--executor", type=str, default="inprocess", choices=("inprocess", "bwrap"),
                        help="Code executor for LLM-generated code: inprocess (tests) or bwrap (isolated).")
    _default_graph = os.environ.get("SANDBOX_GRAPH_PATH", "runs/sandbox_graph.lbdb")
    parser.add_argument("--graph", type=str, default=_default_graph,
                        help=f"LadybugDB graph path (default: {_default_graph} for disk persistence). Use :memory: for ephemeral.")
    _default_ratchet = os.environ.get("SANDBOX_RATCHET_PATH", "runs/ratchet.jsonl")
    parser.add_argument("--ratchet", type=str, default=_default_ratchet,
                        help=f"Ratchet ledger path (default: {_default_ratchet}). Failed runs write permanent entries.")
    parser.add_argument("--graph-query", type=str, default=None,
                        help="Execute a Cypher query on the persistent graph and print results.")
    parser.add_argument("--graph-stats", action="store_true",
                        help="Print accumulated provenance statistics from the persistent graph.")
    parser.add_argument("--report", action="store_true",
                        help="Print a comprehensive insight report over the accumulated graph + ratchet + logs (M049 S01).")
    parser.add_argument("--json", action="store_true",
                        help="With --report or --compare-runs, output JSON instead of human-readable.")
    parser.add_argument("--compare-runs", nargs=2, metavar=("ID_A", "ID_B"), default=None,
                        help="Compare two runs side-by-side (score, length, model, trajectory kind diff).")
    parser.add_argument("--recommend", action="store_true",
                        help="Print actionable recommendations derived from the accumulated graph + ratchet + logs (M049 S03).")
    parser.add_argument("--graph-trajectory", action="store_true",
                        help="Print the trajectory chain (TRAJECTORY_STEP vertices with NEXT edges) from the persistent graph.")
    parser.add_argument("--ratchet-stats", action="store_true",
                        help="Print accumulated ratchet entries.")
    parser.add_argument("--strategy", type=str, default="plain",
                        choices=("plain", "dspy", "fast-rlm"),
                        help="Reasoning strategy: plain (M043), dspy (M051), fast-rlm (M052).")
    parser.add_argument("--bench", type=str, default=None, choices=("cache-types", "program-bench"),
                        help="Benchmark to run (M042 cache_types or M053 program-bench smallest-CLI).")
    parser.add_argument("--event-log", type=str, default=None,
                        help="Event audit-trail backend (M051 S03). 'sqlite:<path>' for disk, 'inmemory' for ephemeral, or unset to disable.")
    parser.add_argument("--event-stats", action="store_true",
                        help="Print accumulated event counts from the event audit trail.")
    parser.add_argument("--governance-check", action="store_true",
                        help="Run self-governance: apply our own verification tools to our own codebase (recursive dogfooding).")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)

    # Load .env so SANDBOX_GRAPH_PATH / SANDBOX_RATCHET_PATH / SANDBOX_LOG_DIR
    # are available without manual `source .env`.
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    from active_skill_system.composition.logging_config import configure_logging

    configure_logging()

    # Per-session sandbox log file (M049 cross-session log persistence).
    sandbox_logger = _get_sandbox_logger()
    sandbox_logger.info("session_start model=%s executor=%s graph=%s", args.model, args.executor, args.graph)

    if args.ratchet_stats:
        return _run_ratchet_stats(args.ratchet or "runs/ratchet.jsonl")
    if args.graph_trajectory:
        return _run_graph_trajectory(args.graph)
    if args.graph_query is not None:
        return _run_graph_query(args.graph, args.graph_query)
    if args.graph_stats:
        return _run_graph_stats(args.graph)
    if args.report:
        return _run_report(args.graph, args.ratchet, args.json, os.environ.get("SANDBOX_LOG_DIR"))
    if args.compare_runs is not None:
        return _run_compare_runs(args.graph, args.compare_runs[0], args.compare_runs[1], args.json, os.environ.get("SANDBOX_LOG_DIR"))
    if args.recommend:
        return _run_recommend(args.graph, args.ratchet, args.json, os.environ.get("SANDBOX_LOG_DIR"))
    if args.event_stats:
        return _run_event_stats(args.event_log or os.environ.get("SANDBOX_EVENT_LOG", ""))
    if args.governance_check:
        return _run_governance_check()
    if args.check is not None:
        return _run_check(args.check)
    if args.model is not None:
        if args.bench == "program-bench":
            return _run_program_bench(args.model, args.executor, args.graph, args.ratchet, args.strategy)
        event_store = _build_event_store(args.event_log or os.environ.get("SANDBOX_EVENT_LOG"))
        return _run_single_model(args.model, args.executor, args.graph, args.ratchet, args.strategy, event_store)
    if args.models is not None:
        return _run_multi_model(args.models, args.graph)
    print("nothing to do: pass --check / --model / --models", flush=True)
    return EX_USAGE


def _run_program_bench(
    model: str, executor_type: str, graph_path: str, ratchet_path: str | None, strategy: str,
) -> int:
    """ProgramBench smallest-CLI validator (M053 S01, D014).

    Reads the fixture spec from tests/fixtures/program_bench/smallest_cli/,
    asks the LLM to regenerate json_pretty.py from a brief spec, then runs
    the parity tests against the LLM-generated candidate.
    """
    import subprocess

    from active_skill_system.adapters.ladybug_graph_store import LadybugGraphStore
    from active_skill_system.adapters.llm.minimax import MiniMaxProvider
    from active_skill_system.adapters.plain_llm_strategy import PlainLLMStrategy
    from active_skill_system.application.ports.reasoning_engine import ReasoningRequest
    from active_skill_system.domain.loop_graph import project

    fixture_root = Path("tests/fixtures/program_bench/smallest_cli")
    target = fixture_root / "json_pretty.py"
    parity_tests = fixture_root / "tests" / "test_json_pretty_parity.py"
    if not target.exists() or not parity_tests.exists():
        print(f"program_bench: fixture missing at {fixture_root}", flush=True)
        return EX_NOT_FOUND

    # Read the reference impl as hidden spec; build the user-facing spec.
    spec = (
        "Write a Python CLI named 'json_pretty' that pretty-prints JSON. "
        "Requirements: (1) read JSON from a file path argument or stdin if no path "
        "is given, (2) --indent N sets indent width (default 2), (3) --sort-keys sorts "
        "object keys alphabetically (off by default), (4) --indent 0 produces compact "
        "output (no whitespace), (5) exit 0 on success, exit 1 with a stderr message "
        "on invalid JSON. Use only the Python standard library. Output only the code."
    )

    # Use the requested strategy.
    if strategy == "dspy":
        from active_skill_system.adapters.dspy_strategy import DSPyStrategy

        engine = DSPyStrategy()
    elif strategy == "fast-rlm":
        from active_skill_system.adapters.fast_rlm_strategy import FastRLMStrategy

        engine = FastRLMStrategy()
    else:
        engine = PlainLLMStrategy(provider=MiniMaxProvider())

    request = ReasoningRequest(
        system="You are a Python code generator. Output only code.",
        prompt=spec,
        model=model,
        max_tokens=16384,
        temperature=0.0,
    )
    response = engine.forward(request)
    if response.error:
        print(f"program_bench: reasoning failed: {response.error}", flush=True)
        return EX_PARTIAL
    raw = response.text or ""
    # Reuse the existing _extract_code from sandbox_agent_runner.
    from active_skill_system.application.use_cases.sandbox_agent_runner import _extract_code

    code = _extract_code(raw)
    if not code.strip():
        print("program_bench: empty candidate", flush=True)
        return EX_PARTIAL

    # Write the candidate into runs/program_bench/<run_id>/json_pretty.py.
    import sys
    import uuid

    run_id = f"program-bench-{uuid.uuid4().hex[:8]}"
    out_dir = Path("runs/program_bench") / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    candidate = out_dir / "json_pretty.py"
    candidate.write_text(code, encoding="utf-8")
    print(f"program_bench: candidate written to {candidate}", flush=True)

    # Run the parity tests against the candidate. We copy the tests to out_dir
    # and patch the _CLI reference so it points at the LLM-generated candidate.
    parity_runner = out_dir / "test_parity.py"
    runner_src = parity_tests.read_text(encoding="utf-8")
    runner_src = runner_src.replace(
        "_FIXTURE_DIR = Path(__file__).resolve().parents[1]",
        f"_FIXTURE_DIR = Path({str(candidate)!r}).parent",
    )
    parity_runner.write_text(runner_src, encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(parity_runner), "-q", "-p", "no:cacheprovider"],
        capture_output=True, text=True, timeout=60,
    )
    print(proc.stdout, flush=True)
    if proc.returncode != 0:
        print(proc.stderr, flush=True)
        return EX_PARTIAL

    # Persist a synthetic Loop into the graph so --report/--recommend pick it up.
    from active_skill_system.domain.loop import Budget, Loop, LoopEvent, LoopEventKind, LoopState

    loop = Loop.start(
        id=run_id,
        intent=f"program-bench:{model}",
        budget=Budget(max_llm_calls=1, max_cost=0.05),
        skills=("program-bench",),
    )
    loop = loop.advance(LoopEvent.now(LoopEventKind.VERIFIED, LoopState.VERIFYING, {"verifier": "program-bench-parity"}))
    loop = loop.advance(LoopEvent.now(LoopEventKind.FINISHED, LoopState.DONE, {"score": 1.0}))
    store = LadybugGraphStore(graph_path)
    store.store_loop_graph(project(loop))

    _get_sandbox_logger().info(
        "program_bench_passed run_id=%s model=%s score=1.0",
        run_id, model,
    )
    return EX_OK


def _run_governance_check() -> int:
    """Self-governance check: apply our own tools to our own codebase."""
    from active_skill_system.application.use_cases.self_governance_check import (
        run_governance_check,
    )

    result = run_governance_check()
    print(f"=== governance check (score {result.score:.2%}) ===", flush=True)
    for name, ok in result.axes.items():
        status = "OK" if ok else "FAIL"
        detail = result.details.get(name, "")[:120]
        print(f"  {name}: {status}  {detail}", flush=True)
    if result.all_passed:
        return EX_OK
    failed = result.failed_axes()
    _get_sandbox_logger().warning(
        "governance_check_failed score=%.2f axes_failed=%s",
        result.score, failed,
    )
    return EX_PARTIAL


def _build_event_store(spec: str | None):
    """Build an EventStore from a --event-log spec (M051 S03).

    Accepts:
      - None / empty → None (event trail disabled)
      - 'inmemory' → InMemoryEventLog (ephemeral)
      - 'sqlite:<path>' or 'sqlite:///<path>' → SQLiteEventLog (disk)
    Returns an EventStoreImpl or None.
    """
    if not spec:
        return None
    from active_skill_system.adapters.event_store_impl import EventStoreImpl

    if spec == "inmemory":
        from active_skill_system.adapters.inmemory_event_log import InMemoryEventLog

        return EventStoreImpl(InMemoryEventLog())
    if spec.startswith("sqlite"):
        from active_skill_system.adapters.sqlite_event_log import SQLiteEventLog

        # Normalise 'sqlite:runs/events.db' → 'runs/events.db'
        path = spec.split(":", 1)[1] if ":" in spec else spec
        if path.startswith("///"):
            path = path[3:]
        elif path.startswith("//"):
            path = path[2:]
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        return EventStoreImpl(SQLiteEventLog(path))
    print(f"event-log: unknown spec {spec!r} (use 'inmemory' or 'sqlite:<path>')", flush=True)
    return None


def _run_event_stats(spec: str) -> int:
    """Print accumulated event counts from the event audit trail."""
    from collections import Counter

    store = _build_event_store(spec)
    if store is None:
        print("event-log: disabled (pass --event-log sqlite:<path>)", flush=True)
        return EX_OK
    events = list(store.iter_events())
    print(f"event-log: {spec} ({len(events)} events)", flush=True)
    by_type: Counter[str] = Counter(e.type for e in events)
    for etype, count in by_type.most_common():
        print(f"  {etype}: {count}", flush=True)
    return EX_OK


def _run_check(candidate_path: str) -> int:
    from active_skill_system.application.use_cases.sandbox_verifier import verify_candidate

    fitness = verify_candidate(candidate_path)
    axes = fitness.axes()
    print(f"candidate: {candidate_path}", flush=True)
    print(f"score: {axes['score']:.2f}", flush=True)
    for name, val in axes.items():
        if name != "score":
            print(f"  {name}: {val}", flush=True)
    return EX_OK if axes["score"] == 1.0 else EX_PARTIAL


def _write_ratchet_entry(ratchet_path: str, result: Any) -> None:
    """Write a permanent ratchet entry for a failed sandbox run (D012 dogfood)."""
    from pathlib import Path

    from harness import RatchetEntry, RatchetLedger

    error_detail = result.error or f"fitness={result.fitness.score:.2f}"
    axes = result.fitness.axes()
    failed_axes = [k for k, v in axes.items() if isinstance(v, bool) and not v and k != "score"]
    entry = RatchetEntry.new(
        area="sandbox",
        diff=f"model={result.model} score={result.fitness.score:.2f} failed_axes={failed_axes}",
        justification=f"Sandbox run failed: {error_detail}",
        test_ref=result.generated_path or "unknown",
    )
    ledger = RatchetLedger.load(Path(ratchet_path))
    ledger.append(entry)
    print(f"ratchet: entry written to {ratchet_path} ({entry.id})", flush=True)


def _run_ratchet_stats(ratchet_path: str) -> int:
    """Print accumulated ratchet entries.

    Exit codes:
      EX_OK        — file exists (even if empty)
      EX_NOT_FOUND — file does not exist (distinct from empty)
    """
    from pathlib import Path

    from harness import RatchetLedger

    p = Path(ratchet_path)
    if not p.exists():
        print(f"ratchet: {ratchet_path} (NOT FOUND)", flush=True)
        _get_sandbox_logger().warning(
            "ratchet_not_found path=%s", ratchet_path,
        )
        return EX_NOT_FOUND
    ledger = RatchetLedger.load(p)
    entries = ledger.entries
    print(f"ratchet: {ratchet_path} ({len(entries)} entries)", flush=True)
    for e in entries[-20:]:
        print(f"  {e.id} | {e.area} | {e.diff[:80]}", flush=True)
    return EX_OK


_sandbox_logger: logging.Logger | None = None


def _get_sandbox_logger() -> logging.Logger:
    """Lazy module-level sandbox session logger (M049)."""
    global _sandbox_logger
    if _sandbox_logger is not None:
        return _sandbox_logger
    log_dir = Path(os.environ.get("SANDBOX_LOG_DIR", "logs/sandbox"))
    log_dir.mkdir(parents=True, exist_ok=True)
    session_ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    sandbox_log_path = log_dir / f"sandbox-{session_ts}.log"
    logger = logging.getLogger("sandbox.session")
    if not any(
        isinstance(h, logging.FileHandler)
        and getattr(h, "baseFilename", "") == str(sandbox_log_path)
        for h in logger.handlers
    ):
        fh = logging.FileHandler(sandbox_log_path, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)sZ %(levelname)s %(message)s"))
        logger.addHandler(fh)
        logger.setLevel(logging.INFO)
    print(f"sandbox log: {sandbox_log_path}", flush=True)
    _sandbox_logger = logger
    return logger


def _run_graph_trajectory(graph_path: str) -> int:
    """Print the trajectory chain from the persistent graph (Wave 2 P1).

    Exit codes:
      EX_OK         — chain printed (or 'no trajectory steps yet' if empty)
      EX_PARTIAL    — Cypher failed
      EX_NOT_FOUND  — graph file does not exist
    """
    from pathlib import Path

    from active_skill_system.adapters.ladybug_graph_store import LadybugGraphStore

    p = Path(graph_path)
    if not p.exists() and graph_path != ":memory:":
        print(f"graph not found: {graph_path}", flush=True)
        _get_sandbox_logger().warning("graph_not_found path=%s", graph_path)
        return EX_NOT_FOUND
    store = LadybugGraphStore(graph_path)
    query = (
        "MATCH (l:RglaVertex)-[u:RglaEdge {ekind: 'uses'}]->(s:RglaVertex) "
        "WHERE s.id STARTS WITH 'trajectory_step:' "
        "RETURN l.id, s.id, s.label"
    )
    print(f"graph: {graph_path} (trajectory)", flush=True)
    try:
        r = store._connection().execute(query)
        rows: list[tuple] = []
        while r.has_next():
            rows.append(r.get_next())
    except Exception as e:  # noqa: BLE001
        print(f"query error: {e}", flush=True)
        _get_sandbox_logger().warning("trajectory_query_failed path=%s err=%s", graph_path, e)
        return EX_PARTIAL
    if not rows:
        print("  no trajectory steps persisted yet", flush=True)
        return EX_OK
    by_loop: dict[str, list[tuple]] = {}
    for loop_id, step_id, label in rows:
        by_loop.setdefault(loop_id, []).append((step_id, label))
    for loop_id, steps in sorted(by_loop.items()):
        steps.sort(key=lambda t: t[0])
        print(f"\n  {loop_id}:", flush=True)
        for step_id, label in steps:
            print(f"    {step_id}  {label or '?'}", flush=True)
    return EX_OK


def _run_recommend(
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


def _run_compare_runs(
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
        _get_sandbox_logger().warning(
            "compare_runs_missing a=%s b=%s missing=%s", loop_a, loop_b, cmp.missing_id,
        )
        return EX_NOT_FOUND
    if as_json:
        # Build JSON-safe dict.
        def _s(sum_: object) -> dict:
            return {
                "loop_id": sum_.loop_id,  # type: ignore[attr-defined]
                "score": sum_.score,  # type: ignore[attr-defined]
                "trajectory_kinds": sum_.trajectory_kinds,  # type: ignore[attr-defined]
                "trajectory_length": sum_.trajectory_length,  # type: ignore[attr-defined]
                "model": sum_.model,  # type: ignore[attr-defined]
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


def _run_report(graph_path: str, ratchet_path: str | None, as_json: bool, log_dir: str | None) -> int:
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
        # InsightReport.facts() returns ordered (label, value) pairs.
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


def _run_graph_query(graph_path: str, cypher: str) -> int:
    """Execute a Cypher query on the persistent graph.

    Exit codes:
      EX_OK         — query executed (0 rows is success, not error)
      EX_PARTIAL    — query failed (Cypher error)
      EX_NOT_FOUND  — graph file does not exist
    """
    from pathlib import Path

    from active_skill_system.adapters.ladybug_graph_store import LadybugGraphStore

    p = Path(graph_path)
    if not p.exists() and graph_path != ":memory:":
        print(f"graph not found: {graph_path}", flush=True)
        _get_sandbox_logger().warning("graph_not_found path=%s cypher=%s", graph_path, cypher)
        return EX_NOT_FOUND
    store = LadybugGraphStore(graph_path)
    try:
        result = store._connection().execute(cypher)
        rows = []
        while result.has_next():
            rows.append(result.get_next())
        print(f"query: {cypher}", flush=True)
        print(f"rows: {len(rows)}", flush=True)
        for row in rows[:20]:
            print(f"  {row}", flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"query error: {e}", flush=True)
        _get_sandbox_logger().warning("cypher_failed path=%s err=%s", graph_path, e)
        return EX_PARTIAL
    return EX_OK


def _run_graph_stats(graph_path: str) -> int:
    """Print accumulated provenance statistics.

    Exit codes:
      EX_OK         — stats computed (0 values are success on empty graph)
      EX_NOT_FOUND  — graph file does not exist
    """
    from pathlib import Path

    from active_skill_system.adapters.ladybug_graph_store import LadybugGraphStore

    p = Path(graph_path)
    if not p.exists() and graph_path != ":memory:":
        print(f"graph not found: {graph_path}", flush=True)
        _get_sandbox_logger().warning("graph_not_found path=%s", graph_path)
        return EX_NOT_FOUND
    store = LadybugGraphStore(graph_path)
    stats = [
        ("total vertices", "MATCH (v) RETURN count(v)"),
        ("total edges", "MATCH ()-[e]->() RETURN count(e)"),
        ("loop vertices", "MATCH (v) WHERE v.id STARTS WITH 'loop:' RETURN count(v)"),
        ("VERIFIED_BY edges", "MATCH ()-[e:RglaEdge {ekind: 'verified_by'}]->() RETURN count(e)"),
        ("USES edges", "MATCH ()-[e:RglaEdge {ekind: 'uses'}]->() RETURN count(e)"),
        ("LEARNS_FROM edges", "MATCH ()-[e:RglaEdge {ekind: 'learns_from'}]->() RETURN count(e)"),
        ("CREATED edges", "MATCH ()-[e:RglaEdge {ekind: 'created'}]->() RETURN count(e)"),
        ("trajectory steps", "MATCH (v:RglaVertex) WHERE v.id STARTS WITH 'trajectory_step:' RETURN count(v)"),
        ("NEXT edges", "MATCH ()-[e:RglaEdge {ekind: 'next'}]->() RETURN count(e)"),
    ]
    print(f"graph: {graph_path}", flush=True)
    failures = 0
    for label, query in stats:
        try:
            r = store._connection().execute(query)
            count = r.get_next()[0] if r.has_next() else 0
            print(f"  {label}: {count}", flush=True)
        except Exception:  # noqa: BLE001
            print(f"  {label}: (query failed)", flush=True)
            failures += 1
    if failures:
        _get_sandbox_logger().warning(
            "graph_stats_partial path=%s failed_queries=%d", graph_path, failures,
        )
        return EX_PARTIAL
    return EX_OK


def _build_executor(executor_type: str):
    """Build a CodeExecutorPort adapter by type string (lazy import, R008)."""
    if executor_type == "bwrap":
        from active_skill_system.adapters.bwrap_executor import BwrapExecutor
        return BwrapExecutor()
    from active_skill_system.adapters.inprocess_executor import InProcessExecutor
    return InProcessExecutor()


def _run_single_model(
    model: str, executor_type: str = "inprocess",
    graph_path: str = "runs/sandbox_graph.lbdb",
    ratchet_path: str | None = None,
    strategy: str = "plain",
    event_store=None,
) -> int:
    """Run one model on the benchmark; record Loop + LoopGraph provenance."""
    from active_skill_system.adapters.ladybug_graph_store import LadybugGraphStore
    from active_skill_system.adapters.llm.minimax import MiniMaxProvider
    from active_skill_system.adapters.plain_llm_strategy import PlainLLMStrategy
    from active_skill_system.application.use_cases.sandbox_agent_runner import SandboxAgentRunner
    from active_skill_system.domain.loop_graph import LoopEdgeKind, project

    if strategy == "dspy":
        from active_skill_system.adapters.dspy_strategy import DSPyStrategy

        engine = DSPyStrategy()
        if engine.is_stub:
            print(f"dspy_strategy: stub mode ({engine.stub_reason}); falling back to plain", flush=True)
            engine = PlainLLMStrategy(provider=MiniMaxProvider())
        else:
            print(f"dspy_strategy: configured (model={engine._dspy_lm.model})", flush=True)
    elif strategy == "fast-rlm":
        from active_skill_system.adapters.fast_rlm_strategy import FastRLMStrategy

        engine = FastRLMStrategy()
        if engine.is_stub:
            print(f"fast_rlm_strategy: stub mode ({engine.stub_reason}); falling back to plain", flush=True)
            engine = PlainLLMStrategy(provider=MiniMaxProvider())
        else:
            print(f"fast_rlm_strategy: configured (primary={engine._resolved_primary})", flush=True)
    else:
        engine = PlainLLMStrategy(provider=MiniMaxProvider())
    code_executor = _build_executor(executor_type)
    runner = SandboxAgentRunner(engine=engine, code_executor=code_executor)
    result = runner.run(model=model)

    # Project the Loop to LoopGraph and store provenance (disk-persistent).
    store = LadybugGraphStore(graph_path)
    graph = project(result.loop, trajectory=result.trajectory)
    store.store_loop_graph(graph)

    # Per-run structured log entry (M049).
    _get_sandbox_logger().info(
        "run_complete run_id=%s model=%s score=%.2f trajectory_steps=%d generated=%s error=%s",
        result.loop.id, result.model, result.fitness.score,
        len(result.trajectory), result.generated_path or "none", result.error or "none",
    )

    # Emit trajectory events to the audit trail (M051 S03, additive).
    if event_store is not None and result.trajectory:
        from active_skill_system.application.use_cases.emit_trajectory_events import (
            emit_trajectory_events,
        )

        n = emit_trajectory_events(
            steps=result.trajectory, store=event_store, run_id=result.loop.id,
        )
        print(f"event-log: emitted {n} events for {result.loop.id}", flush=True)

    print(f"model: {result.model}", flush=True)
    print(f"loop: {result.loop.id} state={result.loop.state.value}", flush=True)
    print(f"score: {result.fitness.score:.2f}", flush=True)
    axes = result.fitness.axes()
    for name, val in axes.items():
        if name != "score":
            print(f"  {name}: {val}", flush=True)
    if result.error:
        print(f"error: {result.error}", flush=True)
    if result.generated_path:
        print(f"generated: {result.generated_path}", flush=True)
    # Provenance summary.
    loop_vid = f"loop:{result.loop.id}"
    neighbours = store.query_neighbours(loop_vid, direction="out")
    print(f"provenance: {len(graph.vertices)} vertices, {len(graph.edges)} edges", flush=True)
    print(f"  {loop_vid} -> {[v.id for v in neighbours]}", flush=True)
    verified = store.has_edge(LoopEdgeKind.VERIFIED_BY, loop_vid, "verifier:sandbox-verifier")
    print(f"  VERIFIED_BY verifier: {verified}", flush=True)

    # D012 dogfood: write ratchet entry if run failed (fitness < 1.0 or error).
    if ratchet_path and (result.fitness.score < 1.0 or result.error):
        _write_ratchet_entry(ratchet_path, result)

    return EX_OK if result.fitness.score == 1.0 else EX_PARTIAL


def _run_multi_model(models_csv: str, graph_path: str = "runs/sandbox_graph.lbdb") -> int:
    """Run the benchmark across N models; print comparative report + reader query."""
    from active_skill_system.adapters.ladybug_graph_store import LadybugGraphStore
    from active_skill_system.adapters.llm.minimax import MiniMaxProvider
    from active_skill_system.adapters.plain_llm_strategy import PlainLLMStrategy
    from active_skill_system.application.use_cases.sandbox_harness import SandboxHarness
    from active_skill_system.domain.loop_graph import project

    models = [m.strip() for m in models_csv.split(",") if m.strip()]
    engine = PlainLLMStrategy(provider=MiniMaxProvider())
    harness = SandboxHarness(engine=engine, models=models)
    report = harness.run_all()

    # Store all Loops' LoopGraph provenance in one store.
    store = LadybugGraphStore(graph_path)
    # Re-run projection is not stored here (harness returns summaries); the
    # report itself is the human-readable provenance. GraphStore wiring for
    # multi-run provenance is a future enrichment.
    _ = (project, store)  # available for future graph-enrichment

    print(report.table(), flush=True)
    return EX_OK if report.winner_score == 1.0 else EX_PARTIAL


if __name__ == "__main__":
    raise SystemExit(main())
