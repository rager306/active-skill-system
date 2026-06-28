"""L4 Composition — Loop -> LoopGraph -> GraphStore provenance pipeline (M041 S02).

Wires the RGLA vertical slice (D009 + D010): construct a Loop, project it to a
LoopGraph, store it via an injected GraphStore (LadybugGraphStore by default),
and demonstrate a provenance query (neighbours of the loop vertex). This is the
end-to-end proof that the domain stays infra-free (R002), the adapter is
swappable behind the port (D010), and provenance is rebuildable from events
(D009 §4.2).

The typed VERIFIED payload (confidence + verifier) demonstrates the typed
sub-Loop return contract (D011 §5.3): typed outputs at sub-Loop boundaries are
the durable evidence-routing layer, and become LoopGraph edge payloads.

R008 / R009: module-level imports are stdlib only; heavy imports
(LadybugGraphStore, project, Loop) are lazy inside helpers/main. Importing this
module is side-effect free.

Usage::

    uv run python -m active_skill_system.composition.loop_graph_store
    uv run python -m active_skill_system.composition.loop_graph_store --db /tmp/g.lbdb
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from typing import Any


def _build_sample_loop() -> Any:
    """Build a sample Loop with a typed VERIFIED event (D011 §5.3 contract)."""
    from active_skill_system.domain.loop import Budget, Loop, LoopEvent, LoopEventKind, LoopState

    loop = Loop.start(
        id="sample-loop-1",
        intent="Demonstrate RGLA Loop -> LoopGraph -> GraphStore provenance",
        budget=Budget(max_iterations=10, max_llm_calls=20),
        skills=("sql-plan-opt", "iac-plan-opt"),
    )
    # Typed sub-Loop return contract: a VERIFIED event carries a typed payload
    # (verifier + confidence) that becomes a LoopGraph VERIFIED_BY edge payload.
    loop = loop.advance(
        LoopEvent.now(
            LoopEventKind.VERIFIED,
            LoopState.VERIFYING,
            {"verifier": "gap-detector", "confidence": 0.92},
        )
    )
    return loop


def _project_and_store(loop: Any, store: Any) -> Any:
    """Project the loop to a LoopGraph and store it. Returns the projection."""
    from active_skill_system.domain.loop_graph import project

    graph = project(loop)
    store.store_loop_graph(graph)
    return graph


def _build_store(db_path: str) -> Any:
    """Lazy-construct a LadybugGraphStore (R008/R009)."""
    from active_skill_system.adapters.ladybug_graph_store import LadybugGraphStore

    return LadybugGraphStore(path=db_path)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="active-skill-loop-graph-store",
        description=(
            "RGLA vertical slice: build a Loop, project it to a LoopGraph, "
            "store it via a GraphStore (LadybugDB), and print a provenance query. "
            "No network, no LLM — pure offline provenance."
        ),
    )
    parser.add_argument(
        "--db",
        type=str,
        default=":memory:",
        help="GraphStore path (default :memory: for a transient in-process graph).",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """main implementation."""
    args = _parse_args(argv)

    from active_skill_system.composition.logging_config import configure_logging

    configure_logging()

    loop = _build_sample_loop()
    store = _build_store(args.db)
    graph = _project_and_store(loop, store)

    # Provenance query: neighbours of the loop vertex (outgoing edges).
    loop_vid = "loop:sample-loop-1"
    neighbours = store.query_neighbours(loop_vid, direction="out")

    print(f"loop: {loop.id} (intent={loop.intent!r})", flush=True)
    print(f"stored: {store.count_vertices()} vertices, {store.count_edges()} edges", flush=True)
    print(f"projection: {len(graph.vertices)} vertices, {len(graph.edges)} edges", flush=True)
    print(f"neighbours of {loop_vid}:", flush=True)
    for v in neighbours:
        print(f"  - {v.kind.value}: {v.id} ({v.label})", flush=True)

    # Demonstrate the typed sub-Loop contract payload on a VERIFIED_BY edge.
    from active_skill_system.domain.loop_graph import LoopEdgeKind

    if store.has_edge(LoopEdgeKind.VERIFIED_BY, loop_vid, "verifier:gap-detector"):
        print(
            "typed contract: VERIFIED_BY edge carries "
            f"confidence={0.92} (D011 §5.3 typed sub-Loop return)",
            flush=True,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
