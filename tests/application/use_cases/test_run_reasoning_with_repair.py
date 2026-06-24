"""Integration tests for RunReasoningWithRepairUseCase (M009 S04).

Full pipeline: TaskSpec with ungrounded goal → build graph → validate (gaps)
→ repair loop with SimpleSearchTool → tool resolves gap → patch accepted →
re-validate → gaps=0 → completed. Also: tool can't find fact → partial.
"""

from __future__ import annotations

from active_skill_system.adapters.simple_search_tool import SimpleSearchTool
from active_skill_system.application.tools.registry import ToolRegistry
from active_skill_system.application.use_cases.repair_loop import RepairStatus
from active_skill_system.application.use_cases.run_reasoning_vertical import (
    TaskSpec,
)
from active_skill_system.application.use_cases.run_reasoning_with_repair import (
    RunReasoningWithRepairUseCase,
)


def _registry_with_kb(kb: dict[str, str]) -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(SimpleSearchTool(kb))
    return reg


def test_repair_loop_closes_gap_with_search_tool() -> None:
    """Gap detected → search tool finds fact → patch accepted → completed."""
    # TaskSpec with an unsupported goal (no facts, no claims → gap).
    spec = TaskSpec(goal="What is the capital of France?")
    # Tool KB has the answer.
    registry = _registry_with_kb({"What is the capital of France?": "Paris"})

    use_case = RunReasoningWithRepairUseCase(
        tool_registry=registry, max_cycles=3
    )
    result = use_case.run(spec)

    assert result.repair.status is RepairStatus.COMPLETED
    assert result.repair.gaps_remaining == 0
    assert result.repair.patches_accepted >= 1
    assert result.answer_ready is True


def test_repair_loop_partial_when_tool_cannot_find_fact() -> None:
    """Gap detected → tool can't find fact → partial (gap remains)."""
    spec = TaskSpec(goal="What is the capital of France?")
    # Tool KB is empty — no fact found.
    registry = _registry_with_kb({})

    use_case = RunReasoningWithRepairUseCase(
        tool_registry=registry, max_cycles=3
    )
    result = use_case.run(spec)

    assert result.repair.gaps_remaining >= 1
    # No patches accepted (tool returned None → no patch).
    assert result.repair.patches_accepted == 0


def test_repair_loop_immediate_completed_when_no_gaps() -> None:
    """TaskSpec with supporting fact → no gaps → completed immediately."""
    spec = TaskSpec(
        goal="Answer the question",
        facts=("Paris is the capital of France",),
    )
    registry = _registry_with_kb({})

    use_case = RunReasoningWithRepairUseCase(
        tool_registry=registry, max_cycles=3
    )
    result = use_case.run(spec)

    assert result.repair.status is RepairStatus.COMPLETED
    assert result.repair.cycles_used == 0
    assert result.repair.gaps_remaining == 0
