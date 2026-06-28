"""L1 Domain — API rate limiting optimization types (M031 S01).

Domain profile for API rate limiting optimization. Primary fitness axis:
rate_limit_utilization (lower = better — more headroom). Inverse-axis
semantic is the same as lower=better (we want more headroom, not less).

Pure domain. NO I/O, NO infrastructure imports (R002). stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class APINodeKind(StrEnum):
    """APINodeKind class."""
    ENDPOINT = "endpoint"
    RATE_LIMITER = "rate_limiter"
    QUOTA = "quota"
    THROTTLE = "throttle"
    API_TRANSFORM_INCREASE_QUOTA = "api_transform_increase_quota"
    API_TRANSFORM_CACHE = "api_transform_cache"
    API_TRANSFORM_BATCH = "api_transform_batch"
    API_TRANSFORM_DEBOUNCE = "api_transform_debounce"


class APIGapClass(StrEnum):
    """APIGapClass class."""
    HIGH_UTILIZATION = "high_utilization"
    FREQUENT_THROTTLING = "frequent_throttling"
    SLOW_RESPONSE = "slow_response"
    QUOTA_EXHAUSTION = "quota_exhaustion"
    BURST_PATTERN = "burst_pattern"


class APIActionType(StrEnum):
    """APIActionType class."""
    INCREASE_QUOTA = "increase_quota"
    CACHE = "cache"
    BATCH = "batch"
    DEBOUNCE = "debounce"


@dataclass(frozen=True)
class APITransformParams:
    """APITransformParams class."""
    transform_type: APINodeKind
    params: dict[str, Any]
    legal: bool = True

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.transform_type, APINodeKind):
            errors.append(f"transform_type must be a APINodeKind (got {type(self.transform_type).__name__})")
        transform_kinds = {
            APINodeKind.API_TRANSFORM_INCREASE_QUOTA,
            APINodeKind.API_TRANSFORM_CACHE,
            APINodeKind.API_TRANSFORM_BATCH,
            APINodeKind.API_TRANSFORM_DEBOUNCE,
        }
        if self.transform_type not in transform_kinds:
            errors.append(f"transform_type must be a API_TRANSFORM_* kind (got {self.transform_type!r})")
        if not isinstance(self.params, dict):
            errors.append(f"params must be a dict (got {type(self.params).__name__})")
        if not isinstance(self.legal, bool):
            errors.append(f"legal must be a bool (got {type(self.legal).__name__})")
        if errors:
            raise ValueError("APITransformParams invariant violation: " + "; ".join(errors))


@dataclass(frozen=True)
class APIMetrics:
    """Measured API rate limiting metrics.

    Carries:
      - rate_limit_utilization: fraction of quota used (float in [0, 1]; lower = better).
      - throttled_requests_pct: percentage of requests throttled (float in [0, 100]; lower = better).
      - avg_response_ms: average response time in ms (float, >= 0.0; reported but not in ranking).
      - is_valid: False if the rate-limiting plan is invalid.
    """

    rate_limit_utilization: float
    throttled_requests_pct: float
    avg_response_ms: float
    is_valid: bool = True

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.rate_limit_utilization, (int, float)) or isinstance(self.rate_limit_utilization, bool) or not (0.0 <= float(self.rate_limit_utilization) <= 1.0):
            errors.append(f"rate_limit_utilization must be in [0.0, 1.0] (got {self.rate_limit_utilization!r})")
        if not isinstance(self.throttled_requests_pct, (int, float)) or isinstance(self.throttled_requests_pct, bool) or not (0.0 <= float(self.throttled_requests_pct) <= 100.0):
            errors.append(f"throttled_requests_pct must be in [0.0, 100.0] (got {self.throttled_requests_pct!r})")
        if not isinstance(self.avg_response_ms, (int, float)) or isinstance(self.avg_response_ms, bool) or float(self.avg_response_ms) < 0.0:
            errors.append(f"avg_response_ms must be a non-negative number (got {self.avg_response_ms!r})")
        if not isinstance(self.is_valid, bool):
            errors.append(f"is_valid must be a bool (got {type(self.is_valid).__name__})")
        if errors:
            raise ValueError("APIMetrics invariant violation: " + "; ".join(errors))

    def better_than(self, other: APIMetrics) -> bool:
        """True if strictly better. rate_limit_utilization primary (lower better), throttled_requests_pct tie."""
        if not isinstance(other, APIMetrics):
            return False
        if not self.is_valid and other.is_valid:
            return False
        if self.is_valid and not other.is_valid:
            return True
        if float(self.rate_limit_utilization) < float(other.rate_limit_utilization):
            return True
        return (
            float(self.rate_limit_utilization) == float(other.rate_limit_utilization)
            and float(self.throttled_requests_pct) < float(other.throttled_requests_pct)
        )
