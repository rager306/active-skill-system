"""Unit tests for SimpleSearchTool, SimpleCalcTool, ToolRegistry (M009 S03).

Also tests tool→GraphPatch integration: a search result becomes an Evidence
node + DERIVED_FROM edge, grounding a previously-ungrounded claim.
"""

from __future__ import annotations

from active_skill_system.adapters.simple_calc_tool import SimpleCalcTool
from active_skill_system.adapters.simple_search_tool import SimpleSearchTool
from active_skill_system.application.ports.tool import ToolCapability
from active_skill_system.application.tools.registry import ToolRegistry
from active_skill_system.domain.runtime import (
    GraphPatch,
    NodeKind,
    PatchOp,
    TaskGraph,
    TaskNode,
    TaskNodeId,
)

# ── SimpleSearchTool ──────────────────────────────────────────────────────


def test_search_tool_finds_known_query() -> None:
    tool = SimpleSearchTool({"capital of france": "Paris"})
    result = tool.invoke({"query": "capital of france"})
    assert result.success is True
    assert result.text == "Paris"
    assert result.evidence_id == "capital of france"


def test_search_tool_misses_unknown_query() -> None:
    tool = SimpleSearchTool({"a": "b"})
    result = tool.invoke({"query": "unknown"})
    assert result.success is False
    assert result.text == ""


def test_search_tool_case_insensitive() -> None:
    tool = SimpleSearchTool({"Hello": "World"})
    result = tool.invoke({"query": "hello"})
    assert result.success is True
    assert result.text == "World"


# ── SimpleCalcTool ────────────────────────────────────────────────────────


def test_calc_tool_addition() -> None:
    result = SimpleCalcTool().invoke({"expression": "2+2"})
    assert result.success is True
    assert result.text == "4"


def test_calc_tool_complex_expression() -> None:
    result = SimpleCalcTool().invoke({"expression": "10*3-5"})
    assert result.success is True
    assert result.text == "25"


def test_calc_tool_division() -> None:
    result = SimpleCalcTool().invoke({"expression": "10/4"})
    assert result.success is True
    assert result.text == "2.5"


def test_calc_tool_rejects_invalid_expression() -> None:
    result = SimpleCalcTool().invoke({"expression": "import os"})
    assert result.success is False


def test_calc_tool_rejects_empty() -> None:
    result = SimpleCalcTool().invoke({"expression": ""})
    assert result.success is False


# ── ToolRegistry ──────────────────────────────────────────────────────────


def test_registry_register_and_lookup() -> None:
    reg = ToolRegistry()
    search = SimpleSearchTool({"a": "b"})
    calc = SimpleCalcTool()
    reg.register(search)
    reg.register(calc)

    found = reg.get_by_capability(ToolCapability.SEARCH)
    assert found is search

    found_calc = reg.get_by_capability(ToolCapability.COMPUTE)
    assert found_calc is calc


def test_registry_returns_none_for_missing_capability() -> None:
    reg = ToolRegistry()
    assert reg.get_by_capability(ToolCapability.SEARCH) is None


def test_registry_list_tools() -> None:
    reg = ToolRegistry()
    reg.register(SimpleSearchTool({"a": "b"}))
    reg.register(SimpleCalcTool())
    assert len(reg.list_tools()) == 2


def test_registry_reregroduce_replaces_by_name() -> None:
    reg = ToolRegistry()
    reg.register(SimpleSearchTool({"old": "data"}))
    reg.register(SimpleSearchTool({"new": "data"}))
    # Same name → replaces, not duplicates.
    assert len(reg.list_tools()) == 1


# ── Tool → GraphPatch integration ────────────────────────────────────────


def test_search_result_becomes_evidence_patch() -> None:
    """A search tool result → Evidence node + DERIVED_FROM edge → grounds claim."""
    tool = SimpleSearchTool({"capital of france": "Paris"})
    result = tool.invoke({"query": "capital of france"})
    assert result.success

    # Build a GraphPatch that adds the evidence node + grounds the claim.
    patch = GraphPatch(
        operations=(
            PatchOp(op_type="add_node", payload={"node_id": "ev1", "kind": "evidence", "text": result.text}),
            PatchOp(op_type="add_edge", payload={"source": "ev1", "target": "claim1", "kind": "derived_from"}),
        )
    )
    # Apply to a graph that has an ungrounded claim.
    graph = (
        TaskGraph()
        .add_node(TaskNode(TaskNodeId("claim1"), NodeKind.CLAIM, "The capital is Paris"))
        .add_node(TaskNode(TaskNodeId("goal1"), NodeKind.GOAL, "What is the capital?"))
    )
    patched = patch.apply(graph)
    assert len(patched.nodes) == 3  # claim1, goal1 + evidence
    assert any(n.id == TaskNodeId("ev1") for n in patched.nodes)
