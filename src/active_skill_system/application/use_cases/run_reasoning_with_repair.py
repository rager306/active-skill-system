"""L2 Application use-case — RunReasoningWithRepairUseCase (M009 S04).

Orchestrates the full Cognitive Runtime pipeline WITH reasoning loop:
  1. Accept a TaskSpec (from ParseTaskSpec or hand-crafted).
  2. Build an initial TaskGraph (_build_graph from M003).
  3. Validate → detect gaps.
  4. If gaps: run RepairLoopUseCase with an execute_action callback that
     uses the ToolRegistry (e.g. SimpleSearchTool) to resolve gaps.
  5. Return the final graph + RepairResult.

The execute_action callback bridges the repair loop to the tool layer:
  gap → tool.invoke → ToolResult → GraphPatch (Evidence node + DERIVED_FROM)

Anti-fancy invariant: tool results ground claims via Evidence nodes + support
edges. The LLM/tool cannot self-promote PROPOSED→VERIFIED — the validator
checks provenance independently.

Pure application. Depends on domain + ports; no I/O (R002).
"""

from __future__ import annotations

from dataclasses import dataclass

from active_skill_system.application.ports.tool import ToolCapability
from active_skill_system.application.tools.registry import ToolRegistry
from active_skill_system.application.use_cases.repair_loop import (
    RepairLoopUseCase,
    RepairResult,
)
from active_skill_system.application.use_cases.repair_policy import RepairPolicy
from active_skill_system.application.use_cases.run_reasoning_vertical import (
    RunReasoningVerticalUseCase,
    TaskSpec,
)
from active_skill_system.application.use_cases.validate_task_graph import (
    ValidateTaskGraphUseCase,
)
from active_skill_system.domain.runtime import (
    GapClass,
    GapClassification,
    GraphPatch,
    NodeKind,
    PatchOp,
    TaskGraph,
)


@dataclass(frozen=True)
class ReasoningWithRepairResult:
    """Result of the full pipeline with reasoning loop."""

    graph: TaskGraph
    repair: RepairResult
    answer_ready: bool


class RunReasoningWithRepairUseCase:
    """Full pipeline: build → validate → repair-loop (with tools) → result."""

    def __init__(
        self,
        *,
        validator: ValidateTaskGraphUseCase | None = None,
        policy: RepairPolicy | None = None,
        tool_registry: ToolRegistry | None = None,
        max_cycles: int = 5,
    ) -> None:
        self._validator = validator or ValidateTaskGraphUseCase()
        self._policy = policy or RepairPolicy.default_policy()
        self._tools = tool_registry or ToolRegistry()
        self._max_cycles = max_cycles

    def run(self, task_spec: TaskSpec) -> ReasoningWithRepairResult:
        """Run the full pipeline with reasoning loop on a TaskSpec."""
        # Step 1-2: build initial graph (reuse M003 builder).
        vertical = RunReasoningVerticalUseCase(self._validator)
        initial_result = vertical.run(task_spec)
        # Re-build the graph (vertical.run returns ReasoningResult, not graph;
        # we need the actual TaskGraph for the repair loop).
        from active_skill_system.application.use_cases.run_reasoning_vertical import (
            _build_graph,
        )
        graph = _build_graph(task_spec)

        # Step 3-4: validate → if gaps → repair loop with tools.
        report = self._validator.validate(graph)
        if not report.gaps:
            # No gaps → done immediately.
            return ReasoningWithRepairResult(
                graph=graph,
                repair=RepairResult(
                    final_graph=graph,
                    cycles_used=0,
                    gaps_remaining=0,
                    patches_accepted=0,
                    patches_rejected=0,
                    status=__import__(
                        "active_skill_system.application.use_cases.repair_loop",
                        fromlist=["RepairStatus"],
                    ).RepairStatus.COMPLETED,
                ),
                answer_ready=initial_result.answer_ready,
            )

        # Run repair loop with tool-backed execute_action.
        loop = RepairLoopUseCase(
            self._validator, self._policy, max_cycles=self._max_cycles
        )
        repair_result = loop.run(graph, self._execute_action_with_tools)

        # Step 5: determine answer_ready from the final graph.
        final_report = self._validator.validate(repair_result.final_graph)
        answer_ready = (
            final_report.reachable
            and not final_report.ungrounded_factual_claims
            and not final_report.constraint_violations
        )

        return ReasoningWithRepairResult(
            graph=repair_result.final_graph,
            repair=repair_result,
            answer_ready=answer_ready,
        )

    def _execute_action_with_tools(
        self, gap: GapClassification, graph: TaskGraph
    ) -> GraphPatch | None:
        """Execute a repair action using the tool registry.

        For MISSING_EVIDENCE gaps: use SimpleSearchTool to find a fact,
        produce a GraphPatch that adds an Evidence node + DERIVED_FROM edge.
        For other gap types: return None (no tool available yet).
        """
        if gap.gap_class is not GapClass.MISSING_EVIDENCE:
            return None

        search_tool = self._tools.get_by_capability(ToolCapability.SEARCH)
        if search_tool is None:
            return None

        # Use the gap node's text as the search query (heuristic).
        gap_node = None
        for node in graph.nodes:
            if node.id == gap.node_id:
                gap_node = node
                break
        query = gap_node.text if gap_node and gap_node.text else gap.proposed_action

        result = search_tool.invoke({"query": query})
        if not result.success:
            return None

        # Build a GraphPatch: Evidence node + DERIVED_FROM edge to the gap node.
        evidence_id = f"ev_{gap.node_id.value}"
        return GraphPatch(
            operations=(
                PatchOp(
                    op_type="add_node",
                    payload={
                        "node_id": evidence_id,
                        "kind": NodeKind.EVIDENCE.value,
                        "text": result.text,
                    },
                ),
                PatchOp(
                    op_type="add_edge",
                    payload={
                        "source": evidence_id,
                        "target": gap.node_id.value,
                        "kind": "derived_from",
                    },
                ),
            )
        )
