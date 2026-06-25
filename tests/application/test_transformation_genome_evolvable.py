"""Conformance + behavior tests for TransformationGenomeEvolvable (M016 S03 T03).

Third concrete Evolvable case (after ModelGenome and PromptGenome per D004).
Wraps a tuple of TransformParams candidates and conforms to the Evolvable
Protocol: mutation_space, mutate, evaluate. The fitness signal is derived
from the best cycles-reduction ratio vs a baseline CompilerMetrics, so the
EvolutionEngine (M017) can rank candidate transformation sets.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from active_skill_system.application.evolvable_adapters import (
    TransformationGenomeEvolvable,
)
from active_skill_system.domain.compiler_types import (
    CompilerMetrics,
    CompilerNodeKind,
    TransformParams,
)
from active_skill_system.domain.evolvable import (
    Evolvable,
    FitnessSignal,
    MutationSpace,
)

# ── helpers ──────────────────────────────────────────────────────────────


def _tile(tile_size: int = 32) -> TransformParams:
    return TransformParams(
        transform_type=CompilerNodeKind.TRANSFORM_TILE,
        params={"tile_size": tile_size},
        legal=True,
    )


def _unroll(factor: int = 2) -> TransformParams:
    return TransformParams(
        transform_type=CompilerNodeKind.TRANSFORM_UNROLL,
        params={"unroll_factor": factor},
        legal=True,
    )


def _fusion(k: int = 2) -> TransformParams:
    return TransformParams(
        transform_type=CompilerNodeKind.TRANSFORM_FUSION,
        params={"fused_loops": k},
        legal=True,
    )


def _interchange() -> TransformParams:
    return TransformParams(
        transform_type=CompilerNodeKind.TRANSFORM_INTERCHANGE,
        params={},
        legal=True,
    )


def _baseline(cycles: int = 1000) -> CompilerMetrics:
    return CompilerMetrics(
        cycles=cycles,
        reg_pressure=10,
        spills=2,
        energy_proxy=1.0,
        is_valid=True,
    )


def _baseline_dict(cycles: int = 1000) -> dict:
    return {
        "cycles": cycles,
        "reg_pressure": 10,
        "spills": 2,
        "energy_proxy": 1.0,
        "is_valid": True,
    }


def _improving_invoker(baseline: CompilerMetrics) -> object:
    """An invoker that always returns an improved-metrics result for any args.

    Cycles cut in half (deterministic) — enough to beat the baseline so the
    FitnessSignal reports regression=False.
    """

    def _invoke(args: dict) -> tuple[bool, str]:
        improved = CompilerMetrics(
            cycles=max(1, baseline.cycles // 2),
            reg_pressure=baseline.reg_pressure,
            spills=baseline.spills,
            energy_proxy=baseline.energy_proxy,
            is_valid=True,
        )
        return (
            True,
            json.dumps(
                {
                    "cycles": improved.cycles,
                    "reg_pressure": improved.reg_pressure,
                    "spills": improved.spills,
                    "energy_proxy": improved.energy_proxy,
                    "is_valid": improved.is_valid,
                },
                sort_keys=True,
            ),
        )

    return _invoke


def _regressing_invoker() -> object:
    """An invoker that always returns WORSE metrics — never improves."""

    def _invoke(args: dict) -> tuple[bool, str]:
        worse = CompilerMetrics(
            cycles=9999,
            reg_pressure=999,
            spills=999,
            energy_proxy=99.9,
            is_valid=True,
        )
        return (
            True,
            json.dumps(
                {
                    "cycles": worse.cycles,
                    "reg_pressure": worse.reg_pressure,
                    "spills": worse.spills,
                    "energy_proxy": worse.energy_proxy,
                    "is_valid": worse.is_valid,
                },
                sort_keys=True,
            ),
        )

    return _invoke


def _failing_invoker() -> object:
    """An invoker that always reports failure — the candidate is skipped."""

    def _invoke(args: dict) -> tuple[bool, str]:
        return (False, "")

    return _invoke


def _malformed_invoker() -> object:
    """An invoker that returns garbage JSON — the candidate is skipped."""

    def _invoke(args: dict) -> tuple[bool, str]:
        return (True, "{this is not json")

    return _invoke


# ── Evolvable conformance ────────────────────────────────────────────────


def test_transformation_genome_evolvable_is_evolvable() -> None:
    assert isinstance(TransformationGenomeEvolvable(invoker=_improving_invoker(_baseline())), Evolvable)


def test_mutation_space_is_a_mutation_space() -> None:
    ms = TransformationGenomeEvolvable(invoker=_improving_invoker(_baseline())).mutation_space
    assert isinstance(ms, MutationSpace)
    assert ms.description
    assert ms.mutate_fn_name
    # The description should mention the three strategies.
    assert "TILE" in ms.description
    assert "UNROLL" in ms.description
    assert "FUSION" in ms.description


def test_mutate_returns_new_tuple_of_transform_params() -> None:
    original = (_tile(tile_size=32),)
    mutated = TransformationGenomeEvolvable(invoker=_improving_invoker(_baseline())).mutate(original)
    assert isinstance(mutated, tuple)
    assert len(mutated) == 1
    assert isinstance(mutated[0], TransformParams)
    assert mutated[0].transform_type is CompilerNodeKind.TRANSFORM_TILE
    # TILE 32 -> 40 (bump by +8).
    assert mutated[0].params["tile_size"] == 40


def test_init_rejects_missing_invoker() -> None:
    """Construction without an invoker must fail fast — production wiring
    lives in the composition layer, not as a hidden default.
    """
    with pytest.raises((TypeError, ValueError)):
        TransformationGenomeEvolvable()  # type: ignore[call-arg]  # pyright: ignore


def test_evaluate_returns_fitness_signal() -> None:
    e = TransformationGenomeEvolvable(invoker=_improving_invoker(_baseline()))
    result = e.evaluate((_tile(tile_size=10),), {"baseline_metrics": _baseline_dict()})
    assert isinstance(result, FitnessSignal)
    assert 0.0 <= result.quality <= 1.0
    assert result.latency == 1.0
    assert result.regression is False


# ── Mutation: each strategy ──────────────────────────────────────────────


def test_mutate_tile_bumps_size_by_8() -> None:
    # 32 -> 40, 200 -> 208 (capped at 256).
    e = TransformationGenomeEvolvable(invoker=_improving_invoker(_baseline()))
    mutated = e.mutate((_tile(tile_size=32),))
    assert mutated[0].params["tile_size"] == 40


def test_mutate_tile_caps_at_256() -> None:
    e = TransformationGenomeEvolvable(invoker=_improving_invoker(_baseline()))
    mutated = e.mutate((_tile(tile_size=256),))
    # Already at cap — must not change (avoids infinite regression on no-op).
    assert mutated[0].params["tile_size"] == 256


def test_mutate_unroll_doubles_factor() -> None:
    e = TransformationGenomeEvolvable(invoker=_improving_invoker(_baseline()))
    mutated = e.mutate((_unroll(factor=2),))
    # 2 -> 4 (double, cap 16).
    assert mutated[0].params["unroll_factor"] == 4


def test_mutate_unroll_caps_at_16() -> None:
    e = TransformationGenomeEvolvable(invoker=_improving_invoker(_baseline()))
    mutated = e.mutate((_unroll(factor=16),))
    assert mutated[0].params["unroll_factor"] == 16


def test_mutate_fusion_increments_k() -> None:
    e = TransformationGenomeEvolvable(invoker=_improving_invoker(_baseline()))
    mutated = e.mutate((_fusion(k=2),))
    # 2 -> 3 (cap 4).
    assert mutated[0].params["fused_loops"] == 3


def test_mutate_fusion_caps_at_4() -> None:
    e = TransformationGenomeEvolvable(invoker=_improving_invoker(_baseline()))
    mutated = e.mutate((_fusion(k=4),))
    assert mutated[0].params["fused_loops"] == 4


def test_mutate_interchange_is_no_op() -> None:
    # INTERCHANGE has no deterministic numeric parameter to bump.
    e = TransformationGenomeEvolvable(invoker=_improving_invoker(_baseline()))
    original = (_interchange(),)
    mutated = e.mutate(original)
    assert mutated[0].params == {}


def test_mutate_picks_first_applicable_strategy() -> None:
    # INTERCHANGE first (no-op), then TILE (mutable). Mutate should bump TILE.
    e = TransformationGenomeEvolvable(invoker=_improving_invoker(_baseline()))
    mutated = e.mutate((_interchange(), _tile(tile_size=32)))
    assert mutated[0].params == {}  # INTERCHANGE unchanged
    assert mutated[1].params["tile_size"] == 40  # TILE bumped


def test_mutate_empty_genome_returns_empty() -> None:
    e = TransformationGenomeEvolvable(invoker=_improving_invoker(_baseline()))
    assert e.mutate(()) == ()


# ── Mutation: type safety ────────────────────────────────────────────────


def test_mutate_rejects_non_tuple_genome() -> None:
    e = TransformationGenomeEvolvable(invoker=_improving_invoker(_baseline()))
    with pytest.raises(TypeError):
        e.mutate([_tile()])  # list, not tuple


def test_mutate_rejects_non_transform_params_element() -> None:
    e = TransformationGenomeEvolvable(invoker=_improving_invoker(_baseline()))
    with pytest.raises(TypeError):
        e.mutate(({"not": "a transform"},))


# ── Evaluate: regression behavior ────────────────────────────────────────


def test_evaluate_regression_true_when_no_candidate_improves() -> None:
    e = TransformationGenomeEvolvable(invoker=_regressing_invoker())
    result = e.evaluate(
        (_tile(tile_size=10), _unroll(factor=4)),
        {"baseline_metrics": _baseline_dict()},
    )
    assert result.regression is True
    # Quality is the best reduction ratio across candidates — 0.0 here because
    # no candidate improved the baseline.
    assert result.quality == 0.0
    # Cost equals number of candidates tried.
    assert result.cost == 2.0


def test_evaluate_regression_false_when_any_candidate_improves() -> None:
    # First candidate regresses, second improves. Quality picks the winner.
    calls: list[dict] = []

    def _invoke(args: dict) -> tuple[bool, str]:
        calls.append(args)
        idx = len(calls)
        if idx == 1:
            # First candidate: regress.
            worse = _baseline(cycles=9999)
        else:
            # Second candidate: improve by 50%.
            better = _baseline(cycles=max(1, _baseline().cycles // 2))
            return (
                True,
                json.dumps(
                    {
                        "cycles": better.cycles,
                        "reg_pressure": better.reg_pressure,
                        "spills": better.spills,
                        "energy_proxy": better.energy_proxy,
                        "is_valid": better.is_valid,
                    },
                    sort_keys=True,
                ),
            )
        return (
            True,
            json.dumps(
                {
                    "cycles": worse.cycles,
                    "reg_pressure": worse.reg_pressure,
                    "spills": worse.spills,
                    "energy_proxy": worse.energy_proxy,
                    "is_valid": worse.is_valid,
                },
                sort_keys=True,
            ),
        )

    e = TransformationGenomeEvolvable(invoker=_invoke)
    result = e.evaluate(
        (_tile(tile_size=10), _unroll(factor=4)),
        {"baseline_metrics": _baseline_dict()},
    )
    assert result.regression is False
    # Best cycles-reduction ratio across candidates: 0.5 (50% improvement).
    assert result.quality == pytest.approx(0.5)


# ── Evaluate: failure handling ───────────────────────────────────────────


def test_evaluate_skips_candidates_with_tool_failure() -> None:
    # All candidates fail — nothing tried successfully.
    e = TransformationGenomeEvolvable(invoker=_failing_invoker())
    result = e.evaluate(
        (_tile(tile_size=10), _unroll(factor=4)),
        {"baseline_metrics": _baseline_dict()},
    )
    # No candidate beat the baseline (none even produced metrics).
    assert result.regression is True
    assert result.quality == 0.0
    # Cost still counts attempts.
    assert result.cost == 2.0


def test_evaluate_skips_candidates_with_malformed_payload() -> None:
    e = TransformationGenomeEvolvable(invoker=_malformed_invoker())
    result = e.evaluate(
        (_tile(tile_size=10),),
        {"baseline_metrics": _baseline_dict()},
    )
    assert result.regression is True
    assert result.quality == 0.0


def test_evaluate_respects_max_candidates() -> None:
    # max_candidates=1 means only the first candidate is tried even though
    # the genome has three.
    call_count = 0

    def _invoke(args: dict) -> tuple[bool, str]:
        nonlocal call_count
        call_count += 1
        # Always improve.
        better = CompilerMetrics(
            cycles=max(1, _baseline().cycles // 2),
            reg_pressure=10,
            spills=2,
            energy_proxy=1.0,
            is_valid=True,
        )
        return (
            True,
            json.dumps(
                {
                    "cycles": better.cycles,
                    "reg_pressure": better.reg_pressure,
                    "spills": better.spills,
                    "energy_proxy": better.energy_proxy,
                    "is_valid": better.is_valid,
                },
                sort_keys=True,
            ),
        )

    e = TransformationGenomeEvolvable(invoker=_invoke)
    e.evaluate(
        (_tile(tile_size=10), _unroll(factor=4), _fusion(k=2)),
        {"baseline_metrics": _baseline_dict(), "max_candidates": 1},
    )
    assert call_count == 1


def test_evaluate_clamps_quality_to_unit_interval() -> None:
    # Even if a candidate somehow improves cycles below 0 (it can't here,
    # but the contract should hold), quality must stay in [0.0, 1.0].
    e = TransformationGenomeEvolvable(invoker=_improving_invoker(_baseline()))
    result = e.evaluate((_tile(tile_size=10),), {"baseline_metrics": _baseline_dict()})
    assert 0.0 <= result.quality <= 1.0


# ── R002 (module infra-free) ─────────────────────────────────────────────


def test_module_infra_free() -> None:
    """The evolvable_adapters module must not import infra (R002).

    A late-bound L3 import inside __init__ is allowed (it is the documented
    production-wiring seam). Direct module-level imports of activegraph /
    anthropic / openai are forbidden.
    """
    mod = importlib.import_module("active_skill_system.application.evolvable_adapters")
    src = Path(mod.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "import activegraph",
        "from activegraph",
        "import anthropic",
        "import openai",
    ):
        assert forbidden not in src, (
            f"evolvable_adapters.py must not contain '{forbidden}' (R002 - application is infra-free)"
        )
