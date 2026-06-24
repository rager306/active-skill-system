"""Tests for ActivegraphExperimentWorkspace (M006).

S01: ExperimentWorkspacePort + ActivegraphExperimentWorkspace + RuntimeRegistry
    construct cleanly, work over SQLite tempfile, surface ForkSpec/DiffResult.
S02: fork/diff semantics — parent prefix identical, divergence after branch,
    diff counts (shared / parent_only / fork_only), list_runs.

C10/C16 verification: parent prefix reconstructed from event log + cache
(verified M001); diff reports shared/parent_only/fork_only.

Fork requires SQLite (verified C16, re-confirmed during implementation:
in-memory raises IncompatibleRuntimeState). All tests use SQLite tempfiles
and close registries in teardown to avoid unraisable warnings escalating to
failures under ``filterwarnings=error``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from active_skill_system.adapters.activegraph_event_sink import ActivegraphEventSink
from active_skill_system.adapters.activegraph_experiment_workspace import (
    ActivegraphExperimentWorkspace,
    RuntimeRegistry,
)
from active_skill_system.adapters.taskgraph_bridge import (
    TaskGraphBridge,
)
from active_skill_system.application.ports.experiment_workspace import (
    DiffResult,
    ForkSpec,
)
from active_skill_system.domain.runtime import (
    NodeKind,
    TaskNode,
    TaskNodeId,
)


def _tmp_url(tmp_path: Path, name: str) -> str:
    return f"sqlite:///{tmp_path / name}"


# ── S01: construction + port + RuntimeRegistry ───────────────────────────


def test_port_protocol_runtime_checkable() -> None:
    """The production adapter satisfies the port structurally (isinstance)."""
    ws = ActivegraphExperimentWorkspace(RuntimeRegistry())
    from active_skill_system.application.ports.experiment_workspace import (
        ExperimentWorkspacePort,
    )

    assert isinstance(ws, ExperimentWorkspacePort)


def test_registry_create_and_get() -> None:
    reg = RuntimeRegistry()
    try:
        run_id, runtime = reg.create(_tmp_url(Path("/tmp"), "r1.db"))
        assert run_id in reg.list_runs()
        assert reg.get(run_id) is runtime
    finally:
        reg.close_all()


def test_registry_rejects_non_sqlite_url() -> None:
    reg = RuntimeRegistry()
    with pytest.raises(ValueError, match="sqlite"):
        reg.create("memory://nope")
    with pytest.raises(ValueError, match="sqlite"):
        reg.create("")


def test_registry_rejects_duplicate_run_id(tmp_path: Path) -> None:
    reg = RuntimeRegistry()
    try:
        run_id, runtime = reg.create(_tmp_url(tmp_path, "r2.db"))
        with pytest.raises(ValueError, match="already in registry"):
            reg.add(run_id, runtime)
    finally:
        reg.close_all()


# ── S02: fork/diff semantics ────────────────────────────────────────────


def test_fork_creates_child_with_parent_prefix_identical(tmp_path: Path) -> None:
    """C16: parent prefix events are identical in both branches up to at_event."""
    reg = RuntimeRegistry()
    try:
        parent_id, parent = reg.create(_tmp_url(tmp_path, "parent.db"))

        # Drive parent through several events via the bridge.
        bridge = TaskGraphBridge(ActivegraphEventSink(parent.graph))
        bridge.on_node_added(TaskNode(TaskNodeId("g1"), NodeKind.GOAL, "G"))
        bridge.on_node_added(TaskNode(TaskNodeId("e1"), NodeKind.EVIDENCE, ""))
        parent.run_goal("noop", actor="me")  # flush a real activegraph event too

        # Pick a branch point after the second node was added.
        event_id_at_branch = list(parent.graph.events)[1].id
        parent_events_before = list(parent.graph.events)

        ws = ActivegraphExperimentWorkspace(reg)
        spec = ws.fork(parent_id, at_event=event_id_at_branch, label="alt")

        child = reg.get(spec.new_run_id)
        child_events = list(child.graph.events)

        # Parent prefix (up to at_event) is identical in child.
        prefix_len = 0
        for e in parent_events_before:
            if e.id == event_id_at_branch:
                break
            prefix_len += 1
        assert len(child_events) >= prefix_len
        for i in range(prefix_len):
            assert child_events[i].id == parent_events_before[i].id, (
                f"event[{i}] diverges in parent prefix: {child_events[i]} vs {parent_events_before[i]}"
            )
    finally:
        reg.close_all()


def test_diff_counts_after_divergence(tmp_path: Path) -> None:
    """After fork, parent and child diverge; diff reports shared+parent_only+fork_only."""
    reg = RuntimeRegistry()
    try:
        parent_id, parent = reg.create(_tmp_url(tmp_path, "p.db"))
        bridge = TaskGraphBridge(ActivegraphEventSink(parent.graph))
        bridge.on_node_added(TaskNode(TaskNodeId("g"), NodeKind.GOAL, "G"))
        parent.run_goal("flush", actor="me")
        branch_id = list(parent.graph.events)[1].id

        ws = ActivegraphExperimentWorkspace(reg)
        spec = ws.fork(parent_id, at_event=branch_id, label="alt")

        # Drive parent forward.
        parent.run_goal("p-only-1", actor="me")
        parent.run_goal("p-only-2", actor="me")
        # Drive child forward.
        child = reg.get(spec.new_run_id)
        child.run_goal("f-only-1", actor="me")
        child.run_goal("f-only-2", actor="me")
        child.run_goal("f-only-3", actor="me")

        diff = ws.diff(parent_id, spec.new_run_id)
        assert isinstance(diff, DiffResult)
        # parent prefix (up to branch) is shared; subsequent events diverge.
        assert diff.shared_events >= 1
        assert diff.parent_only_events >= 1
        assert diff.fork_only_events >= 1
        # Total events seen by both: shared + parent_only + fork_only.
        assert diff.shared_events + diff.parent_only_events + diff.fork_only_events >= 3
    finally:
        reg.close_all()


def test_list_runs_returns_parent_and_forks(tmp_path: Path) -> None:
    reg = RuntimeRegistry()
    try:
        parent_id, parent = reg.create(_tmp_url(tmp_path, "p2.db"))
        parent.run_goal("seed", actor="me")
        branch_id = list(parent.graph.events)[0].id
        ws = ActivegraphExperimentWorkspace(reg)
        s1 = ws.fork(parent_id, at_event=branch_id, label="a")
        s2 = ws.fork(parent_id, at_event=branch_id, label="b")

        runs = ws.list_runs()
        assert parent_id in runs
        assert s1.new_run_id in runs
        assert s2.new_run_id in runs
    finally:
        reg.close_all()


def test_fork_returns_fork_spec_with_correct_fields(tmp_path: Path) -> None:
    reg = RuntimeRegistry()
    try:
        parent_id, parent = reg.create(_tmp_url(tmp_path, "p3.db"))
        parent.run_goal("x", actor="me")
        branch_id = list(parent.graph.events)[0].id
        ws = ActivegraphExperimentWorkspace(reg)
        spec = ws.fork(parent_id, at_event=branch_id, label="L")
        assert isinstance(spec, ForkSpec)
        assert spec.parent_run_id == parent_id
        assert spec.at_event == branch_id
        assert spec.label == "L"
        assert spec.new_run_id.endswith("::L")
    finally:
        reg.close_all()
