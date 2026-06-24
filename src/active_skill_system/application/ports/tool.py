"""L2 outbound port — ToolPort (M009 S03).

Typed contract for tools the repair loop can invoke. Simplified SkillSpec
(full GeneSpec = M4+). Tools are registered in a ``ToolRegistry`` and looked
up by capability; the repair loop's ``execute_action`` callback wires the
right tool for a gap.

Pure application. NO infrastructure imports (R002).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable


class ToolCapability(StrEnum):
    """Capabilities a tool can provide (for registry lookup)."""

    SEARCH = "search"
    COMPUTE = "compute"
    READ = "read"
    WRITE = "write"


@dataclass(frozen=True)
class ToolResult:
    """Result of a tool invocation.

    Carries:
      - text: the result content (grounded fact / computed value).
      - evidence_id: a stable id for provenance (e.g. the query or expression).
      - success: False if the tool couldn't produce a result.
    """

    text: str
    evidence_id: str | None = None
    success: bool = True


@runtime_checkable
class ToolPort(Protocol):
    """Typed tool contract (simplified SkillSpec).

    Attributes:
      - name: unique tool identifier.
      - capabilities: what this tool can do (for registry lookup).

    Methods:
      - invoke(args): execute the tool, return a ``ToolResult``.
    """

    name: str
    capabilities: frozenset[ToolCapability]

    def invoke(self, args: dict[str, Any]) -> ToolResult: ...
