"""L2 outbound port - Runtime abstraction.

The application depends on this Protocol; L3 adapters (e.g.
`active_skill_system.adapters.runtime.activegraph.ActiveGraphRuntimeAdapter`)
implement it. Deliberately independent of activegraph / anthropic / openai
so the application layer stays infra-free (enforced by import-linter).

Note: at runtime, ActiveGraph's own Runtime satisfies `RuntimePort` via the
adapter in `adapters/runtime/`. This port is the application's declared
contract and the seam for swapping runtimes (e.g. an in-memory test fake,
a future DuckDB-backed deterministic runtime, etc.).

The port is intentionally narrow: it covers the use-cases the application
needs (run / fork / replay / diff / export). ActiveGraph-specific features
(behaviors, packs, policies) live below the port - the adapter injects
them as composition-time concerns, not as runtime API surface.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

# ── value types ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Budget:
    """Execution budget for a single run. Mirrors activegraph's budget dict."""

    max_llm_calls: int | None = None
    max_tool_calls: int | None = None
    max_cost_usd: str | None = None  # kept as str to preserve decimal precision


@dataclass(frozen=True)
class RunGoal:
    """Input to `RuntimePort.run_goal`."""

    goal: str
    actor: str = "user"
    persist_to: str | None = None
    seed: int | None = None
    budget: Budget = field(default_factory=Budget)


@dataclass(frozen=True)
class RunResult:
    """Output of `RuntimePort.run_goal` and `RuntimePort.replay`.

    Carries the structural facts the application needs (run_id, event
    counts, claim/memo counts); raw event-log access is via `export_trace`.
    """

    run_id: str
    goal: str
    status: str  # "ok" | "failed" | "budget_exceeded" | ...
    events_processed: int
    llm_calls: int
    tool_calls: int
    cost_usd: str
    claim_count: int = 0
    evidence_count: int = 0
    memo_count: int = 0
    failure_count: int = 0


@dataclass(frozen=True)
class ForkSpec:
    """Output of `RuntimePort.fork` - describes the new run spawned at a branch point."""

    parent_run_id: str
    at_event: str
    new_run_id: str
    label: str | None = None


@dataclass(frozen=True)
class DiffResult:
    """Output of `RuntimePort.diff` - high-level diff between two runs."""

    run_a: str
    run_b: str
    shared_events: int
    parent_only_events: int
    fork_only_events: int


@dataclass(frozen=True)
class TraceLine:
    """One line of an exported trace (format-agnostic projection)."""

    run_id: str
    sequence: int
    event_type: str
    payload_summary: str  # one-line human-readable summary (no raw content)


# ── the port ──────────────────────────────────────────────────────────────


@runtime_checkable
class RuntimePort(Protocol):
    """Minimal contract the application requires of a runtime.

    Adapters implement this over real runtimes (e.g. activegraph). Use-cases
    in `application/use_cases/` depend ONLY on this Protocol, never on a
    concrete runtime - that is what makes them testable with fakes and
    swappable.
    """

    def run_goal(self, goal: RunGoal, *, llm_provider: Any | None = None) -> RunResult:
        """Start a new run. Returns once the run terminates or hits its budget."""
        ...

    def fork(self, parent_run_id: str, at_event: str, *, label: str | None = None) -> ForkSpec:
        """Spawn a new run from a branch point in the parent run."""
        ...

    def replay(self, run_id: str) -> RunResult:
        """Rebuild the graph from the event log; no behaviors fire."""
        ...

    def diff(self, run_a: str, run_b: str) -> DiffResult:
        """Compare two runs structurally (shared / parent_only / fork_only events)."""
        ...

    def export_trace(self, run_id: str) -> Iterable[TraceLine]:
        """Yield one TraceLine per event in the run (read-only projection)."""
        ...
