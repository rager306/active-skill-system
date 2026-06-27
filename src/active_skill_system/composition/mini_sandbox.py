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
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)

    from active_skill_system.composition.logging_config import configure_logging

    configure_logging()

    if args.check is not None:
        return _run_check(args.check)
    if args.model is not None:
        return _run_single_model(args.model)
    if args.models is not None:
        return _run_multi_model(args.models)
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


def _run_single_model(model: str) -> int:
    """Run one model on the benchmark; record Loop + LoopGraph provenance."""
    from active_skill_system.adapters.ladybug_graph_store import LadybugGraphStore
    from active_skill_system.adapters.llm.minimax import MiniMaxProvider
    from active_skill_system.adapters.plain_llm_strategy import PlainLLMStrategy
    from active_skill_system.application.use_cases.sandbox_agent_runner import SandboxAgentRunner
    from active_skill_system.domain.loop_graph import LoopEdgeKind, project

    engine = PlainLLMStrategy(provider=MiniMaxProvider())
    runner = SandboxAgentRunner(engine=engine)
    result = runner.run(model=model)

    # Project the Loop to LoopGraph and store provenance.
    store = LadybugGraphStore(":memory:")
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

    return 0 if result.fitness.score == 1.0 else 1


def _run_multi_model(models_csv: str) -> int:
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
    store = LadybugGraphStore(":memory:")
    # Re-run projection is not stored here (harness returns summaries); the
    # report itself is the human-readable provenance. GraphStore wiring for
    # multi-run provenance is a future enrichment.
    _ = (project, store)  # available for future graph-enrichment

    print(report.table(), flush=True)
    return 0 if report.winner_score == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
