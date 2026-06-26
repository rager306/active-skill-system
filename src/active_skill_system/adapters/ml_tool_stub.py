"""L3 Adapter — MLToolStub (M027 S02).

Deterministic stub simulating ML training transforms. Primary axis: loss.

  ADJUST_LR(factor)    : loss *= factor, epochs -= 5 (faster convergence)
  PRUNE_LAYER(n)       : loss += 0.01*n, epochs -= 10 (smaller model, slightly worse loss)
  ADD_REGULARIZATION   : loss *= 0.95, accuracy += 0.05 (capped 1.0)
  SWITCH_OPTIMIZER     : loss *= 0.8, epochs -= 20
"""

from __future__ import annotations

import json
from typing import Any

from active_skill_system.application.ports.tool import (
    ToolCapability,
    ToolProfile,
    ToolResult,
)
from active_skill_system.domain.ml_types import MLMetrics, MLNodeKind


def _metrics_from_dict(d: dict[str, Any]) -> MLMetrics:
    if not isinstance(d, dict):
        raise ValueError(f"baseline must be a dict (got {type(d).__name__})")
    try:
        return MLMetrics(
            loss=float(d["loss"]),
            accuracy=float(d["accuracy"]),
            epochs=int(d["epochs"]),
            convergence_time=float(d["convergence_time"]),
            is_valid=bool(d.get("is_valid", True)),
        )
    except KeyError as e:
        raise ValueError(f"baseline missing required key: {e.args[0]!r}") from None
    except (TypeError, ValueError) as e:
        raise ValueError(f"baseline has invalid values: {e}") from None


def _apply_transform(kind: MLNodeKind, params: dict[str, Any], baseline: MLMetrics) -> MLMetrics:
    loss = float(baseline.loss)
    accuracy = float(baseline.accuracy)
    epochs = baseline.epochs
    convergence_time = float(baseline.convergence_time)

    if kind is MLNodeKind.ML_TRANSFORM_ADJUST_LR:
        factor = float(params.get("lr_factor", 0.5))
        if factor <= 0.0 or factor > 1.0:
            raise ValueError(f"lr_factor must be in (0.0, 1.0] (got {factor!r})")
        loss = max(0.0, loss * factor)
        epochs = max(0, epochs - 5)
    elif kind is MLNodeKind.ML_TRANSFORM_PRUNE_LAYER:
        n = int(params.get("n_layers", 1))
        if n < 1:
            raise ValueError(f"n_layers must be >= 1 (got {n!r})")
        loss = max(0.0, loss + 0.01 * n)
        epochs = max(0, epochs - 10)
    elif kind is MLNodeKind.ML_TRANSFORM_ADD_REGULARIZATION:
        loss = max(0.0, loss * 0.95)
        accuracy = min(1.0, accuracy + 0.05)
    elif kind is MLNodeKind.ML_TRANSFORM_SWITCH_OPTIMIZER:
        loss = max(0.0, loss * 0.8)
        epochs = max(0, epochs - 20)
    else:
        raise ValueError(f"unsupported ML transform kind: {kind!r}")

    return MLMetrics(loss=loss, accuracy=accuracy, epochs=epochs, convergence_time=convergence_time, is_valid=True)


class MLToolStub:
    name = "ml_apply_transform"
    capabilities = frozenset({ToolCapability.COMPUTE})
    profile = ToolProfile.NORMAL

    def invoke(self, args: dict[str, Any]) -> ToolResult:
        if not isinstance(args, dict):
            return ToolResult(text="", evidence_id=None, success=False)
        kind_raw = args.get("transform_type")
        params_raw = args.get("params", {})
        baseline_raw = args.get("baseline")
        if kind_raw is None:
            try:
                baseline = _metrics_from_dict(baseline_raw if isinstance(baseline_raw, dict) else {})
            except ValueError:
                return ToolResult(text="", evidence_id=None, success=False)
            return ToolResult(
                text=json.dumps(_metrics_to_dict(baseline), sort_keys=True),
                evidence_id="missing_transform", success=True,
            )
        try:
            kind = MLNodeKind(kind_raw) if not isinstance(kind_raw, MLNodeKind) else kind_raw
        except ValueError:
            return ToolResult(text="", evidence_id=str(kind_raw), success=False)
        try:
            baseline = _metrics_from_dict(baseline_raw if isinstance(baseline_raw, dict) else {})
        except ValueError:
            return ToolResult(text="", evidence_id=str(kind_raw), success=False)
        if not isinstance(params_raw, dict):
            return ToolResult(text="", evidence_id=str(kind_raw), success=False)
        if params_raw.get("legal", True) is False:
            return ToolResult(text="", evidence_id=str(kind_raw), success=False)
        try:
            new_metrics = _apply_transform(kind, params_raw, baseline)
        except ValueError:
            return ToolResult(text="", evidence_id=str(kind_raw), success=False)
        return ToolResult(
            text=json.dumps(_metrics_to_dict(new_metrics), sort_keys=True),
            evidence_id=str(kind_raw), success=True,
        )


def _metrics_to_dict(m: MLMetrics) -> dict[str, Any]:
    return {"loss": m.loss, "accuracy": m.accuracy, "epochs": m.epochs, "convergence_time": m.convergence_time, "is_valid": m.is_valid}
