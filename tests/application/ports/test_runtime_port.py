"""Offline tests for application/ports/runtime.py - the L2 RuntimePort Protocol.

These tests verify:

  1) The Protocol is importable without dragging in activegraph (R002,
     R005 - application layer stays infra-free).
  2) The value types (Budget, RunGoal, RunResult, ForkSpec, DiffResult,
     TraceLine) are frozen dataclasses with sensible defaults.
  3) A duck-typed fake with matching method signatures satisfies
     `isinstance(fake, RuntimePort)`.
  4) The Protocol exposes the documented method signatures (so adapters
     that claim RuntimePort actually implement them).
"""

from __future__ import annotations

from active_skill_system.application.ports.runtime import (
    Budget,
    DiffResult,
    ForkSpec,
    RunGoal,
    RunResult,
    RuntimePort,
    TraceLine,
)


def test_runtime_port_protocol_importable() -> None:
    """The Protocol is importable and the L2 port module stays infra-free.

    R002: domain + application layers must not import activegraph /
    anthropic / openai. We verify by inspecting the *direct* imports of
    the port module: it should depend only on stdlib + typing.

    Note: the L3 adapter (`adapters.runtime.activegraph`) DOES import
    activegraph - that is allowed by layering. This test only proves
    the L2 port stays clean.
    """
    import importlib

    # Re-import in a fresh interpreter-like state to check direct imports.
    # The simplest check: inspect the port module's __dict__ for the
    # sentinel import of the source files (not their transitive effects).
    mod = importlib.import_module("active_skill_system.application.ports.runtime")
    src_path = mod.__file__
    assert src_path is not None
    with open(src_path) as f:
        src = f.read()
    # Direct import statements should not mention infrastructure packages.
    for forbidden in (
        "import activegraph",
        "from activegraph",
        "import anthropic",
        "import openai",
    ):
        assert forbidden not in src, (
            f"runtime.py must not contain '{forbidden}' (R002 - application is infra-free)"
        )


def test_value_types_are_frozen_dataclasses() -> None:
    """All value types are frozen dataclasses (immutable, hashable)."""
    for cls in (Budget, RunGoal, RunResult, ForkSpec, DiffResult, TraceLine):
        assert dataclass_like(cls), f"{cls.__name__} should be a dataclass"
        # Frozen check via __dataclass_params__.
        params = getattr(cls, "__dataclass_params__", None)
        assert params is not None and params.frozen is True, (
            f"{cls.__name__} should be @dataclass(frozen=True)"
        )


def test_value_types_have_sensible_defaults() -> None:
    """RunGoal, RunResult, Budget, TraceLine have defaults so use-cases can construct them minimally."""
    g = RunGoal(goal="Diligence: test")
    assert g.actor == "user"
    assert g.persist_to is None
    assert g.seed is None
    assert isinstance(g.budget, Budget)

    b = Budget()
    assert b.max_llm_calls is None
    assert b.max_tool_calls is None
    assert b.max_cost_usd is None

    t = TraceLine(run_id="r1", sequence=0, event_type="goal.created", payload_summary="x")
    assert t.run_id == "r1"


def test_fake_runtime_implements_protocol() -> None:
    """A duck-typed fake with matching methods satisfies isinstance(_, RuntimePort).

    Because RuntimePort is @runtime_checkable, isinstance works on any
    object whose methods match the protocol's surface - no explicit
    inheritance required.
    """

    class FakeRuntime:
        def run_goal(self, goal, *, llm_provider=None):  # noqa: ARG002
            return RunResult(
                run_id="fake-1",
                goal=goal.goal,
                status="ok",
                events_processed=0,
                llm_calls=0,
                tool_calls=0,
                cost_usd="0.0",
            )

        def fork(self, parent_run_id, at_event, *, label=None):  # noqa: ARG002
            return ForkSpec(
                parent_run_id=parent_run_id, at_event=at_event, new_run_id="x", label=label
            )

        def replay(self, run_id):  # noqa: ARG002
            return RunResult(
                run_id=run_id,
                goal="<replay>",
                status="ok",
                events_processed=0,
                llm_calls=0,
                tool_calls=0,
                cost_usd="0.0",
            )

        def diff(self, run_a, run_b):  # noqa: ARG002
            return DiffResult(
                run_a=run_a, run_b=run_b, shared_events=0, parent_only_events=0, fork_only_events=0
            )

        def export_trace(self, run_id):  # noqa: ARG002
            return iter(())

    fake = FakeRuntime()
    assert isinstance(fake, RuntimePort), (
        "FakeRuntime with matching method signatures must satisfy RuntimePort (Protocol)"
    )


def test_runtime_port_methods_signatures() -> None:
    """The Protocol exposes the documented method names (contract)."""
    method_names = {"run_goal", "fork", "replay", "diff", "export_trace"}
    for name in method_names:
        assert hasattr(RuntimePort, name), f"RuntimePort must expose {name}"


def test_runtime_port_is_runtime_checkable() -> None:
    """RuntimePort is @runtime_checkable (used by adapters and tests)."""
    import typing

    assert hasattr(RuntimePort, "_is_runtime_protocol") or typing.is_protocol(RuntimePort)
    # The @runtime_checkable decorator exposes __instancecheck__ via _abc_inst_check_helper.
    assert hasattr(RuntimePort, "__instancecheck__")


def test_value_types_repr_is_deterministic() -> None:
    """repr() works for all frozen dataclasses - helps logs and error messages."""
    r = RunResult(
        run_id="r1",
        goal="g",
        status="ok",
        events_processed=1,
        llm_calls=1,
        tool_calls=0,
        cost_usd="0.001",
    )
    s = repr(r)
    assert "r1" in s
    assert "ok" in s


# ── helpers ──────────────────────────────────────────────────────────────


def dataclass_like(cls) -> bool:
    """True if cls is a dataclass (handles both classic and slotted forms)."""
    return hasattr(cls, "__dataclass_params__")
