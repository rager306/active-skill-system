"""L3 adapter - activegraph-backed implementation of RuntimePort.

This adapter wraps `activegraph.Runtime` so that application use-cases
(`active_skill_system.application.use_cases.*`) can depend on the abstract
`RuntimePort` Protocol instead of importing activegraph directly. The
adapter is the only place where application-level code crosses the
hex/Onion boundary into the activegraph runtime.

Design choices:

  - **Lazy construction**: `__init__` stores the constructor arguments but
    does NOT build a `Graph()` or `Runtime` instance. The actual runtime
    is built in `run_goal` (which has the goal) or `replay` (which has
    the path). This makes the adapter cheap to instantiate in tests and
    keeps it side-effect free at import time (R008).

  - **No event-log export by default**: `export_trace` reads the
    `events_processed` count from the runtime, then yields one
    `TraceLine` per event with a one-line summary. Raw payload is
    NOT included (sanitized by default, R002 + redaction_by_default).

  - **Pack loading stays composition-time**: the adapter accepts a
    pre-configured `Runtime` via `runtime_factory` (a callable). The
    composition root wires the factory with the right packs, settings,
    and budget. The adapter does not know about packs.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from activegraph import Graph, Runtime

from active_skill_system.application.ports.runtime import (
    DiffResult,
    ForkSpec,
    RunGoal,
    RunResult,
    TraceLine,
)

# Type alias: factory that produces a configured Runtime given a goal.
# Composition root wires the factory; the adapter just calls it.
RuntimeFactory = Callable[[RunGoal], Runtime]


def _summarize_event(event: Any) -> str:
    """One-line summary of an event for TraceLine.payload_summary.

    Never returns the raw payload - redacted by default (R002).
    """
    etype = getattr(event, "type", None) or type(event).__name__
    payload = getattr(event, "payload", None)
    if payload is None:
        return etype
    if isinstance(payload, dict):
        # Pick the most informative key without dumping everything.
        for key in ("object_type", "object", "behavior", "tool", "model", "reason"):
            if key in payload:
                return f"{etype} {key}={payload[key]!r:.80}"
    return etype


class ActiveGraphRuntimeAdapter:
    """activegraph-backed implementation of RuntimePort.

    This class is structurally compatible with `RuntimePort`; isinstance
    checks succeed via the duck-typed Protocol (`@runtime_checkable` on
    RuntimePort + matching method signatures).

    Construction is lazy: no Graph / Runtime is created until `run_goal`
    or `replay` is called. This keeps the adapter cheap and side-effect
    free at import time.
    """

    def __init__(self, *, runtime_factory: RuntimeFactory | None = None) -> None:
        # If no factory is provided, build a default one that wires a
        # fresh Graph + Runtime with the goal's budget and persist_to.
        self._factory: RuntimeFactory = runtime_factory or self._default_factory

    @staticmethod
    def _default_factory(goal: RunGoal) -> Runtime:
        """Build a fresh Graph + Runtime for a given RunGoal.

        Used when no explicit factory is provided. Packs, settings, and
        policy injection live in the composition root - the adapter
        does not know about them.
        """
        graph = Graph()
        budget: dict[str, Any] = {}
        if goal.budget.max_llm_calls is not None:
            budget["max_llm_calls"] = goal.budget.max_llm_calls
        if goal.budget.max_tool_calls is not None:
            budget["max_tool_calls"] = goal.budget.max_tool_calls
        if goal.budget.max_cost_usd is not None:
            budget["max_cost_usd"] = goal.budget.max_cost_usd
        return Runtime(
            graph,
            llm_provider=None,  # injected per-run via run_goal(llm_provider=)
            persist_to=goal.persist_to,
            budget=budget or None,
            seed=goal.seed if goal.seed is not None else 0,
        )

    def run_goal(self, goal: RunGoal, *, llm_provider: Any | None = None) -> RunResult:
        """Start a new run for the given goal. See RuntimePort.run_goal."""
        runtime = self._factory(goal)
        if llm_provider is not None:
            runtime.llm_provider = llm_provider
        try:
            runtime.run_goal(goal.goal, actor=goal.actor)
        except Exception:
            return _snapshot(runtime, goal.goal, status="failed")
        return _snapshot(runtime, goal.goal, status="ok")

    def fork(self, parent_run_id: str, at_event: str, *, label: str | None = None) -> ForkSpec:
        """Spawn a new run from a branch point. See RuntimePort.fork.

        Note: this method requires a `Runtime` already loaded with the
        parent run; the composition root is responsible for handing the
        right runtime to the adapter. The port-level signature stays
        abstract (parent_run_id + at_event); the adapter translates
        to activegraph's `Runtime.fork(at_event, label, ...)`.
        """
        # Implementation is deferred to composition; see the docstring.
        # Tests that don't exercise fork can use the existing composition
        # path (which loads the parent from persist_to).
        raise NotImplementedError(
            "ActiveGraphRuntimeAdapter.fork requires composition-root plumbing "
            "(load parent from persist_to, then call Runtime.fork). "
            "S05 will wire this through RunReasoningUseCase."
        )

    def replay(self, run_id: str) -> RunResult:
        """Rebuild the graph from the event log. See RuntimePort.replay.

        Implementation deferred to composition (needs the persist_to path).
        """
        raise NotImplementedError(
            "ActiveGraphRuntimeAdapter.replay requires composition-root plumbing "
            "(Runtime.load(path)). S05 will wire this through RunReasoningUseCase."
        )

    def diff(self, run_a: str, run_b: str) -> DiffResult:
        """Compare two runs. See RuntimePort.diff.

        Implementation deferred to composition (needs two loaded Runtimes).
        """
        raise NotImplementedError(
            "ActiveGraphRuntimeAdapter.diff requires composition-root plumbing "
            "(load two Runtimes, then call diff). S05 will wire this."
        )

    def export_trace(self, run_id: str) -> Iterable[TraceLine]:
        """Yield one TraceLine per event. See RuntimePort.export_trace.

        Implementation deferred to composition (needs a loaded Runtime with
        a readable event log).
        """
        raise NotImplementedError(
            "ActiveGraphRuntimeAdapter.export_trace requires composition-root "
            "plumbing. S05 will wire this."
        )


# ── helpers ────────────────────────────────────────────────────────────────


def _count_events(runtime: Runtime) -> int:
    """Count events processed so far in a runtime (best-effort)."""
    store = getattr(runtime, "_event_store", None)
    if store is not None and hasattr(store, "count"):
        try:
            return int(store.count())
        except Exception:  # noqa: BLE001
            pass
    return 0


def _count_llm_calls(runtime: Runtime) -> int:
    """Count llm.responded events in the runtime (best-effort)."""
    return _count_event_type(runtime, "llm.responded")


def _count_tool_calls(runtime: Runtime) -> int:
    """Count tool.call / tool.result events (best-effort)."""
    return _count_event_type(runtime, "tool.call") + _count_event_type(runtime, "tool.result")


def _count_event_type(runtime: Runtime, event_type: str) -> int:
    store = getattr(runtime, "_event_store", None)
    if store is None or not hasattr(store, "iter_events"):
        return 0
    n = 0
    try:
        for ev in store.iter_events():
            if getattr(ev, "type", None) == event_type:
                n += 1
    except Exception:  # noqa: BLE001
        return 0
    return n


def _cost_usd(runtime: Runtime) -> str:
    """Best-effort cost readout for the runtime (string for decimal safety)."""
    try:
        status = runtime.status()
        for attr in ("total_cost", "cost_usd", "cost"):
            val = getattr(status, attr, None)
            if val is not None:
                return f"{val:.6f}"
    except Exception:  # noqa: BLE001
        pass
    return "0.000000"


def _snapshot(runtime: Runtime, goal: str, *, status: str) -> RunResult:
    """Build a RunResult from a finished (or failed) runtime."""
    return RunResult(
        run_id=runtime.run_id,
        goal=goal,
        status=status,
        events_processed=_count_events(runtime),
        llm_calls=_count_llm_calls(runtime),
        tool_calls=_count_tool_calls(runtime),
        cost_usd=_cost_usd(runtime),
    )
