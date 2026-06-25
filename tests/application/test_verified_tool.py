"""Unit tests for VerifiedToolResult + ToolProfile + registry filtering (M014 S03)."""

from __future__ import annotations

from active_skill_system.application.ports.tool import (
    ToolCapability,
    ToolProfile,
    ToolResult,
    VerifiedToolResult,
)
from active_skill_system.application.tools.registry import ToolRegistry

# ── VerifiedToolResult ────────────────────────────────────────────────────


def test_verified_tool_result_default_not_verified() -> None:
    r = VerifiedToolResult(text="ok", evidence_id="e1")
    assert r.verified is False
    assert r.verification_source is None


def test_verified_tool_result_with_verification() -> None:
    r = VerifiedToolResult(text="ok", evidence_id="e1", verified=True, verification_source="readback")
    assert r.verified is True
    assert r.verification_source == "readback"


def test_from_tool_result() -> None:
    base = ToolResult(text="42", evidence_id="2+2", success=True)
    verified = VerifiedToolResult.from_tool_result(base, verified=True, verification_source="recompute")
    assert verified.text == "42"
    assert verified.verified is True
    assert verified.verification_source == "recompute"


# ── ToolProfile ───────────────────────────────────────────────────────────


def test_tool_profile_all_three_values() -> None:
    assert {p.value for p in ToolProfile} == {"normal", "break_glass", "debug"}


# ── ToolRegistry profile filtering ───────────────────────────────────────


class _FakeTool:
    """Minimal tool for profile-filter testing."""

    def __init__(self, name: str, profile: ToolProfile = ToolProfile.NORMAL) -> None:
        self.name = name
        self.capabilities = frozenset({ToolCapability.SEARCH})
        self.profile = profile

    def invoke(self, args):  # noqa: ANN001, ARG002
        return ToolResult(text="ok")

    def verify(self, result):  # noqa: ANN001, ARG002
        return None


def test_registry_normal_profile_hides_break_glass() -> None:
    reg = ToolRegistry()
    reg.register(_FakeTool("safe_tool", ToolProfile.NORMAL))
    reg.register(_FakeTool("dangerous_tool", ToolProfile.BREAK_GLASS))
    visible = reg.list_by_profile(ToolProfile.NORMAL)
    assert len(visible) == 1
    assert visible[0].name == "safe_tool"


def test_registry_break_glass_shows_both() -> None:
    reg = ToolRegistry()
    reg.register(_FakeTool("safe", ToolProfile.NORMAL))
    reg.register(_FakeTool("danger", ToolProfile.BREAK_GLASS))
    visible = reg.list_by_profile(ToolProfile.BREAK_GLASS)
    assert len(visible) == 2


def test_registry_debug_shows_all() -> None:
    reg = ToolRegistry()
    reg.register(_FakeTool("safe", ToolProfile.NORMAL))
    reg.register(_FakeTool("danger", ToolProfile.BREAK_GLASS))
    reg.register(_FakeTool("diag", ToolProfile.DEBUG))
    visible = reg.list_by_profile(ToolProfile.DEBUG)
    assert len(visible) == 3


def test_registry_normal_hides_debug() -> None:
    reg = ToolRegistry()
    reg.register(_FakeTool("safe", ToolProfile.NORMAL))
    reg.register(_FakeTool("diag", ToolProfile.DEBUG))
    visible = reg.list_by_profile(ToolProfile.NORMAL)
    assert len(visible) == 1
    assert visible[0].name == "safe"
