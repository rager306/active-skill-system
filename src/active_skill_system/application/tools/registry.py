"""L2 Application — ToolRegistry (M009 S03, extended M014 S03).

Maps ``ToolCapability`` → ``ToolPort`` instances so the repair loop can look
up the right tool for a gap. Extended with ToolProfile filtering (D007):
``list_by_profile`` returns only tools visible at a given safety profile.

Pure application. NO infrastructure imports (R002).
"""

from __future__ import annotations

from active_skill_system.application.ports.tool import (
    ToolCapability,
    ToolPort,
    ToolProfile,
)


class ToolRegistry:
    """Lookup tools by capability and profile.

    Usage::

        reg = ToolRegistry()
        reg.register(my_search_tool)
        tool = reg.get_by_capability(ToolCapability.SEARCH)
        safe_tools = reg.list_by_profile(ToolProfile.NORMAL)
    """

    def __init__(self) -> None:
        self._tools: list[ToolPort] = []

    def register(self, tool: ToolPort) -> None:
        """Register a tool. Idempotent on tool.name (re-register replaces)."""
        # Remove any existing tool with the same name.
        self._tools = [t for t in self._tools if t.name != tool.name]
        self._tools.append(tool)

    def get_by_capability(self, capability: ToolCapability) -> ToolPort | None:
        """Return the first registered tool with the given capability, or None."""
        for tool in self._tools:
            if capability in tool.capabilities:
                return tool
        return None

    def list_tools(self) -> tuple[ToolPort, ...]:
        """Return all registered tools."""
        return tuple(self._tools)

    def list_by_profile(self, profile: ToolProfile) -> tuple[ToolPort, ...]:
        """Return only tools visible at the given profile level.

        NORMAL profile sees only NORMAL tools.
        BREAK_GLASS profile sees NORMAL + BREAK_GLASS tools.
        DEBUG profile sees all tools.
        """
        visibility = {
            ToolProfile.NORMAL: {ToolProfile.NORMAL},
            ToolProfile.BREAK_GLASS: {ToolProfile.NORMAL, ToolProfile.BREAK_GLASS},
            ToolProfile.DEBUG: {ToolProfile.NORMAL, ToolProfile.BREAK_GLASS, ToolProfile.DEBUG},
        }
        allowed = visibility.get(profile, {ToolProfile.NORMAL})
        return tuple(t for t in self._tools if getattr(t, "profile", ToolProfile.NORMAL) in allowed)
