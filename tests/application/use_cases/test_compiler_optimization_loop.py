"""Unit tests for CompilerOptimizationLoopUseCase (M016 S03 T02)."""

from __future__ import annotations

import json
from dataclasses import dataclass

from active_skill_system.application.ports.tool import (
    ToolCapability,
    ToolProfile,
    ToolResult,
)
from active_skill_system.application.tools.registry import ToolRegistry
from active_skill_system.application.use_cases.compiler_gap_detector import NO_GAP
from active_skill_system.application.use_cases.compiler_optimization_loop import (
    CompilerOptimizationLoopUseCase,
    LoopStatus,
    _parse_metrics,
)
from active_skill_system.application.use_cases.compiler_repair_policy import (
    CompilerRepairPolicy,
)
from active_skill_system.domain.compiler_types import (
    CompilerActionType,
    CompilerGapClass,
    CompilerMetrics,
    CompilerNodeKind,
    TransformParams,
)

# ── fake tools for deterministic testing ──────────────────────────────────


@dataclass
class FakeTool:
    """Records invocations and returns a programmable sequence of metrics."""

    name: str = "fake_compiler_tool"
    profile: ToolProfile = ToolProfile.NORMAL
    responses: tuple[dict, ...] = ()
    invocations: list[dict] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.invocations is None:
            self.invocations = []

    @property
    def capabilities(self) -> frozenset:
        return frozenset({ToolCapability.COMPUTE})

    def invoke(self, args: dict) -> ToolResult:
        self.invocations.append(args)
        if not self.responses:
            return ToolResult(text="", success=False)
        payload = self.responses[len(self.invocations) - 1]
        return ToolResult(text=json.dumps(payload), success=True)


# ── helpers ───────────────────────────────────────────────────────────────


def _baseline() -> CompilerMetrics:
    return CompilerMetrics(cycles=1000, reg_pressure=16, spills=4, energy_proxy=2.5)


def _good_metrics() -> dict:
    return {"cycles": 100, "reg_pressure": 8, "spills": 0, "energy_proxy": 0.5, "is_valid": True}


def _bad_metrics() -> dict:
    return {"cycles": 1500, "reg_pressure": 32, "spills": 16, "energy_proxy": 5.0, "is_valid": True}


def _tile_candidate(tile_size: int = 10) -> TransformParams:
    return TransformParams(
        transform_type=CompilerNodeKind.TRANSFORM_TILE,
        params={"tile_size": tile_size},
    )


# ── parse_metrics helper ──────────────────────────────────────────────────


def test_parse_metrics_ok() -> None:
    m = _parse_metrics(json.dumps(_good_metrics()))
    assert m is not None
    assert m.cycles == 100


def test_parse_metrics_invalid_json() -> None:
    assert _parse_metrics("not json") is None


def test_parse_metrics_non_dict() -> None:
    assert _parse_metrics("[1, 2, 3]") is None


def test_parse_metrics_missing_key() -> None:
    assert _parse_metrics(json.dumps({"cycles": 1, "reg_pressure": 1})) is None


def test_parse_metrics_negative_cycles_rejected() -> None:
    assert _parse_metrics(json.dumps({"cycles": -1, "reg_pressure": 0, "spills": 0, "energy_proxy": 0.0})) is None


# ── loop: success path ────────────────────────────────────────────────────


def test_completes_when_candidate_improves_metrics() -> None:
    tool = FakeTool(responses=(_good_metrics(),))
    reg = ToolRegistry()
    reg.register(tool)
    loop = CompilerOptimizationLoopUseCase(tool_registry=reg, max_cycles=3)
    result = loop.run(_baseline(), (_tile_candidate(),))
    assert result.status is LoopStatus.COMPLETED
    assert result.final_metrics.cycles == 100
    assert result.accepted_count == 1


def test_completes_records_trace_with_no_gap() -> None:
    tool = FakeTool(responses=(_good_metrics(),))
    reg = ToolRegistry()
    reg.register(tool)
    loop = CompilerOptimizationLoopUseCase(tool_registry=reg, max_cycles=3)
    result = loop.run(_baseline(), (_tile_candidate(),))
    # Trace records the gap observed between current and new_metrics.
    # new_metrics better_than current → gap is NO_GAP, action is APPLY_TRANSFORM, accepted=True.
    assert result.trace[-1] == (0, NO_GAP, CompilerActionType.APPLY_TRANSFORM.value, True)


# ── loop: no-improvement path ─────────────────────────────────────────────


def test_no_improvement_when_no_candidate_helps() -> None:
    tool = FakeTool(responses=(_bad_metrics(), _bad_metrics(), _bad_metrics()))
    reg = ToolRegistry()
    reg.register(tool)
    loop = CompilerOptimizationLoopUseCase(tool_registry=reg, max_cycles=3)
    result = loop.run(_baseline(), (_tile_candidate(), _tile_candidate(20), _tile_candidate(40)))
    assert result.status is LoopStatus.NO_IMPROVEMENT
    assert result.accepted_count == 0
    assert result.final_metrics.cycles == 1000  # baseline unchanged


def test_no_improvement_when_candidates_exhausted() -> None:
    tool = FakeTool(responses=(_bad_metrics(),))
    reg = ToolRegistry()
    reg.register(tool)
    loop = CompilerOptimizationLoopUseCase(tool_registry=reg, max_cycles=2)
    # Only 1 candidate but max_cycles=2; loop will run 2 iters but only 1 candidate.
    result = loop.run(_baseline(), (_tile_candidate(),))
    # After 1st iter: bad metrics, accepted=0 → continue
    # 2nd iter: i>=len(candidates) → break, status NO_IMPROVEMENT
    assert result.status is LoopStatus.NO_IMPROVEMENT
    assert result.candidates_tried == 1


# ── loop: terminal success on first accepted ──────────────────────────────


def test_stops_at_first_accepted_candidate() -> None:
    """The loop must stop as soon as ANY candidate is accepted (terminal success).

    Two good responses configured but only the first should be tried.
    """
    tool = FakeTool(responses=(_good_metrics(), _good_metrics()))
    reg = ToolRegistry()
    reg.register(tool)
    loop = CompilerOptimizationLoopUseCase(tool_registry=reg, max_cycles=5)
    result = loop.run(_baseline(), (_tile_candidate(), _tile_candidate(20), _tile_candidate(40)))
    assert result.status is LoopStatus.COMPLETED
    assert result.accepted_count == 1
    assert result.candidates_tried == 1  # did not try candidates[1] or [2]
    assert result.iterations_used == 1
    assert len(result.trace) == 1


def test_no_improvement_when_candidates_exhausted_via_break() -> None:
    """When max_cycles > len(candidates) and nothing was accepted,
    the loop exits with NO_IMPROVEMENT after exhausting candidates."""
    tool = FakeTool(responses=(_bad_metrics(),))
    reg = ToolRegistry()
    reg.register(tool)
    loop = CompilerOptimizationLoopUseCase(tool_registry=reg, max_cycles=5)
    result = loop.run(_baseline(), (_tile_candidate(),))
    assert result.status is LoopStatus.NO_IMPROVEMENT
    assert result.accepted_count == 0
    assert result.candidates_tried == 1


# ── loop: max_cycles limits candidates ────────────────────────────────────


def test_max_cycles_limits_how_many_candidates_are_tried() -> None:
    """When max_cycles < len(candidates), loop stops after max_cycles
    attempts even if more candidates exist."""
    tool = FakeTool(responses=(_bad_metrics(), _bad_metrics(), _bad_metrics()))
    reg = ToolRegistry()
    reg.register(tool)
    loop = CompilerOptimizationLoopUseCase(tool_registry=reg, max_cycles=2)
    cands = (_tile_candidate(10), _tile_candidate(20), _tile_candidate(40))
    result = loop.run(_baseline(), cands)
    assert result.candidates_tried == 2
    assert result.status is LoopStatus.NO_IMPROVEMENT


# ── loop: replan ──────────────────────────────────────────────────────────


def test_lowering_replan_action_terminates_loop() -> None:
    """If the classifier returns a gap whose mapped action is LOWERING_REPLAN,
    the loop should return REPLAN_REQUIRED after invoking the tool."""
    # Provide a response so the loop reaches the policy lookup. The action
    # mapping routes MISSING_TRANSFORM to LOWERING_REPLAN, which terminates.
    tool = FakeTool(responses=(_bad_metrics(),))
    reg = ToolRegistry()
    reg.register(tool)
    policy = CompilerRepairPolicy(mapping={
        CompilerGapClass.MISSING_TRANSFORM: CompilerActionType.LOWERING_REPLAN,
    })
    loop = CompilerOptimizationLoopUseCase(
        tool_registry=reg, policy=policy, max_cycles=3,
    )
    result = loop.run(_baseline(), (_tile_candidate(),))
    assert result.status is LoopStatus.REPLAN_REQUIRED
    assert len(tool.invocations) == 1  # tool was invoked, then policy stopped the loop


# ── loop: tool integration ───────────────────────────────────────────────


def test_loop_uses_registry_not_hardcoded_tool() -> None:
    tool = FakeTool(responses=(_good_metrics(),))
    reg = ToolRegistry()
    reg.register(tool)
    loop = CompilerOptimizationLoopUseCase(tool_registry=reg)
    result = loop.run(_baseline(), (_tile_candidate(),))
    assert len(tool.invocations) == 1
    assert tool.invocations[0]["transform_type"] == "transform_tile"
    assert tool.invocations[0]["params"]["tile_size"] == 10
    assert result.accepted_count == 1


def test_loop_fails_gracefully_when_no_tool_registered() -> None:
    reg = ToolRegistry()  # empty
    loop = CompilerOptimizationLoopUseCase(tool_registry=reg, max_cycles=3)
    result = loop.run(_baseline(), (_tile_candidate(),))
    assert result.status is LoopStatus.NO_IMPROVEMENT
    assert result.accepted_count == 0


def test_loop_handles_tool_failure() -> None:
    tool = FakeTool(responses=())  # no responses → success=False
    reg = ToolRegistry()
    reg.register(tool)
    loop = CompilerOptimizationLoopUseCase(tool_registry=reg, max_cycles=3)
    result = loop.run(_baseline(), (_tile_candidate(),))
    assert result.accepted_count == 0


def test_loop_with_real_compiler_tool_stub() -> None:
    """Integration test with the real CompilerToolStub (deterministic)."""
    from active_skill_system.adapters.compiler_tool_stub import CompilerToolStub

    tool = CompilerToolStub()
    reg = ToolRegistry()
    reg.register(tool)
    loop = CompilerOptimizationLoopUseCase(tool_registry=reg, max_cycles=1)
    result = loop.run(_baseline(), (_tile_candidate(tile_size=10),))
    # tile_size=10 → cycles 1000 → 100, spills 4 → 5 (4 + ceil(10/16)=4+1).
    # Spills 4→5 is a tolerable trade-off (not > 2x), so accepted.
    assert result.accepted_count == 1
    assert result.final_metrics.cycles == 100


# ── loop: max_cycles clamp ────────────────────────────────────────────────


def test_max_cycles_clamped_to_at_least_one() -> None:
    tool = FakeTool(responses=(_good_metrics(),))
    reg = ToolRegistry()
    reg.register(tool)
    # max_cycles=0 must be clamped to 1.
    loop = CompilerOptimizationLoopUseCase(tool_registry=reg, max_cycles=0)
    assert loop._max_cycles == 1
    result = loop.run(_baseline(), (_tile_candidate(),))
    assert result.iterations_used >= 1


# ── loop: defaults ───────────────────────────────────────────────────────


def test_default_policy_and_registry_used_when_not_provided() -> None:
    from active_skill_system.adapters.compiler_tool_stub import CompilerToolStub

    # Constructor without policy / registry should use defaults.
    loop = CompilerOptimizationLoopUseCase(max_cycles=1)
    assert loop._policy is not None
    assert loop._registry is not None
    # Inject the real tool and run.
    loop._registry.register(CompilerToolStub())
    result = loop.run(_baseline(), (_tile_candidate(tile_size=10),))
    assert result.accepted_count == 1


# ── module hygiene ────────────────────────────────────────────────────────


def test_module_infra_free() -> None:
    import importlib
    from pathlib import Path

    mod = importlib.import_module("active_skill_system.application.use_cases.compiler_optimization_loop")
    src = Path(mod.__file__).read_text()
    for forbidden in ("import activegraph", "from activegraph", "import anthropic", "import openai"):
        assert forbidden not in src, f"compiler_optimization_loop.py must not contain '{forbidden}' (R002)"
