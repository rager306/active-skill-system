"""Offline tests for application/use_cases/run_reasoning.py.

The first application-layer use-case (`RunReasoningUseCase`) orchestrates a
reasoning goal through the S01 `RuntimePort` while staying infra-free
(no activegraph / anthropic / openai imports anywhere in the test).

Coverage:
  1) Happy path returns the runtime's RunResult.
  2) `goal`, `actor`, `persist_to`, `seed` are forwarded into `RunGoal`.
  3) Budget is forwarded; defaults to `Budget()` when omitted.
  4) Optional LLM provider is forwarded to `runtime.run_goal`;
     `None` is forwarded when the use-case was constructed without one.
  5) Blank / whitespace-only goals raise `ValueError`.
  6) Invalid input never reaches the runtime.
  7) A failed `RunResult.status` is propagated honestly (no translation).
  8) The package import / re-export works.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from active_skill_system.application.ports.llm import LLMProviderPort
from active_skill_system.application.ports.runtime import (
    Budget,
    DiffResult,
    ForkSpec,
    RunGoal,
    RunResult,
    RuntimePort,
)
from active_skill_system.application.use_cases import RunReasoningUseCase
from active_skill_system.application.use_cases.run_reasoning import RunReasoningRequest

# ── fakes ─────────────────────────────────────────────────────────────────


class _FakeRuntime:
    """Duck-typed fake that satisfies `RuntimePort` via structural typing.

    Records every `run_goal` call so tests can assert what the use-case
    forwarded. Other Protocol methods are stubs (they are not exercised
    by `RunReasoningUseCase`).
    """

    def __init__(self) -> None:
        self.calls: list[tuple[RunGoal, Any]] = []
        self.next_result: RunResult | None = None

    def run_goal(
        self, goal: RunGoal, *, llm_provider: Any | None = None
    ) -> RunResult:  # noqa: ARG002 - protocol signature
        self.calls.append((goal, llm_provider))
        if self.next_result is not None:
            return self.next_result
        return RunResult(
            run_id="fake-run-1",
            goal=goal.goal,
            status="ok",
            events_processed=0,
            llm_calls=0,
            tool_calls=0,
            cost_usd="0.0",
        )

    # Protocol surface — unused by RunReasoningUseCase but required for
    # `isinstance(fake, RuntimePort)` to remain true.
    def fork(  # pragma: no cover - not exercised
        self,
        parent_run_id: str,
        at_event: str,
        *,
        label: str | None = None,
    ) -> ForkSpec:
        return ForkSpec(
            parent_run_id=parent_run_id,
            at_event=at_event,
            new_run_id="unused",
            label=label,
        )

    def replay(self, run_id: str) -> RunResult:  # pragma: no cover - not exercised
        return RunResult(
            run_id=run_id,
            goal="<replay>",
            status="ok",
            events_processed=0,
            llm_calls=0,
            tool_calls=0,
            cost_usd="0.0",
        )

    def diff(self, run_a: str, run_b: str) -> DiffResult:  # pragma: no cover - not exercised
        return DiffResult(
            run_a=run_a,
            run_b=run_b,
            shared_events=0,
            parent_only_events=0,
            fork_only_events=0,
        )

    def export_trace(self, run_id: str) -> Any:  # pragma: no cover - not exercised
        return iter(())


@dataclass
class _FakeLLM:
    """Duck-typed fake that satisfies `LLMProviderPort` structurally."""

    default_model: str = "fake-model"

    def complete(self, **kwargs: Any) -> Any:  # pragma: no cover - not exercised
        return None


# ── tests ─────────────────────────────────────────────────────────────────


def test_run_happy_path_returns_runtime_result() -> None:
    """A minimal request round-trips a `RunResult` from the runtime."""
    runtime = _FakeRuntime()
    use_case = RunReasoningUseCase(runtime)

    result = use_case.run(RunReasoningRequest(goal="Diligence: explore X"))

    assert isinstance(result, RunResult)
    assert result.run_id == "fake-run-1"
    assert result.goal == "Diligence: explore X"
    assert result.status == "ok"
    assert runtime.calls, "runtime.run_goal must have been invoked exactly once"


def test_run_forwards_goal_actor_persist_to_seed_into_run_goal() -> None:
    """All non-budget fields of the request land on the constructed `RunGoal`."""
    runtime = _FakeRuntime()
    use_case = RunReasoningUseCase(runtime)

    use_case.run(
        RunReasoningRequest(
            goal="Diligence: explore",
            actor="analyst",
            persist_to="/tmp/diligence.db",
            seed=42,
        )
    )

    assert len(runtime.calls) == 1
    forwarded_goal, _ = runtime.calls[0]
    assert isinstance(forwarded_goal, RunGoal)
    assert forwarded_goal.goal == "Diligence: explore"
    assert forwarded_goal.actor == "analyst"
    assert forwarded_goal.persist_to == "/tmp/diligence.db"
    assert forwarded_goal.seed == 42


def test_run_forwards_budget_into_run_goal() -> None:
    """An explicit `Budget` on the request is forwarded verbatim."""
    runtime = _FakeRuntime()
    use_case = RunReasoningUseCase(runtime)

    budget = Budget(max_llm_calls=5, max_tool_calls=10, max_cost_usd="0.50")
    use_case.run(RunReasoningRequest(goal="Diligence: cap", budget=budget))

    forwarded_goal, _ = runtime.calls[0]
    assert forwarded_goal.budget == budget


def test_run_defaults_budget_when_request_omits_it() -> None:
    """Omitting `budget` constructs a `RunGoal` with `Budget()` defaults."""
    runtime = _FakeRuntime()
    use_case = RunReasoningUseCase(runtime)

    use_case.run(RunReasoningRequest(goal="Diligence: default"))

    forwarded_goal, _ = runtime.calls[0]
    assert forwarded_goal.budget == Budget()


def test_run_forwards_optional_llm_provider_to_runtime() -> None:
    """An `LLMProviderPort` passed to the use-case is forwarded to the runtime."""
    runtime = _FakeRuntime()
    llm = _FakeLLM()
    assert isinstance(llm, LLMProviderPort)  # structural sanity

    use_case = RunReasoningUseCase(runtime, llm_provider=llm)
    use_case.run(RunReasoningRequest(goal="Diligence: llm"))

    _, llm_arg = runtime.calls[0]
    assert llm_arg is llm


def test_run_forwards_none_when_no_llm_provider_was_injected() -> None:
    """Without an LLM the use-case explicitly forwards `None` to the runtime."""
    runtime = _FakeRuntime()
    use_case = RunReasoningUseCase(runtime)

    use_case.run(RunReasoningRequest(goal="Diligence: no-llm"))

    _, llm_arg = runtime.calls[0]
    assert llm_arg is None


@pytest.mark.parametrize(
    ("bad_goal", "label"),
    [
        ("", "empty string"),
        (" ", "single space"),
        ("   ", "multiple spaces"),
        ("\t", "tab"),
        ("\n", "newline"),
        (" \t\n ", "mixed whitespace"),
    ],
)
def test_blank_or_whitespace_goal_raises_value_error(
    bad_goal: str, label: str
) -> None:
    """Blank / whitespace-only goals raise `ValueError` before the runtime runs."""
    runtime = _FakeRuntime()
    use_case = RunReasoningUseCase(runtime)

    with pytest.raises(ValueError):
        use_case.run(RunReasoningRequest(goal=bad_goal))

    assert runtime.calls == [], (
        f"runtime must not be invoked for {label}; got calls={runtime.calls}"
    )


def test_invalid_goal_does_not_call_runtime() -> None:
    """Invalid input short-circuits before `runtime.run_goal` is reached."""
    runtime = _FakeRuntime()
    use_case = RunReasoningUseCase(runtime, llm_provider=_FakeLLM())

    with pytest.raises(ValueError):
        use_case.run(RunReasoningRequest(goal=""))

    assert runtime.calls == [], (
        "Use-case must not call the runtime when validation fails; "
        f"got calls={runtime.calls}"
    )


def test_failed_runtime_result_returned_honestly() -> None:
    """A `failed` (or otherwise non-`ok`) `RunResult` propagates verbatim."""
    runtime = _FakeRuntime()
    runtime.next_result = RunResult(
        run_id="r-failed",
        goal="Diligence: doomed",
        status="failed",
        events_processed=3,
        llm_calls=1,
        tool_calls=0,
        cost_usd="0.001",
        claim_count=0,
        evidence_count=0,
        memo_count=0,
        failure_count=2,
    )
    use_case = RunReasoningUseCase(runtime)

    result = use_case.run(RunReasoningRequest(goal="Diligence: doomed"))

    assert result is runtime.next_result, (
        "Use-case must return the runtime's RunResult object directly "
        "(no copy, no translation)."
    )
    assert result.status == "failed"
    assert result.failure_count == 2
    assert result.events_processed == 3
    assert result.llm_calls == 1
    assert result.cost_usd == "0.001"


def test_use_case_is_infra_free() -> None:
    """The use-case module must not import activegraph / anthropic / openai.

    Reinforces R002 + the layering contract: application-layer code stays
    independent of infrastructure.
    """
    import importlib

    mod = importlib.import_module("active_skill_system.application.use_cases.run_reasoning")
    src_path = mod.__file__
    assert src_path is not None
    with open(src_path) as f:
        src = f.read()
    for forbidden in (
        "import activegraph",
        "from activegraph",
        "import anthropic",
        "import openai",
    ):
        assert forbidden not in src, (
            f"run_reasoning.py must not contain '{forbidden}' (R002 - application is infra-free)"
        )


def test_public_package_export_works() -> None:
    """`from active_skill_system.application.use_cases import RunReasoningUseCase` resolves."""
    from active_skill_system.application.use_cases import RunReasoningUseCase as Imported

    assert Imported is RunReasoningUseCase


def test_fake_runtime_satisfies_runtime_port_protocol() -> None:
    """The test fake must satisfy `RuntimePort` so the use-case contract is honored."""
    runtime = _FakeRuntime()
    assert isinstance(runtime, RuntimePort), (
        "Duck-typed _FakeRuntime must satisfy RuntimePort (structural)"
    )


def test_use_case_invokes_runtime_exactly_once() -> None:
    """The use-case performs exactly one `runtime.run_goal` call per `run()`."""
    runtime = _FakeRuntime()
    use_case = RunReasoningUseCase(runtime)

    use_case.run(RunReasoningRequest(goal="Diligence: once"))
    use_case.run(RunReasoningRequest(goal="Diligence: twice"))

    assert len(runtime.calls) == 2, (
        f"Expected exactly two runtime calls; got {len(runtime.calls)}"
    )
