"""L3 Adapter — LogToolStub (M030 S02).

Deterministic stub simulating log analysis transforms. Primary axis: error_rate.

  FILTER(level)     : error_rate *= 0.5, log_volume_mb *= 0.7
  AGGREGATE(window) : parse_time_ms //= 2, error_rate unchanged
  SAMPLE(rate)      : log_volume_mb *= rate, error_rate unchanged, parse_time_ms *= rate
  ROTATE(max_size)  : log_volume_mb //= 2, parse_time_ms //= 2
"""

from __future__ import annotations

import json
from typing import Any

from active_skill_system.application.ports.tool import (
    ToolCapability,
    ToolProfile,
    ToolResult,
)
from active_skill_system.domain.log_types import LogMetrics, LogNodeKind


def _metrics_from_dict(d: dict[str, Any]) -> LogMetrics:
    if not isinstance(d, dict):
        raise ValueError(f"baseline must be a dict (got {type(d).__name__})")
    try:
        return LogMetrics(
            error_rate=float(d["error_rate"]),
            log_volume_mb=float(d["log_volume_mb"]),
            parse_time_ms=float(d["parse_time_ms"]),
            is_valid=bool(d.get("is_valid", True)),
        )
    except KeyError as e:
        raise ValueError(f"baseline missing required key: {e.args[0]!r}") from None
    except (TypeError, ValueError) as e:
        raise ValueError(f"baseline has invalid values: {e}") from None


def _apply_transform(kind: LogNodeKind, params: dict[str, Any], baseline: LogMetrics) -> LogMetrics:
    error_rate = float(baseline.error_rate)
    log_volume = float(baseline.log_volume_mb)
    parse_time = float(baseline.parse_time_ms)

    if kind is LogNodeKind.LOG_TRANSFORM_FILTER:
        error_rate = max(0.0, error_rate * 0.5)
        log_volume = max(0.0, log_volume * 0.7)
    elif kind is LogNodeKind.LOG_TRANSFORM_AGGREGATE:
        parse_time = max(0.0, parse_time / 2)
    elif kind is LogNodeKind.LOG_TRANSFORM_SAMPLE:
        rate = float(params.get("rate", 0.1))
        if rate <= 0.0 or rate >= 1.0:
            raise ValueError(f"rate must be in (0.0, 1.0) (got {rate!r})")
        log_volume = max(0.0, log_volume * rate)
        parse_time = max(0.0, parse_time * rate)
    elif kind is LogNodeKind.LOG_TRANSFORM_ROTATE:
        log_volume = max(0.0, log_volume / 2)
        parse_time = max(0.0, parse_time / 2)
    else:
        raise ValueError(f"unsupported log transform kind: {kind!r}")

    return LogMetrics(error_rate=error_rate, log_volume_mb=log_volume, parse_time_ms=parse_time, is_valid=True)


class LogToolStub:
    """LogToolStub class."""
    name = "log_apply_transform"
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
            kind = LogNodeKind(kind_raw) if not isinstance(kind_raw, LogNodeKind) else kind_raw
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


def _metrics_to_dict(m: LogMetrics) -> dict[str, Any]:
    return {"error_rate": m.error_rate, "log_volume_mb": m.log_volume_mb, "parse_time_ms": m.parse_time_ms, "is_valid": m.is_valid}
