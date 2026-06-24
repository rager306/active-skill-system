"""Offline tests for adapters/runtime/activegraph.py - the L3 RuntimePort adapter.

These tests verify:

  1) ActiveGraphRuntimeAdapter is duck-typed-compatible with RuntimePort
     (isinstance works because of @runtime_checkable).
  2) __init__ is lazy: constructing the adapter does NOT create a
     Graph() or Runtime() (R008 - no side-effects on import; R006 -
     cheap to instantiate in tests).
  3) run_goal propagates the goal and budget through the default factory
     (using a recording fake runtime instead of activegraph.Runtime so
     the test stays offline and deterministic).
  4) NotImplementedError methods (fork / replay / diff / export_trace)
     are correctly marked for S05.
"""

from __future__ import annotations

import pytest

from active_skill_system.adapters.runtime.activegraph import (
    ActiveGraphRuntimeAdapter,
)
from active_skill_system.application.ports.runtime import (
    Budget,
    RunGoal,
    RuntimePort,
)


def test_adapter_class_satisfies_runtime_port_protocol() -> None:
    """isinstance(adapter, RuntimePort) == True via duck-typed Protocol.

    Confirms that the adapter's method signatures match the Protocol's
    surface (run_goal, fork, replay, diff, export_trace).
    """
    adapter = ActiveGraphRuntimeAdapter()
    assert isinstance(adapter, RuntimePort), (
        "ActiveGraphRuntimeAdapter must satisfy RuntimePort Protocol"
    )


def test_adapter_constructor_is_lazy() -> None:
    """Constructing the adapter does NOT create Graph() or Runtime().

    This is the core of R008 / R006: cheap instantiation, no I/O on import.
    We can't observe the absence of side-effects directly, but we can
    verify that supplying a custom factory (that records the call)
    is NOT invoked at __init__.
    """
    factory_calls: list[RunGoal] = []

    def recording_factory(goal: RunGoal):
        factory_calls.append(goal)
        raise RuntimeError("factory should not be called at __init__")

    ActiveGraphRuntimeAdapter(runtime_factory=recording_factory)
    assert factory_calls == [], (
        "RuntimeFactory must not be called during __init__ (lazy construction, R008)"
    )


def test_adapter_default_factory_signature() -> None:
    """The default factory is a RuntimeFactory callable taking a RunGoal."""
    adapter = ActiveGraphRuntimeAdapter()
    assert adapter._factory is not None
    assert callable(adapter._factory)


def test_adapter_run_goal_propagates_goal_via_factory() -> None:
    """run_goal invokes the factory with the RunGoal and returns RunResult.

    Uses a recording fake factory instead of a real Runtime so the test
    stays offline (no activegraph runtime startup, no network, no DB).
    """
    captured: dict = {}

    def fake_factory(goal: RunGoal):
        captured["goal"] = goal

        class _StubRuntime:
            run_id = "stub-1"

            def run_goal(self, g: str, *, actor: str = "user") -> None:
                captured["ran_goal"] = g
                captured["actor"] = actor

            def status(self, recent: int = 20) -> object:  # noqa: ARG002
                class _Status:
                    total_cost = 0.00123

                return _Status()

        return _StubRuntime()

    adapter = ActiveGraphRuntimeAdapter(runtime_factory=fake_factory)  # type: ignore[arg-type]
    result = adapter.run_goal(
        RunGoal(
            goal="Diligence: acme",
            actor="bot",
            persist_to=None,
            seed=42,
            budget=Budget(max_llm_calls=10),
        ),
    )
    assert captured["goal"].goal == "Diligence: acme"
    assert captured["goal"].actor == "bot"
    assert captured["goal"].seed == 42
    assert captured["ran_goal"] == "Diligence: acme"
    assert captured["actor"] == "bot"
    assert result.run_id == "stub-1"
    assert result.status == "ok"
    assert result.goal == "Diligence: acme"


def test_adapter_run_goal_returns_failed_status_on_exception() -> None:
    """If the stub runtime raises, the adapter returns a failed RunResult."""

    class _RaisingRuntime:
        run_id = "raising-1"

        def run_goal(self, g: str, *, actor: str = "user") -> None:  # noqa: ARG002
            raise RuntimeError("simulated runtime failure")

    def raising_factory(goal: RunGoal) -> object:  # noqa: ARG002
        return _RaisingRuntime()

    adapter = ActiveGraphRuntimeAdapter(runtime_factory=raising_factory)  # type: ignore[arg-type]
    result = adapter.run_goal(RunGoal(goal="x"))
    assert result.status == "failed"
    assert result.run_id == "raising-1"


def test_adapter_run_goal_injects_llm_provider() -> None:
    """When llm_provider is passed to run_goal, the adapter sets it on the runtime."""
    captured: dict = {}

    class _StubRuntime:
        run_id = "stub-2"
        llm_provider = None  # instance attribute, set by adapter below

        def run_goal(self, g: str, *, actor: str = "user") -> None:  # noqa: ARG002
            # Snapshot the instance's llm_provider at run-time so the
            # test observes what the adapter assigned, not the class attr.
            captured["llm_provider_at_run"] = self.llm_provider

        def status(self, recent: int = 20) -> object:  # noqa: ARG002
            class _Status:
                total_cost = 0.0

            return _Status()

    def factory(goal: RunGoal) -> object:  # noqa: ARG002
        return _StubRuntime()

    adapter = ActiveGraphRuntimeAdapter(runtime_factory=factory)  # type: ignore[arg-type]
    sentinel = object()
    adapter.run_goal(RunGoal(goal="y"), llm_provider=sentinel)
    assert captured["llm_provider_at_run"] is sentinel, (
        "adapter should assign llm_provider on the runtime before run_goal"
    )


@pytest.mark.parametrize(
    "method,args",
    [
        ("fork", ("parent-1", "evt_42")),
        ("replay", ("run-1",)),
        ("diff", ("run-a", "run-b")),
        ("export_trace", ("run-1",)),
    ],
)
def test_adapter_deferred_methods_raise_not_implemented(method: str, args: tuple) -> None:
    """fork / replay / diff / export_trace are deferred to S05 composition.

    This is documented behavior: the port signature is abstract, the
    adapter translates to activegraph-specific calls only when composition
    can supply the necessary plumbing (Runtime.load from persist_to).
    """
    adapter = ActiveGraphRuntimeAdapter()
    fn = getattr(adapter, method)
    with pytest.raises(NotImplementedError) as exc_info:
        fn(*args)
    assert "S05" in str(exc_info.value) or "composition" in str(exc_info.value).lower()
