"""Regression: golden-master snapshots for LoopGraph provenance (M045 S03).

Golden-master pattern: snapshot the LoopGraph structure (vertex kinds, edge
kinds+endpoints) for a canonical Loop. Any change to project() that alters the
provenance graph is caught as a regression. The expected dict is inline —
intentional changes require updating the golden (explicit decision).
"""

from __future__ import annotations

from active_skill_system.domain.loop import (
    Budget,
    Loop,
    LoopEvent,
    LoopEventKind,
    LoopState,
)
from active_skill_system.domain.loop_graph import project


def _canonical_loop() -> Loop:
    """A canonical Loop with skills + a VERIFIED event — the golden reference."""
    loop = Loop.start(
        id="golden-loop",
        intent="golden reference",
        budget=Budget(max_iterations=5, max_llm_calls=10),
        skills=("skill-a", "skill-b"),
    )
    loop = loop.advance(
        LoopEvent.now(
            LoopEventKind.VERIFIED,
            LoopState.VERIFYING,
            {"verifier": "golden-verifier", "confidence": 0.9},
        )
    )
    return loop


def _graph_signature(graph) -> dict:
    """Extract a comparable signature from a LoopGraph (kinds+endpoints, not objects)."""
    return {
        "vertices": sorted((v.kind.value, v.id, v.label) for v in graph.vertices),
        "edges": sorted((e.kind.value, e.src, e.dst) for e in graph.edges),
    }


# ── Golden master ─────────────────────────────────────────────────────

GOLDEN_LOOP_GRAPH = {
    "vertices": [
        ("intent", "intent:golden-loop", "golden reference"),
        ("loop", "loop:golden-loop", "golden-loop"),
        ("skill", "skill:skill-a", "skill-a"),
        ("skill", "skill:skill-b", "skill-b"),
        ("verifier", "verifier:golden-verifier", "golden-verifier"),
    ],
    "edges": [
        ("created", "intent:golden-loop", "loop:golden-loop"),
        ("uses", "loop:golden-loop", "skill:skill-a"),
        ("uses", "loop:golden-loop", "skill:skill-b"),
        ("verified_by", "loop:golden-loop", "verifier:golden-verifier"),
    ],
}


def test_golden_master_loop_graph_structure():
    """LoopGraph projection of the canonical Loop matches the golden snapshot.

    If this fails, project() changed the provenance structure. Update the
    golden ONLY if the change is intentional (and document why).
    """
    loop = _canonical_loop()
    graph = project(loop)
    actual = _graph_signature(graph)
    assert actual == GOLDEN_LOOP_GRAPH, (
        f"LoopGraph golden master mismatch!\n"
        f"Expected: {GOLDEN_LOOP_GRAPH}\n"
        f"Actual:   {actual}"
    )


def test_golden_master_vertex_count():
    """The canonical Loop projects to exactly 5 vertices."""
    graph = project(_canonical_loop())
    assert len(graph.vertices) == 5


def test_golden_master_edge_count():
    """The canonical Loop projects to exactly 4 edges (created + 2 uses + verified_by)."""
    graph = project(_canonical_loop())
    assert len(graph.edges) == 4


# ── Runlog golden (JSONL keys) ────────────────────────────────────────

GOLDEN_RUNLOG_KEYS = {
    "timestamp", "domain", "tool", "baseline_rows",
    "baseline_fitness", "candidate_fitness",
    "promoted", "iterations_used", "reason",
}


def test_golden_master_runlog_keys():
    """Runlog JSONL record must contain all expected keys (M039 contract).

    This guards the runlog schema against drift — adding a key is OK, removing
    one is a regression.
    """
    import json
    from pathlib import Path
    # Find the most recent runlog
    runlogs = sorted(Path("runs").glob("sql_evolution.*.jsonl"))
    if not runlogs:
        # Generate one if none exists
        import subprocess
        subprocess.run(
            ["uv", "run", "python", "-m", "active_skill_system.composition.sql_evolution",
             "--quiet", "--emit-runlog"],
            capture_output=True, timeout=30,
        )
        runlogs = sorted(Path("runs").glob("sql_evolution.*.jsonl"))

    assert runlogs, "no runlog found and could not generate one"
    record = json.loads(runlogs[-1].read_text(encoding="utf-8"))

    missing = GOLDEN_RUNLOG_KEYS - set(record.keys())
    assert not missing, f"runlog missing keys: {missing}"
