"""L2 outbound port — ToolPort (M009 S03, extended M014 S03).

Typed contract for tools the repair loop can invoke. Extended with:
  - ToolProfile (D007): normal/break_glass/debug visibility control.
  - VerifiedToolResult (D007): ToolResult + independent verification.
  - verify() method on ToolPort (optional): action-level anti-fancy gate.

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


class ToolProfile(StrEnum):
    """Visibility/safety profile for a tool (D007 Synapse patterns).

    NORMAL: visible to all agents by default (safe, read-only or deterministic).
    BREAK_GLASS: hidden by default; requires explicit profile escalation
        (irreversible operations, foreground actions).
    DEBUG: hidden from all production profiles; diagnostic only.
    """

    NORMAL = "normal"
    BREAK_GLASS = "break_glass"
    DEBUG = "debug"


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


@dataclass(frozen=True)
class VerifiedToolResult:
    """ToolResult + independent verification (D007 4th anti-fancy level).

    Wraps a ToolResult with a verification layer: the result was independently
    confirmed (e.g. readback from a separate source of truth).

    Carries:
      - text: the result content (same as ToolResult).
      - evidence_id: stable provenance id.
      - success: whether the tool produced a result.
      - verified: whether the result was independently confirmed.
      - verification_source: how it was verified (e.g. "readback", "recompute").
    """

    text: str
    evidence_id: str | None = None
    success: bool = True
    verified: bool = False
    verification_source: str | None = None

    @classmethod
    def from_tool_result(
        cls,
        result: ToolResult,
        *,
        verified: bool = False,
        verification_source: str | None = None,
    ) -> VerifiedToolResult:
        """Create a VerifiedToolResult from a ToolResult."""
        return cls(
            text=result.text,
            evidence_id=result.evidence_id,
            success=result.success,
            verified=verified,
            verification_source=verification_source,
        )


@runtime_checkable
class ToolPort(Protocol):
    """Typed tool contract (simplified SkillSpec).

    Attributes:
      - name: unique tool identifier.
      - capabilities: what this tool can do (for registry lookup).
      - profile: safety visibility (default NORMAL).

    Methods:
      - invoke(args): execute the tool, return a ``ToolResult``.
      - verify(result): optionally independently verify the result.
          Returns a ``VerifiedToolResult`` or None if verification is not
          applicable (default: not implemented → None).
    """

    name: str
    capabilities: frozenset[ToolCapability]
    profile: ToolProfile

    def invoke(self, args: dict[str, Any]) -> ToolResult: ...

    def verify(self, result: ToolResult) -> VerifiedToolResult | None:
        """Independently verify a tool result. Default: None (not verifiable)."""
        ...
