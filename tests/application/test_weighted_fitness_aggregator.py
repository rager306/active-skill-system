"""Tests for WeightedFitnessAggregator (M025 S01)."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from active_skill_system.application.weighted_fitness_aggregator import (
    WeightedFitnessAggregator,
    WeightedFitnessScore,
)
from active_skill_system.domain.evolvable import FitnessSignal


def _sig(quality: float, regression: bool = False, cost: float = 1.0) -> FitnessSignal:
    return FitnessSignal(quality=quality, cost=cost, latency=1.0, regression=regression)


# ── WeightedFitnessScore structure ────────────────────────────────────────


def test_weighted_fitness_score_is_frozen() -> None:
    s = WeightedFitnessScore(score=0.5)
    with pytest.raises((AttributeError, Exception)):
        s.score = 0.9  # type: ignore[misc]


def test_weighted_fitness_score_rejects_out_of_range() -> None:
    with pytest.raises(ValueError, match=r"\[0\.0, 1\.0\]"):
        WeightedFitnessScore(score=1.5)
    with pytest.raises(ValueError, match=r"\[0\.0, 1\.0\]"):
        WeightedFitnessScore(score=-0.1)


# ── WeightedFitnessAggregator validation ─────────────────────────────────


def test_aggregator_rejects_empty_weights() -> None:
    with pytest.raises(ValueError, match="weights must be non-empty"):
        WeightedFitnessAggregator(weights={})


def test_aggregator_rejects_weights_not_summing_to_one() -> None:
    with pytest.raises(ValueError, match="sum to 1.0"):
        WeightedFitnessAggregator(weights={"a": 0.5, "b": 0.3})  # sum=0.8


def test_aggregator_rejects_negative_weights() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        WeightedFitnessAggregator(weights={"a": 1.5, "b": -0.5})  # sum=1.0 but b<0


def test_aggregator_rejects_non_dict_weights() -> None:
    with pytest.raises(TypeError, match="weights must be a dict"):
        WeightedFitnessAggregator(weights=[("a", 1.0)])  # type: ignore[arg-type]


# ── Aggregation ───────────────────────────────────────────────────────────


def test_aggregate_three_signals_weighted() -> None:
    """3 axes: cycles*0.5 + spills*0.3 + cache*0.2."""
    agg = WeightedFitnessAggregator(weights={"cycles": 0.5, "spills": 0.3, "cache": 0.2})
    result = agg.aggregate({
        "cycles": _sig(quality=0.8),
        "spills": _sig(quality=0.6),
        "cache": _sig(quality=1.0),
    })
    # 0.5*0.8 + 0.3*0.6 + 0.2*1.0 = 0.4 + 0.18 + 0.2 = 0.78
    assert result.score == pytest.approx(0.78)
    assert result.regression is False
    assert "0.7800" in result.reason


def test_aggregate_single_signal() -> None:
    agg = WeightedFitnessAggregator(weights={"only": 1.0})
    result = agg.aggregate({"only": _sig(quality=0.9)})
    assert result.score == pytest.approx(0.9)


def test_aggregate_empty_signals_returns_zero_score() -> None:
    agg = WeightedFitnessAggregator(weights={"a": 0.5, "b": 0.5})
    result = agg.aggregate({})
    assert result.score == 0.0
    assert result.regression is False
    assert "No signals matched" in result.reason


def test_aggregate_missing_signal_contributes_zero() -> None:
    agg = WeightedFitnessAggregator(weights={"a": 0.5, "b": 0.5})
    result = agg.aggregate({"a": _sig(quality=1.0)})  # b missing
    assert result.score == pytest.approx(0.5)  # only a contributes
    assert result.contributions["b"] == 0.0


def test_aggregate_regression_propagates_from_any_signal() -> None:
    """Any signal with regression=True blocks the aggregate."""
    agg = WeightedFitnessAggregator(weights={"a": 0.5, "b": 0.5})
    result = agg.aggregate({
        "a": _sig(quality=1.0, regression=False),
        "b": _sig(quality=0.9, regression=True),
    })
    assert result.regression is True
    assert result.score == pytest.approx(0.95)  # score still computed
    assert "BLOCKED" in result.reason


def test_aggregate_ignores_signals_not_in_weights() -> None:
    """Signals for unknown names are ignored."""
    agg = WeightedFitnessAggregator(weights={"a": 1.0})
    result = agg.aggregate({
        "a": _sig(quality=0.5),
        "unknown": _sig(quality=1.0, regression=True),  # ignored
    })
    assert result.score == pytest.approx(0.5)
    assert result.regression is False  # unknown signal ignored


def test_aggregate_rejects_non_fitness_signal_value() -> None:
    agg = WeightedFitnessAggregator(weights={"a": 1.0})
    with pytest.raises(TypeError, match="FitnessSignal"):
        agg.aggregate({"a": "not a signal"})  # type: ignore[dict-item]


def test_aggregate_clamps_score_to_unit_interval() -> None:
    """Floating point edge case: score clamped to [0, 1]."""
    agg = WeightedFitnessAggregator(weights={"a": 1.0})
    result = agg.aggregate({"a": _sig(quality=1.0)})
    assert 0.0 <= result.score <= 1.0


def test_weights_property_returns_copy() -> None:
    agg = WeightedFitnessAggregator(weights={"a": 0.5, "b": 0.5})
    w = agg.weights
    w["c"] = 999.0
    assert "c" not in agg.weights  # mutation didn't affect internal state


# ── R002 ────────────────────────────────────────────────────────────────


def test_module_infra_free() -> None:
    mod = importlib.import_module("active_skill_system.application.weighted_fitness_aggregator")
    src = Path(mod.__file__).read_text(encoding="utf-8")
    for forbidden in ("import activegraph", "from activegraph", "import anthropic", "import openai"):
        assert forbidden not in src, f"weighted_fitness_aggregator.py must not contain '{forbidden}' (R002)"
