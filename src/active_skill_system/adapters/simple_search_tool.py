"""L3 Adapter — SimpleSearchTool (M009 S03).

A deterministic mock knowledge-base search tool for unit tests and dev.
No external API; backed by a dict of query→fact. In production, this would
be replaced by a real RAG / web-search adapter.

Implements ``ToolPort`` (structural typing via Protocol).
"""

from __future__ import annotations

from typing import Any

from active_skill_system.application.ports.tool import (
    ToolCapability,
    ToolResult,
)


class SimpleSearchTool:
    """Mock knowledge-base search tool (deterministic, no network).

    capabilities: {search}
    invoke({'query': 'capital of france'}) → ToolResult(text='Paris', ...)
    """

    name = "simple_search"
    capabilities = frozenset({ToolCapability.SEARCH})

    def __init__(self, knowledge_base: dict[str, str] | None = None) -> None:
        self._kb: dict[str, str] = dict(knowledge_base or {})

    def invoke(self, args: dict[str, Any]) -> ToolResult:
        query = args.get("query", "")
        if not isinstance(query, str) or not query.strip():
            return ToolResult(text="", evidence_id=None, success=False)
        # Case-insensitive exact match (deterministic).
        for key, value in self._kb.items():
            if key.lower() == query.lower():
                return ToolResult(text=value, evidence_id=query, success=True)
        return ToolResult(text="", evidence_id=query, success=False)
