"""L4 Composition — sandbox governance + events (M052 S00).

Self-governance check + event audit trail modes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from active_skill_system.composition.cli_exit import EX_OK, EX_PARTIAL
from active_skill_system.composition.sandbox.helpers import get_sandbox_logger


def run_governance_check(trace: Any = None) -> int:
    """Self-governance check: apply our own tools to our own codebase."""
    from active_skill_system.application.use_cases.self_governance_check import (
        run_governance_check,
    )

    result = run_governance_check(trace=trace)
    print(f"=== governance check (score {result.score:.2%}) ===", flush=True)
    for name, ok in result.axes.items():
        status = "OK" if ok else "FAIL"
        detail = result.details.get(name, "")[:120]
        print(f"  {name}: {status}  {detail}", flush=True)
    if result.all_passed:
        return EX_OK
    failed = result.failed_axes()
    get_sandbox_logger().warning("governance_check_failed score=%.2f axes_failed=%s", result.score, failed)
    return EX_PARTIAL


def build_event_store(spec: str | None) -> Any:
    """Build an EventStore from a --event-log spec (M051 S03)."""
    if not spec:
        return None
    from active_skill_system.adapters.event_store_impl import EventStoreImpl

    if spec == "inmemory":
        from active_skill_system.adapters.inmemory_event_log import InMemoryEventLog
        return EventStoreImpl(InMemoryEventLog())
    if spec.startswith("sqlite"):
        from active_skill_system.adapters.sqlite_event_log import SQLiteEventLog
        path = spec.split(":", 1)[1] if ":" in spec else spec
        if path.startswith("///"):
            path = path[3:]
        elif path.startswith("//"):
            path = path[2:]
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        return EventStoreImpl(SQLiteEventLog(path))
    print(f"event-log: unknown spec {spec!r} (use 'inmemory' or 'sqlite:<path>')", flush=True)
    return None


def run_event_stats(spec: str) -> int:
    """Print accumulated event counts from the event audit trail."""
    from collections import Counter

    store = build_event_store(spec)
    if store is None:
        print("event-log: disabled (pass --event-log sqlite:<path>)", flush=True)
        return EX_OK
    events = list(store.iter_events())
    print(f"event-log: {spec} ({len(events)} events)", flush=True)
    by_type: Counter[str] = Counter(e.type for e in events)
    for etype, count in by_type.most_common():
        print(f"  {etype}: {count}", flush=True)
    return EX_OK
