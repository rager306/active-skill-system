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
from collections.abc import Sequence
from typing import Any


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
    parser.add_argument("--graph", type=str, default="runs/sandbox_graph.lbdb",
                        help="LadybugDB graph path (default: runs/sandbox_graph.lbdb for disk persistence). Use :memory: for ephemeral.")
    parser.add_argument("--graph-query", type=str, default=None,
                        help="Execute a Cypher query on the persistent graph and print results.")
    parser.add_argument("--graph-stats", action="store_true",
                        help="Print accumulated provenance statistics from the persistent graph.")
    parser.add_argument("--ratchet", type=str, default=None,
                        help="Ratchet ledger path. If set, failed runs (fitness<1.0 or error) write permanent entries.")
    parser.add_argument("--ratchet-stats", action="store_true",
                        help="Print accumulated ratchet entries.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)

    from active_skill_system.composition.logging_config import configure_logging

    configure_logging()

    if args.ratchet_stats:
        return _run_ratchet_stats(args.ratchet or "runs/ratchet.jsonl")
    if args.graph_query is not None:
        return _run_graph_query(args.graph, args.graph_query)
    if args.graph_stats:
        return _run_graph_stats(args.graph)
    if args.check is not None:
        return _run_check(args.check)
    if args.model is not None:
        return _run_single_model(args.model, args.executor, args.graph, args.ratchet)
    if args.models is not None:
        return _run_multi_model(args.models, args.graph)
    print("nothing to do: pass --check / --model / --models", flush=True)
    return 0


def _run_check(candidate_path: str) -> int:
    from active_skill_system.application.use_cases.sandbox_verifier import verify_candidate

    fitness = verify_candidate(candidate_path)
    axes = fitness.axes()
    print(f"candidate: {candidate_path}", flush=True)
    print(f"score: {axes['score']:.2f}", flush=True)
    for name, val in axes.items():
        if name != "score":
            print(f"  {name}: {val}", flush=True)
    return 0 if axes["score"] == 1.0 else 1


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
    """Print accumulated ratchet entries."""
    from pathlib import Path

    from harness import RatchetLedger

    ledger = RatchetLedger.load(Path(ratchet_path))
    entries = ledger.entries
    print(f"ratchet: {ratchet_path} ({len(entries)} entries)", flush=True)
    for e in entries[-20:]:
        print(f"  {e.id} | {e.area} | {e.diff[:80]}", flush=True)
    return 0


def _run_graph_query(graph_path: str, cypher: str) -> int:
    """Execute a Cypher query on the persistent graph."""
    from active_skill_system.adapters.ladybug_graph_store import LadybugGraphStore

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
        return 1
    return 0


def _run_graph_stats(graph_path: str) -> int:
    """Print accumulated provenance statistics."""
    from active_skill_system.adapters.ladybug_graph_store import LadybugGraphStore

    store = LadybugGraphStore(graph_path)
    stats = [
        ("total vertices", "MATCH (v) RETURN count(v)"),
        ("total edges", "MATCH ()-[e]->() RETURN count(e)"),
        ("loop vertices", "MATCH (v) WHERE v.id STARTS WITH 'loop:' RETURN count(v)"),
        ("VERIFIED_BY edges", "MATCH ()-[e:RglaEdge {ekind: 'verified_by'}]->() RETURN count(e)"),
        ("USES edges", "MATCH ()-[e:RglaEdge {ekind: 'uses'}]->() RETURN count(e)"),
        ("LEARNS_FROM edges", "MATCH ()-[e:RglaEdge {ekind: 'learns_from'}]->() RETURN count(e)"),
        ("CREATED edges", "MATCH ()-[e:RglaEdge {ekind: 'created'}]->() RETURN count(e)"),
    ]
    print(f"graph: {graph_path}", flush=True)
    for label, query in stats:
        try:
            r = store._connection().execute(query)
            count = r.get_next()[0] if r.has_next() else 0
            print(f"  {label}: {count}", flush=True)
        except Exception:  # noqa: BLE001
            print(f"  {label}: (query failed)", flush=True)
    return 0


def _build_executor(executor_type: str):
    """Build a CodeExecutorPort adapter by type string (lazy import, R008)."""
    if executor_type == "bwrap":
        from active_skill_system.adapters.bwrap_executor import BwrapExecutor
        return BwrapExecutor()
    from active_skill_system.adapters.inprocess_executor import InProcessExecutor
    return InProcessExecutor()


def _run_single_model(model: str, executor_type: str = "inprocess", graph_path: str = "runs/sandbox_graph.lbdb", ratchet_path: str | None = None) -> int:
    """Run one model on the benchmark; record Loop + LoopGraph provenance."""
    from active_skill_system.adapters.ladybug_graph_store import LadybugGraphStore
    from active_skill_system.adapters.llm.minimax import MiniMaxProvider
    from active_skill_system.adapters.plain_llm_strategy import PlainLLMStrategy
    from active_skill_system.application.use_cases.sandbox_agent_runner import SandboxAgentRunner
    from active_skill_system.domain.loop_graph import LoopEdgeKind, project

    engine = PlainLLMStrategy(provider=MiniMaxProvider())
    code_executor = _build_executor(executor_type)
    runner = SandboxAgentRunner(engine=engine, code_executor=code_executor)
    result = runner.run(model=model)

    # Project the Loop to LoopGraph and store provenance (disk-persistent).
    store = LadybugGraphStore(graph_path)
    graph = project(result.loop)
    store.store_loop_graph(graph)

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

    return 0 if result.fitness.score == 1.0 else 1


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
    return 0 if report.winner_score == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
