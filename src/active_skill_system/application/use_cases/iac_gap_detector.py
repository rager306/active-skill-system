"""L2 Application — IaC gap detector (M023 S03).

Pure function ``classify_iac_gap(previous, current) -> IaCGapClass | NO_GAP_SENTINEL``
mirroring ``compiler_gap_detector.classify_gap`` and ``sql_gap_detector.classify_sql_gap``
on IaC primitives. Primary axis: resource_count. NO_GAP is a string sentinel.
"""

from __future__ import annotations

from active_skill_system.domain.iac_types import IaCGapClass, IaCPlanMetrics

NO_GAP: str = "__no_gap__"


def is_iac_improved(previous: IaCPlanMetrics, current: IaCPlanMetrics) -> bool:
    return current.better_than(previous)


def classify_iac_gap(previous: IaCPlanMetrics | None, current: IaCPlanMetrics) -> IaCGapClass | str:
    if previous is None:
        return IaCGapClass.UNUSED_VARIABLE
    if not current.is_valid:
        return IaCGapClass.UNUSED_VARIABLE

    res_better = current.resource_count < previous.resource_count
    res_worse = current.resource_count > previous.resource_count
    res_equal = current.resource_count == previous.resource_count
    var_better = current.variable_count < previous.variable_count
    var_worse = current.variable_count > previous.variable_count
    var_equal = current.variable_count == previous.variable_count
    drift_better = float(current.drift_score) < float(previous.drift_score)

    # NO_GAP: resource_count strictly better AND (variable_count not worse AND drift not worse).
    if res_better and not var_worse and not drift_better is False:  # drift not worse: !drift_worse i.e. current.drift <= previous.drift
        # Equivalent: not (current.drift > previous.drift)
        if float(current.drift_score) <= float(previous.drift_score):
            return NO_GAP

    if res_worse and var_worse:
        return IaCGapClass.COST_REGRESSION
    if res_better and var_worse:
        return IaCGapClass.MISSING_OUTPUT
    if res_worse and var_better:
        return IaCGapClass.CIRCULAR_DEPENDENCY
    if res_equal and var_equal and float(current.drift_score) > float(previous.drift_score):
        return IaCGapClass.DRIFT_DETECTED
    return IaCGapClass.UNUSED_VARIABLE