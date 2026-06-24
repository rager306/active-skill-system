"""First application-layer use-case: run a reasoning goal through RuntimePort.

The use-case is the application's declared boundary for kicking off a
reasoning run. Composition (S05) wires the real `ActiveGraphRuntimeAdapter`
+ `MiniMaxProvider` into it; tests wire fakes. The use-case itself stays
infra-free: it imports only stdlib + the L2 ports, never activegraph /
anthropic / openai / adapters / composition.

Layering contract:
    - Depends on: `application.ports.runtime`, `application.ports.llm`.
    - Returns:    the S01 `RunResult` (verbatim, no translation).
    - Imports:    stdlib + L2 ports only.

Shape follows D003: a small `RunReasoningUseCase` class initialized with
a `RuntimePort` (and optional `LLMProviderPort`) plus a frozen
`RunReasoningRequest` value object.
"""

from __future__ import annotations

from dataclasses import dataclass

from active_skill_system.application.ports.llm import LLMProviderPort
from active_skill_system.application.ports.runtime import (
    Budget,
    RunGoal,
    RunResult,
    RuntimePort,
)


@dataclass(frozen=True)
class RunReasoningRequest:
    """Input to `RunReasoningUseCase.run()`.

    Mirrors the S01 `RunGoal` field set so the use-case does not need to
    invent a parallel vocabulary. `budget=None` means "use defaults"
    (a fresh `Budget()` is constructed at the seam).
    """

    goal: str
    actor: str = "user"
    persist_to: str | None = None
    seed: int | None = None
    budget: Budget | None = None


class RunReasoningUseCase:
    """Run a reasoning goal through the runtime port.

    Holds no state beyond the injected ports. Each `run()` call:
        1. Validates the request (non-empty, non-whitespace goal).
        2. Constructs an S01 `RunGoal` value object.
        3. Forwards the request to `runtime.run_goal(...)` exactly once,
           passing `llm_provider=self._llm_provider` (which may be `None`).
        4. Returns the runtime's `RunResult` verbatim.

    The use-case never raises on a runtime failure — `RunResult.status`
    is the application's honest signal for "ok / failed / budget_exceeded".
    """

    def __init__(
        self,
        runtime: RuntimePort,
        *,
        llm_provider: LLMProviderPort | None = None,
    ) -> None:
        self._runtime = runtime
        self._llm_provider = llm_provider

    def run(self, request: RunReasoningRequest) -> RunResult:
        """Run the request through the runtime port.

        Args:
            request: Typed request (goal + optional actor / persist_to /
                seed / budget).

        Returns:
            The runtime's `RunResult`, untouched. Callers should inspect
            `RunResult.status` to detect non-success outcomes.

        Raises:
            ValueError: If `request.goal` is empty, `None`, or whitespace-only.
                Validation runs before any port call, so the runtime is
                never invoked with an invalid goal.
        """
        goal_text = request.goal
        if not isinstance(goal_text, str) or not goal_text.strip():
            raise ValueError("request.goal must be a non-empty, non-whitespace string")

        run_goal = RunGoal(
            goal=goal_text,
            actor=request.actor,
            persist_to=request.persist_to,
            seed=request.seed,
            budget=request.budget if request.budget is not None else Budget(),
        )

        return self._runtime.run_goal(run_goal, llm_provider=self._llm_provider)
