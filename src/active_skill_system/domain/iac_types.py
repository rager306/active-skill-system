"""L1 Domain — Infrastructure-as-Code plan optimization types (M023 S01).

Domain profile for Infrastructure-as-Code (Terraform-like) plan optimization.
Mirrors ``compiler_types.py`` (M016 S01) and ``sql_types.py`` (M018 S01)
on a different problem class: declarative IaC plans instead of imperative
loop transforms or SQL queries. The shared shape is what lets the
Evolvable trait (D004) generalize across all three domain profiles.

Pure domain. NO I/O, NO infrastructure imports (R002). stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class IaCNodeKind(StrEnum):
    """Node types for IaC plan optimization."""

    RESOURCE = "resource"
    MODULE = "module"
    VARIABLE = "variable"
    OUTPUT = "output"
    PROVIDER = "provider"
    # ── IaC plan transforms ────────────────────────────────────────────
    IA_TRANSFORM_REMOVE_UNUSED = "ia_transform_remove_unused"
    IA_TRANSFORM_ADD_OUTPUT = "ia_transform_add_output"
    IA_TRANSFORM_RESTRUCTURE_DEP = "ia_transform_restructure_dep"
    IA_TRANSFORM_REPLAN_PROVIDERS = "ia_transform_replan_providers"


class IaCGapClass(StrEnum):
    """Classification of IaC plan optimization gaps."""

    UNUSED_VARIABLE = "unused_variable"  # declared variable never referenced
    MISSING_OUTPUT = "missing_output"  # resource with no output reference
    CIRCULAR_DEPENDENCY = "circular_dependency"  # module ref cycle
    DRIFT_DETECTED = "drift_detected"  # actual state diverges from plan
    COST_REGRESSION = "cost_regression"  # plan_cost regressed


class IaCActionType(StrEnum):
    """Type of repair action for an IaC plan gap."""

    REMOVE_UNUSED = "remove_unused"
    ADD_OUTPUT = "add_output"
    RESTRUCTURE_DEP = "restructure_dep"
    REPLAN_PROVIDERS = "replan_providers"


@dataclass(frozen=True)
class IaCTransformParams:
    """Parameters for a specific IaC plan transform.

    Carries:
      - transform_type: one of IaCNodeKind (IA_TRANSFORM_* kind).
      - params: transform parameters (e.g. {"variable_name": "old_var"}).
      - legal: whether the transform is legal given current schema.
    """

    transform_type: IaCNodeKind
    params: dict[str, Any]
    legal: bool = True

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.transform_type, IaCNodeKind):
            errors.append(
                f"transform_type must be a IaCNodeKind (got {type(self.transform_type).__name__})"
            )
        transform_kinds = {
            IaCNodeKind.IA_TRANSFORM_REMOVE_UNUSED,
            IaCNodeKind.IA_TRANSFORM_ADD_OUTPUT,
            IaCNodeKind.IA_TRANSFORM_RESTRUCTURE_DEP,
            IaCNodeKind.IA_TRANSFORM_REPLAN_PROVIDERS,
        }
        if self.transform_type not in transform_kinds:
            errors.append(
                f"transform_type must be a IA_TRANSFORM_* kind (got {self.transform_type!r})"
            )
        if not isinstance(self.params, dict):
            errors.append(f"params must be a dict (got {type(self.params).__name__})")
        if not isinstance(self.legal, bool):
            errors.append(f"legal must be a bool (got {type(self.legal).__name__})")
        if errors:
            raise ValueError("IaCTransformParams invariant violation: " + "; ".join(errors))


# ── IaC metrics (M023 S01) ───────────────────────────────────────────────


@dataclass(frozen=True)
class IaCPlanMetrics:
    """Measured IaC plan metrics after applying (or not) a transformation.

    Carries:
      - resource_count: total resources in the plan (int, >= 0; lower = better).
      - module_count: total modules referenced (int, >= 0; lower = better).
      - variable_count: total variables declared (int, >= 0; lower = better).
      - drift_score: divergence from actual state (float, >= 0.0; lower = better).
      - is_valid: False if the plan is invalid (e.g. illegal transform).
    """

    resource_count: int
    module_count: int
    variable_count: int
    drift_score: float
    is_valid: bool = True

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.resource_count, int) or isinstance(self.resource_count, bool) or self.resource_count < 0:
            errors.append(f"resource_count must be a non-negative int (got {self.resource_count!r})")
        if not isinstance(self.module_count, int) or isinstance(self.module_count, bool) or self.module_count < 0:
            errors.append(f"module_count must be a non-negative int (got {self.module_count!r})")
        if not isinstance(self.variable_count, int) or isinstance(self.variable_count, bool) or self.variable_count < 0:
            errors.append(f"variable_count must be a non-negative int (got {self.variable_count!r})")
        if not isinstance(self.drift_score, (int, float)) or isinstance(self.drift_score, bool) or float(self.drift_score) < 0.0:
            errors.append(f"drift_score must be a non-negative number (got {self.drift_score!r})")
        if not isinstance(self.is_valid, bool):
            errors.append(f"is_valid must be a bool (got {type(self.is_valid).__name__})")
        if errors:
            raise ValueError("IaCPlanMetrics invariant violation: " + "; ".join(errors))

    def better_than(self, other: IaCPlanMetrics) -> bool:
        """True if this metrics is strictly better than other.

        An invalid plan is never better than a valid one. Among valid plans,
        better means strictly lower resource_count, OR same resource_count
        with strictly lower variable_count, OR same resource_count+variable_count
        with strictly lower drift_score. module_count is reported but not
        in the ranking (side diagnostic).
        """
        if not isinstance(other, IaCPlanMetrics):
            return False
        if not self.is_valid and other.is_valid:
            return False
        if self.is_valid and not other.is_valid:
            return True
        if self.resource_count < other.resource_count:
            return True
        if self.resource_count == other.resource_count:
            if self.variable_count < other.variable_count:
                return True
            if self.variable_count == other.variable_count and float(self.drift_score) < float(other.drift_score):
                return True
        return False
