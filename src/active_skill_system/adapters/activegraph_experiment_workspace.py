"""L3 Adapter — ActivegraphExperimentWorkspace (M006 production impl).

Production realisation of ``ExperimentWorkspacePort`` (M006 S01) over the
verified activegraph primitives C10/C16:

  - ``Runtime.fork(at_event, label, ...)`` reconstructs the parent prefix from
    the saved event log + cache, then diverges (CONTRACT v0.8 #5 requires
    SQLite-backed runtime — verified in M001, re-confirmed during M006
    implementation: in-memory runtime raises ``IncompatibleRuntimeState``).
  - ``Runtime.diff(other)`` reports shared / parent_only / fork_only events.

The adapter owns a ``RuntimeRegistry`` keyed by ``run_id`` so application
code never touches ``activegraph.Runtime`` directly. Tests use SQLite
tempfiles (``sqlite:///tmp/test-*.db``); production would use a persistent
SQLite URL per the same constraint.
"""

from __future__ import annotations

import contextlib
import gc
import re
import tempfile
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

from activegraph import Graph, Runtime
from activegraph.runtime.diff import Diff

from active_skill_system.application.ports.experiment_workspace import (
    DiffResult,
    ExperimentWorkspacePort,
    ForkSpec,
)

# SQLite URL must be of the form sqlite:///<path> (per activegraph).
_SQLITE_URL_RE = re.compile(r"^sqlite:(?:/{0,3})(/.+)$")


def _validate_sqlite_url(url: str) -> str:
    """Validate and normalize a SQLite URL; reject non-SQLite schemes."""
    if not url or not _SQLITE_URL_RE.match(url):
        raise ValueError(
            f"RuntimeRegistry requires a sqlite:///path URL (got {url!r})"
        )
    return url


@dataclass
class RuntimeRegistry:
    """Maps run ids to ``activegraph.Runtime`` instances, parented by URL.

    Two ways to obtain runtimes:
      - ``create(persist_to)``: brand-new runtime, returns (run_id, runtime).
      - ``add(run_id, runtime)``: register a runtime you built (e.g. for tests
        that pre-populate events).

    The registry is a single-process in-memory map; production would back it
    with a persistent DB (M007+).
    """

    _runtimes: OrderedDict[str, Runtime] = field(default_factory=OrderedDict)

    def create(self, persist_to: str) -> tuple[str, Runtime]:
        """Create a new Runtime with the given SQLite URL; return (run_id, runtime)."""
        url = _validate_sqlite_url(persist_to)
        run_id = str(uuid.uuid4())
        runtime = Runtime(Graph(), persist_to=url)
        self._runtimes[run_id] = runtime
        return run_id, runtime

    def add(self, run_id: str, runtime: Runtime) -> None:
        if run_id in self._runtimes:
            raise ValueError(f"run_id {run_id!r} already in registry")
        self._runtimes[run_id] = runtime

    def get(self, run_id: str) -> Runtime:
        if run_id not in self._runtimes:
            raise KeyError(f"unknown run_id {run_id!r}")
        return self._runtimes[run_id]

    def list_runs(self) -> tuple[str, ...]:
        return tuple(self._runtimes.keys())

    def has(self, run_id: str) -> bool:
        return run_id in self._runtimes

    def close_all(self) -> None:
        """Drop all runtimes and force GC so underlying sqlite connections close.

        activegraph's ``Runtime`` does not expose a public ``close()``; the
        SQLite connection is held until the runtime is garbage-collected.
        Tests call this in their teardown to avoid ``unraisable`` resource
        warnings (which `filterwarnings=error` in pyproject.toml promotes to
        test failures).
        """
        self._runtimes.clear()
        gc.collect()


def make_temp_sqlite_url(prefix: str = "m006-fork-") -> tuple[str, Path]:
    """Return (sqlite_url, temp_path) for an in-memory-equivalent test store.

    The file is created in the system temp dir; the caller is responsible
    for cleanup (tests typically pass to tempfile.TemporaryDirectory()).
    """
    fd, path_str = tempfile.mkstemp(prefix=prefix, suffix=".db")
    # Close the fd — activegraph opens its own connection.
    import os

    os.close(fd)
    return f"sqlite:///{path_str}", Path(path_str)


class ActivegraphExperimentWorkspace(ExperimentWorkspacePort):
    """Production implementation of ``ExperimentWorkspacePort`` over activegraph.

    Wraps a ``RuntimeRegistry`` and uses ``Runtime.fork`` + ``Runtime.diff``
    to satisfy the port. Forking requires SQLite-backed runtimes (C16).
    """

    def __init__(self, registry: RuntimeRegistry | None = None) -> None:
        self._registry = registry or RuntimeRegistry()

    @property
    def registry(self) -> RuntimeRegistry:
        return self._registry

    def fork(
        self, parent_run_id: str, at_event: str, *, label: str | None = None
    ) -> ForkSpec:
        parent = self._registry.get(parent_run_id)
        child = parent.fork(at_event=at_event, label=label)
        # ``child`` is a fresh Runtime; ``parent_run_id`` of the child comes
        # from the fork primitive (Runtime.fork records the parent_run_id on
        # the new RunRecord). For the port's ``ForkSpec.new_run_id``, we
        # generate a deterministic id keyed on (parent_run_id, at_event, label)
        # unless the runtime exposes a real one. Falling back to a synthetic
        # id keeps the port contract simple and traceable in tests.
        new_run_id = f"{parent_run_id}::fork::{at_event}" + (f"::{label}" if label else "")
        with contextlib.suppress(ValueError):
            # Re-fork at the same point (with the same label) is a no-op in
            # the current test surface; the existing fork stays in the registry.
            self._registry.add(new_run_id, child)
        return ForkSpec(
            parent_run_id=parent_run_id,
            at_event=at_event,
            new_run_id=new_run_id,
            label=label,
        )

    def diff(self, run_a: str, run_b: str) -> DiffResult:
        rt_a = self._registry.get(run_a)
        rt_b = self._registry.get(run_b)
        diff: Diff = rt_a.diff(rt_b)
        return DiffResult(
            run_a=run_a,
            run_b=run_b,
            shared_events=len(diff.shared_events),
            parent_only_events=len(diff.parent_only_events),
            fork_only_events=len(diff.fork_only_events),
        )

    def list_runs(self) -> tuple[str, ...]:
        return self._registry.list_runs()
