"""L2 Application — BudgetController (M013 S02).

Tracks resource consumption (LLM calls, tool calls, cost) against budget
limits. When a budget is exhausted, the caller must return a partial result
instead of continuing. concept.md F-11 (partial result on budget exhaustion)
and concept.md §7 mandatory limiters (max_cycles, max_tool_calls, etc.).

Pure application. Depends on ports (Budget value-object); no I/O (R002).
"""

from __future__ import annotations

from dataclasses import dataclass, field


class BudgetExhausted(Exception):
    """Raised when a budget limit is exceeded."""

    def __init__(self, resource: str, used: float, limit: float | None) -> None:
        self.resource = resource
        self.used = used
        self.limit = limit
        super().__init__(
            f"Budget exhausted: {resource}={used} exceeds limit={limit}"
        )


@dataclass
class BudgetController:
    """Tracks resource consumption against budget limits.

    Usage::

        ctrl = BudgetController(max_llm_calls=10, max_tool_calls=5)
        ctrl.track(llm_calls=1)
        if ctrl.is_exhausted():
            return partial_result(...)
    """

    max_llm_calls: int | None = None
    max_tool_calls: int | None = None
    max_cost_usd: float | None = None

    _llm_calls: int = field(default=0, init=False)
    _tool_calls: int = field(default=0, init=False)
    _cost_usd: float = field(default=0.0, init=False)

    def track(
        self,
        *,
        llm_calls: int = 0,
        tool_calls: int = 0,
        cost_usd: float = 0.0,
    ) -> None:
        """Add to the consumption counters."""
        self._llm_calls += llm_calls
        self._tool_calls += tool_calls
        self._cost_usd += cost_usd

    def is_exhausted(self) -> bool:
        """True iff any resource has exceeded its limit."""
        if self.max_llm_calls is not None and self._llm_calls >= self.max_llm_calls:
            return True
        if self.max_tool_calls is not None and self._tool_calls >= self.max_tool_calls:
            return True
        return bool(self.max_cost_usd is not None and self._cost_usd >= self.max_cost_usd)

    def remaining(self) -> dict[str, int | float | None]:
        """Return remaining budget for each resource (None = unlimited)."""
        return {
            "llm_calls": (
                self.max_llm_calls - self._llm_calls
                if self.max_llm_calls is not None
                else None
            ),
            "tool_calls": (
                self.max_tool_calls - self._tool_calls
                if self.max_tool_calls is not None
                else None
            ),
            "cost_usd": (
                self.max_cost_usd - self._cost_usd
                if self.max_cost_usd is not None
                else None
            ),
        }

    def enforce(self) -> None:
        """Raise BudgetExhausted if any limit is exceeded."""
        if self.max_llm_calls is not None and self._llm_calls >= self.max_llm_calls:
            raise BudgetExhausted("llm_calls", self._llm_calls, self.max_llm_calls)
        if self.max_tool_calls is not None and self._tool_calls >= self.max_tool_calls:
            raise BudgetExhausted("tool_calls", self._tool_calls, self.max_tool_calls)
        if self.max_cost_usd is not None and self._cost_usd >= self.max_cost_usd:
            raise BudgetExhausted("cost_usd", self._cost_usd, self.max_cost_usd)

    @property
    def used(self) -> dict[str, int | float]:
        """Return current consumption."""
        return {
            "llm_calls": self._llm_calls,
            "tool_calls": self._tool_calls,
            "cost_usd": self._cost_usd,
        }
