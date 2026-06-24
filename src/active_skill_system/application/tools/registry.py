"""L2 Application — ToolRegistry (M009 S03).

Maps ``ToolCapability`` → ``ToolPort`` instances so the repair loop can look
up the right tool for a gap. Simple dict-based registry; persistent storage
and capability-probing are deferred (M4+).

Pure application. NO infrastructure imports (R002).
"""

from __future__ import annotations

from active_skill_system.application.ports.tool import ToolCapability, ToolPort


class ToolRegistry:
    """Lookup tools by capability.

    Usage::

        reg = ToolRegistry()
        reg.register(my_search_tool)
        tool = reg.get_by_capability(ToolCapability.SEARCH)
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
