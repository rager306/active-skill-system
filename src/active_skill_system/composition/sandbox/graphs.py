"""L4 Composition — sandbox graph queries (M052 S00).

Read-only graph operations: --graph-stats, --graph-query, --graph-trajectory,
--ratchet-stats.
"""

from __future__ import annotations

from pathlib import Path

from active_skill_system.composition.cli_exit import EX_NOT_FOUND, EX_OK, EX_PARTIAL
from active_skill_system.composition.sandbox.helpers import get_sandbox_logger


def run_graph_stats(graph_path: str) -> int:
    """Print accumulated provenance statistics."""
    p = Path(graph_path)
    if not p.exists() and graph_path != ":memory:":
        print(f"graph not found: {graph_path}", flush=True)
        get_sandbox_logger().warning("graph_not_found path=%s", graph_path)
        return EX_NOT_FOUND
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
        get_sandbox_logger().warning("graph_stats_partial path=%s failed_queries=%d", graph_path, failures)
        return EX_PARTIAL
    return EX_OK


def run_graph_query(graph_path: str, cypher: str) -> int:
    """Execute a Cypher query on the persistent graph."""
    p = Path(graph_path)
    if not p.exists() and graph_path != ":memory:":
        print(f"graph not found: {graph_path}", flush=True)
        get_sandbox_logger().warning("graph_not_found path=%s cypher=%s", graph_path, cypher)
        return EX_NOT_FOUND
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
        get_sandbox_logger().warning("cypher_failed path=%s err=%s", graph_path, e)
        return EX_PARTIAL
    return EX_OK


def run_graph_trajectory(graph_path: str) -> int:
    """Print the trajectory chain from the persistent graph (Wave 2 P1)."""
    p = Path(graph_path)
    if not p.exists() and graph_path != ":memory:":
        print(f"graph not found: {graph_path}", flush=True)
        get_sandbox_logger().warning("graph_not_found path=%s", graph_path)
        return EX_NOT_FOUND
    from active_skill_system.adapters.ladybug_graph_store import LadybugGraphStore

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
        get_sandbox_logger().warning("trajectory_query_failed path=%s err=%s", graph_path, e)
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


def run_ratchet_stats(ratchet_path: str) -> int:
    """Print accumulated ratchet entries."""
    from harness import RatchetLedger

    p = Path(ratchet_path)
    if not p.exists():
        print(f"ratchet: {ratchet_path} (NOT FOUND)", flush=True)
        get_sandbox_logger().warning("ratchet_not_found path=%s", ratchet_path)
        return EX_NOT_FOUND
    ledger = RatchetLedger.load(p)
    entries = ledger.entries
    print(f"ratchet: {ratchet_path} ({len(entries)} entries)", flush=True)
    for e in entries[-20:]:
        print(f"  {e.id} | {e.area} | {e.diff[:80]}", flush=True)
    return EX_OK
