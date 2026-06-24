"""L2 Application ports — ExperimentWorkspacePort.

Domain- and use-case-facing contract for the experiment workspace: create a
branch (fork) from a run-at-event, and compare two runs structurally (diff).
The port is independent of activegraph — production wires it to
``ActivegraphExperimentWorkspace``; tests can wire a fake.

The contract mirrors the verified activegraph primitives C10/C16
(``activegraph-claims.md``): ``Runtime.fork`` reconstructs the parent prefix
from the saved event log + cache, diverges after the branch point;
``compute_diff`` reports shared / parent_only / fork_only counts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ForkSpec:
    """Output of ``ExperimentWorkspacePort.fork``."""

    parent_run_id: str
    at_event: str
    new_run_id: str
    label: str | None = None


@dataclass(frozen=True)
class DiffResult:
    """Output of ``ExperimentWorkspacePort.diff``: structural counts between two runs."""

    run_a: str
    run_b: str
    shared_events: int
    parent_only_events: int
    fork_only_events: int


@runtime_checkable
class ExperimentWorkspacePort(Protocol):
    """Domain-facing contract for fork + diff (independent of activegraph)."""

    def fork(
        self, parent_run_id: str, at_event: str, *, label: str | None = None
    ) -> ForkSpec:
        """Spawn a new run from a branch point in the parent run."""
        ...

    def diff(self, run_a: str, run_b: str) -> DiffResult:
        """Compare two runs structurally (shared / parent_only / fork_only counts)."""
        ...

    def list_runs(self) -> tuple[str, ...]:
        """Return the ids of all known runs (parent + forks)."""
        ...
