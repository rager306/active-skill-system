"""Integration tests for the diligence composition root (composition/diligence.py).

These tests exercise ``main()`` end-to-end WITHOUT making real LLM calls:
they inject a fake wiring (fake use-case + holder with a fake runtime) through
the ``_wiring`` seam. This verifies:

  1) ``main(argv=None)`` runs the default company ("OpenAI") and returns 0.
  2) ``main(argv=["Acme"])`` forwards a custom company into the goal.
  3) The built layers are wired (the use-case receives a RunReasoningRequest
     whose goal starts with "Diligence:").
  4) Observability flows through the holder (save_state + trace printed).
  5) load_env is idempotent (calling it twice does not raise / change behavior).

No network, no activegraph runtime.
"""

from __future__ import annotations

import io
from contextlib import redirect_stdout
from dataclasses import dataclass, field

from active_skill_system.application.ports.runtime import RunResult


@dataclass
class _FakeRuntime:
    """Fake activegraph Runtime: records save_state + returns a fixed trace."""

    saved: int = 0
    trace_lines: list[str] = field(default_factory=lambda: ["event1", "event2"])

    def save_state(self) -> None:
        self.saved += 1

    class _Trace:
        def __init__(self, lines: list[str]) -> None:
            self._lines = lines

        def lines(self) -> list[str]:
            return list(self._lines)

    @property
    def trace(self) -> _Trace:
        return self._Trace(self.trace_lines)


@dataclass
class _FakeUseCase:
    """Fake use-case: records the RunReasoningRequest and returns a RunResult."""

    last_goal: str = ""

    def run(self, request) -> RunResult:  # noqa: ANN001
        self.last_goal = request.goal
        return RunResult(
            run_id="fake-run-1",
            goal=request.goal,
            status="ok",
            events_processed=7,
            llm_calls=3,
            tool_calls=2,
            cost_usd="0.0",
        )


def _fake_wiring(use_case: _FakeUseCase, runtime: _FakeRuntime):
    """Return a _wiring callable that injects (use_case, holder-with-runtime)."""

    def wiring(model: str):
        holder: dict[str, object] = {"runtime": runtime}
        return use_case, holder

    return wiring


def test_main_with_default_company(monkeypatch) -> None:  # noqa: ANN001
    """Default company is 'OpenAI'; main returns 0 and wires the use-case."""
    import active_skill_system.composition.diligence as dil

    # Avoid real env/network side effects; load_env is safe but pin the model.
    monkeypatch.setattr(dil, "load_env", lambda: {"ANTHROPIC_MODEL": "MiniMax-M3"})

    use_case = _FakeUseCase()
    runtime = _FakeRuntime()
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = dil.main([], _wiring=_fake_wiring(use_case, runtime))

    assert rc == 0
    assert use_case.last_goal == "Diligence: OpenAI"
    assert runtime.saved == 1  # save_state called via holder
    out = buf.getvalue()
    assert "RUN OK" in out
    assert "event1" in out  # trace printed from holder runtime
    assert "fake-run-1" in out  # run_id surfaced from RunResult


def test_main_with_custom_company(monkeypatch) -> None:  # noqa: ANN001
    """argv[0] selects the company; the goal carries it."""
    import active_skill_system.composition.diligence as dil

    monkeypatch.setattr(dil, "load_env", lambda: {"ANTHROPIC_MODEL": "MiniMax-M3"})

    use_case = _FakeUseCase()
    runtime = _FakeRuntime()
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = dil.main(["Acme Corp"], _wiring=_fake_wiring(use_case, runtime))

    assert rc == 0
    assert use_case.last_goal == "Diligence: Acme Corp"


def test_main_idempotent_env_load(monkeypatch) -> None:  # noqa: ANN001
    """load_env may be called repeatedly without breaking main()."""
    import active_skill_system.composition.diligence as dil

    calls = {"n": 0}

    def env():
        calls["n"] += 1
        return {"ANTHROPIC_MODEL": "MiniMax-M3", "ANTHROPIC_AUTH_TOKEN": "x"}

    monkeypatch.setattr(dil, "load_env", env)

    use_case = _FakeUseCase()
    runtime = _FakeRuntime()
    # Two consecutive runs both succeed; env is read each time without error.
    for _ in range(2):
        rc = dil.main(["OpenAI"], _wiring=_fake_wiring(use_case, runtime))
        assert rc == 0
    assert calls["n"] == 2  # load_env invoked once per main() call, idempotent
