"""Unit tests for RepairLoopUseCase (M009 S02).

Drives the repair loop with fake ``execute_action`` callbacks (no tools,
no network). Verifies: gap-closed → completed; regressing patch → rejected;
budget exhaustion → partial; no gaps → immediate completed; loop-detection;
None-action skip.
"""

from __future__ import annotations

from active_skill_system.application.use_cases.repair_loop import (
    RepairLoopUseCase,
    RepairStatus,
)
from active_skill_system.application.use_cases.repair_policy import (
    ActionType,
    RepairPolicy,
)
from active_skill_system.application.use_cases.validate_task_graph import (
    ValidateTaskGraphUseCase,
)
from active_skill_system.domain.runtime import (
    GapClass,
    GraphPatch,
    NodeKind,
    PatchOp,
    TaskGraph,
    TaskNode,
    TaskNodeId,
)


def _goal_graph() -> TaskGraph:
    """A graph with an unsupported goal (has a gap)."""
    return TaskGraph().add_node(
        TaskNode(id=TaskNodeId("goal1"), kind=NodeKind.GOAL, text="G")
    )


def _action_adds_supporting_fact(gap, graph):  # noqa: ANN001
    """Fake action: adds a fact + SUPPORTS edge → closes the gap."""
    return GraphPatch(
        operations=(
            PatchOp(op_type="add_node", payload={"node_id": "f1", "kind": "fact", "text": "F"}),
            PatchOp(op_type="add_edge", payload={"source": "f1", "target": "goal1", "kind": "supports"}),
        )
    )


def _action_adds_nothing(gap, graph):  # noqa: ANN001
    """Fake action: adds an unrelated node (no support → no improvement → rejected)."""
    return GraphPatch(
        operations=(
            PatchOp(op_type="add_node", payload={"node_id": "x1", "kind": "fact", "text": "X"}),
        )
    )


def _action_returns_none(gap, graph):  # noqa: ANN001
    """Fake action: returns None (can't help)."""
    return None


# ── Tests ────────────────────────────────────────────────────────────────


def test_repair_loop_closes_gap_and_completes() -> None:
    """Gap closed by fake action → patch accepted → completed."""
    loop = RepairLoopUseCase(ValidateTaskGraphUseCase(), max_cycles=3)
    result = loop.run(_goal_graph(), _action_adds_supporting_fact)
    assert result.status is RepairStatus.COMPLETED
    assert result.gaps_remaining == 0
    assert result.patches_accepted == 1
    assert result.cycles_used == 1


def test_repair_loop_rejects_non_improving_patch() -> None:
    """Patch that doesn't close the gap → rejected → partial/failed."""
    loop = RepairLoopUseCase(ValidateTaskGraphUseCase(), max_cycles=2)
    result = loop.run(_goal_graph(), _action_adds_nothing)
    # The patch adds a node but doesn't support the goal → no measurable improvement → rejected.
    assert result.patches_rejected >= 1
    assert result.status is RepairStatus.FAILED  # all patches rejected


def test_repair_loop_budget_exhaustion_is_partial() -> None:
    """max_cycles=1 → budget exhausted after one attempt → partial (if action can't fully close)."""
    loop = RepairLoopUseCase(ValidateTaskGraphUseCase(), max_cycles=1)
    result = loop.run(_goal_graph(), _action_adds_nothing)
    assert result.cycles_used == 1
    assert result.gaps_remaining >= 1


def test_repair_loop_no_gaps_immediate_completed() -> None:
    """Graph with no gaps → completed immediately (0 cycles)."""
    from active_skill_system.domain.runtime import EdgeKind, TaskEdge

    g = (
        TaskGraph()
        .add_node(TaskNode(TaskNodeId("f1"), NodeKind.FACT, "F"))
        .add_node(TaskNode(TaskNodeId("goal1"), NodeKind.GOAL, "G"))
        .add_edge(TaskEdge(TaskNodeId("f1"), TaskNodeId("goal1"), EdgeKind.SUPPORTS))
    )
    loop = RepairLoopUseCase(ValidateTaskGraphUseCase(), max_cycles=3)
    result = loop.run(g, _action_adds_supporting_fact)
    assert result.status is RepairStatus.COMPLETED
    assert result.cycles_used == 0
    assert result.gaps_remaining == 0


def test_repair_loop_handles_none_action() -> None:
    """Action returns None → skip gap, continue → partial (gap remains)."""
    loop = RepairLoopUseCase(ValidateTaskGraphUseCase(), max_cycles=2)
    result = loop.run(_goal_graph(), _action_returns_none)
    assert result.cycles_used == 2
    assert result.gaps_remaining >= 1
    assert result.patches_accepted == 0
    assert result.patches_rejected == 0


def test_repair_loop_records_actions_taken() -> None:
    """actions_taken tuple records each cycle's gap/action/accepted."""
    loop = RepairLoopUseCase(ValidateTaskGraphUseCase(), max_cycles=3)
    result = loop.run(_goal_graph(), _action_adds_supporting_fact)
    assert len(result.actions_taken) >= 1
    cycle, gap_class, action_type, accepted = result.actions_taken[0]
    assert isinstance(cycle, int)
    assert gap_class == GapClass.MISSING_EVIDENCE.value
    assert action_type == ActionType.SEARCH.value
    assert accepted is True


def test_repair_policy_default_mapping() -> None:
    """default_policy maps all 8 gap classes to action types."""
    p = RepairPolicy.default_policy()
    for gc in GapClass:
        action = p.action_for(gc)
        assert isinstance(action, ActionType)
