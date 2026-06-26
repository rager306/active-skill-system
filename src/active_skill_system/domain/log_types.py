"""L1 Domain — Log analysis optimization types (M030 S01).

Domain profile for log analysis optimization (filtering, aggregation,
sampling, rotation). Primary fitness axis: error_rate (lower = better).

Pure domain. NO I/O, NO infrastructure imports (R002). stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class LogNodeKind(StrEnum):
    LOG_ENTRY = "log_entry"
    ERROR = "error"
    WARNING = "warning"
    METRIC = "metric"
    LOG_TRANSFORM_FILTER = "log_transform_filter"
    LOG_TRANSFORM_AGGREGATE = "log_transform_aggregate"
    LOG_TRANSFORM_SAMPLE = "log_transform_sample"
    LOG_TRANSFORM_ROTATE = "log_transform_rotate"


class LogGapClass(StrEnum):
    HIGH_ERROR_RATE = "high_error_rate"
    LOG_BLOAT = "log_bloat"
    SLOW_PARSE = "slow_parse"
    MISSING_CONTEXT = "missing_context"
    RETENTION_VIOLATION = "retention_violation"


class LogActionType(StrEnum):
    FILTER = "filter"
    AGGREGATE = "aggregate"
    SAMPLE = "sample"
    ROTATE = "rotate"


@dataclass(frozen=True)
class LogTransformParams:
    transform_type: LogNodeKind
    params: dict[str, Any]
    legal: bool = True

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.transform_type, LogNodeKind):
            errors.append(f"transform_type must be a LogNodeKind (got {type(self.transform_type).__name__})")
        transform_kinds = {
            LogNodeKind.LOG_TRANSFORM_FILTER,
            LogNodeKind.LOG_TRANSFORM_AGGREGATE,
            LogNodeKind.LOG_TRANSFORM_SAMPLE,
            LogNodeKind.LOG_TRANSFORM_ROTATE,
        }
        if self.transform_type not in transform_kinds:
            errors.append(f"transform_type must be a LOG_TRANSFORM_* kind (got {self.transform_type!r})")
        if not isinstance(self.params, dict):
            errors.append(f"params must be a dict (got {type(self.params).__name__})")
        if not isinstance(self.legal, bool):
            errors.append(f"legal must be a bool (got {type(self.legal).__name__})")
        if errors:
            raise ValueError("LogTransformParams invariant violation: " + "; ".join(errors))


@dataclass(frozen=True)
class LogMetrics:
    """Measured log analysis metrics.

    Carries:
      - error_rate: fraction of error-level entries (float in [0, 1]; lower = better).
      - log_volume_mb: total log volume in MB (float, >= 0.0; lower = better).
      - parse_time_ms: time to parse all logs (float, >= 0.0; reported but not in ranking).
      - is_valid: False if the log pipeline is invalid.
    """

    error_rate: float
    log_volume_mb: float
    parse_time_ms: float
    is_valid: bool = True

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.error_rate, (int, float)) or isinstance(self.error_rate, bool) or not (0.0 <= float(self.error_rate) <= 1.0):
            errors.append(f"error_rate must be in [0.0, 1.0] (got {self.error_rate!r})")
        if not isinstance(self.log_volume_mb, (int, float)) or isinstance(self.log_volume_mb, bool) or float(self.log_volume_mb) < 0.0:
            errors.append(f"log_volume_mb must be a non-negative number (got {self.log_volume_mb!r})")
        if not isinstance(self.parse_time_ms, (int, float)) or isinstance(self.parse_time_ms, bool) or float(self.parse_time_ms) < 0.0:
            errors.append(f"parse_time_ms must be a non-negative number (got {self.parse_time_ms!r})")
        if not isinstance(self.is_valid, bool):
            errors.append(f"is_valid must be a bool (got {type(self.is_valid).__name__})")
        if errors:
            raise ValueError("LogMetrics invariant violation: " + "; ".join(errors))

    def better_than(self, other: LogMetrics) -> bool:
        """True if strictly better. error_rate primary, log_volume_mb tie. parse_time reported."""
        if not isinstance(other, LogMetrics):
            return False
        if not self.is_valid and other.is_valid:
            return False
        if self.is_valid and not other.is_valid:
            return True
        if float(self.error_rate) < float(other.error_rate):
            return True
        return (
            float(self.error_rate) == float(other.error_rate)
            and float(self.log_volume_mb) < float(other.log_volume_mb)
        )
