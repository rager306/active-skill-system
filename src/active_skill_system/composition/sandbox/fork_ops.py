"""L4 Composition — fork/diff CLI operations (M052 S06+S07).

--fork <run_id> <at_event> : branch a run at a specific event.
--diff <run_a> <run_b>     : structural diff of two runs.
"""

from __future__ import annotations

from active_skill_system.composition.cli_exit import EX_NOT_FOUND, EX_OK, EX_PARTIAL
from active_skill_system.composition.sandbox.governance import build_event_store
from active_skill_system.composition.sandbox.helpers import get_sandbox_logger


def run_fork(
    parent_run_id: str,
    at_event_id: str,
    fork_model: str | None,
    event_log_spec: str | None,
) -> int:
    """Fork a run at a specific event (M052 S06).

    Copies the event prefix into a new fork run. If fork_model is given,
    the fork can continue with a different model (cache replay for prefix).
    """
    store = build_event_store(event_log_spec or os.environ.get("SANDBOX_EVENT_LOG"))
    if store is None:
        print("fork: --event-log is required for fork operations", flush=True)
        print("  usage: --fork <run_id> <at_event> --event-log sqlite:runs/events.db", flush=True)
        return EX_NOT_FOUND

    from active_skill_system.adapters.native_fork_engine import NativeForkEngine

    engine = NativeForkEngine(store)
    overrides = {}
    if fork_model:
        overrides["model"] = fork_model

    try:
        fork = engine.fork(parent_run_id, at_event_id, config_overrides=overrides)
    except Exception as e:  # noqa: BLE001
        print(f"fork failed: {e}", flush=True)
        return EX_PARTIAL

    print("fork created:", flush=True)
    print(f"  parent: {fork.parent_run_id}", flush=True)
    print(f"  fork:   {fork.fork_run_id}", flush=True)
    print(f"  at:     {fork.at_event_id}", flush=True)
    if fork.config_overrides:
        print(f"  overrides: {fork.config_overrides}", flush=True)

    # Count copied events.
    fork_events = list(store.iter_events(run_id=fork.fork_run_id))
    print(f"  copied events: {len(fork_events)}", flush=True)

    get_sandbox_logger().info(
        "fork_created parent=%s fork=%s at=%s events=%d",
        fork.parent_run_id, fork.fork_run_id, fork.at_event_id, len(fork_events),
    )
    return EX_OK


def run_diff(
    run_a: str,
    run_b: str,
    event_log_spec: str | None,
) -> int:
    """Structural diff of two runs (M052 S07).

    Compares event logs to find the split point and divergent objects.
    """
    store = build_event_store(event_log_spec or os.environ.get("SANDBOX_EVENT_LOG"))
    if store is None:
        print("diff: --event-log is required for diff operations", flush=True)
        return EX_NOT_FOUND

    from active_skill_system.adapters.native_fork_engine import NativeForkEngine

    engine = NativeForkEngine(store)

    # Check both runs exist.
    a_events = list(store.iter_events(run_id=run_a))
    b_events = list(store.iter_events(run_id=run_b))
    if not a_events:
        print(f"run not found: {run_a}", flush=True)
        return EX_NOT_FOUND
    if not b_events:
        print(f"run not found: {run_b}", flush=True)
        return EX_NOT_FOUND

    try:
        diff = engine.diff(run_a, run_b)
    except Exception as e:  # noqa: BLE001
        print(f"diff failed: {e}", flush=True)
        return EX_PARTIAL

    print(diff.summary(), flush=True)
    if diff.is_identical:
        print("  → runs are identical", flush=True)
    else:
        print(f"  → runs diverge at {diff.split_event_id}", flush=True)

    get_sandbox_logger().info(
        "diff_completed a=%s b=%s identical=%s objects=%d",
        run_a, run_b, diff.is_identical, len(diff.divergent_objects),
    )
    return EX_OK


# Need os import.
import os  # noqa: E402
