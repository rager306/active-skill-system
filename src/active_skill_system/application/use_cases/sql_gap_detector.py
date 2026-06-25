"""L2 Application — SQL gap detector (M018 S03 T01).

Pure function ``classify_sql_gap(previous, current) -> SQLGapClass | NO_GAP_SENTINEL``
that mirrors ``compiler_gap_detector.classify_gap`` (M016 S03 T01) but on
SQL primitives. The primary axis is ``rows_examined`` (mirrors M016's
``cycles`` axis), with ``rows_returned`` as the tie-breaker.

NO_GAP is a string sentinel, not a ``SQLGapClass`` value — keeps the
enum as a taxonomy of bad states only (mirrors the M016 pattern).

Pure application. NO infrastructure imports (R002).
"""

from __future__ import annotations

from active_skill_system.domain.sql_types import SQLGapClass, SQLMetrics

# NO_GAP sentinel string. Loop terminates on this branch.
NO_GAP: str = "__no_gap__"

# Tolerable trade-off: candidate rows_returned may grow up to this multiple
# before we call it INEFFICIENT_AGGREGATE instead of MISSING_INDEX.
_ROWS_RETURNED_REGRESSION_RATIO: float = 2.0


def is_sql_improved(previous: SQLMetrics, current: SQLMetrics) -> bool:
    """True iff current is strictly better than previous (delegates to SQLMetrics.better_than)."""
    return current.better_than(previous)


def classify_sql_gap(previous: SQLMetrics | None, current: SQLMetrics) -> SQLGapClass | str:
    """Classify the SQL plan optimization gap between previous and current metrics.

    Per-axis rules (each rule evaluated in order; first match wins):

      1. previous is None → MISSING_INDEX (no candidate tried yet)
      2. current.is_valid is False → MISSING_INDEX (invalid plan, treat as "no transform applied")
      3. rows_examined strictly better AND rows_returned not worse AND time_ms not worse → NO_GAP
      4. rows_examined worse AND rows_returned worse → COST_REGRESSION
      5. rows_examined better BUT rows_returned much worse (>=2x or 0→non-zero) → INEFFICIENT_AGGREGATE
         else rows_examined better BUT rows_returned tolerable → MISSING_INDEX (no movement)
      6. rows_examined worse AND rows_returned better → WRONG_JOIN_ORDER
      7. else → MISSING_INDEX

    Note: ``current.better_than(previous)`` is NOT delegated to directly because
    ``SQLMetrics.better_than`` uses ``rows_examined`` as primary axis with
    ``rows_returned``/``time_ms`` as tie-breakers. The gap classifier must
    inspect each axis explicitly so a 2x ``rows_returned`` regression is
    flagged as INEFFICIENT_AGGREGATE even when rows_examined improved.
    Mirrors the same logic in ``compiler_gap_detector.classify_gap``.
    """
    if previous is None:
        return SQLGapClass.MISSING_INDEX
    if not current.is_valid:
        return SQLGapClass.MISSING_INDEX

    rows_examined_better = current.rows_examined < previous.rows_examined
    rows_examined_equal = current.rows_examined == previous.rows_examined
    rows_returned_better = current.rows_returned < previous.rows_returned
    rows_returned_equal = current.rows_returned == previous.rows_returned
    time_ms_better = float(current.time_ms) < float(previous.time_ms)
    rows_examined_worse = current.rows_examined > previous.rows_examined
    rows_returned_worse = current.rows_returned > previous.rows_returned

    # NO_GAP requires strictly better rows_examined AND not worse on other axes.
    if rows_examined_better and not rows_returned_worse and float(current.time_ms) <= float(previous.time_ms):
        return NO_GAP

    if rows_examined_worse and rows_returned_worse:
        return SQLGapClass.COST_REGRESSION

    if rows_examined_better and rows_returned_worse:
        # Tolerable trade-off vs INEFFICIENT_AGGREGATE classification.
        if previous.rows_returned == 0 and current.rows_returned > 0:
            return SQLGapClass.INEFFICIENT_AGGREGATE
        if previous.rows_returned > 0 and current.rows_returned >= previous.rows_returned * _ROWS_RETURNED_REGRESSION_RATIO:
            return SQLGapClass.INEFFICIENT_AGGREGATE
        return SQLGapClass.MISSING_INDEX

    if rows_examined_worse and rows_returned_better:
        return SQLGapClass.WRONG_JOIN_ORDER

    if rows_examined_equal and rows_returned_equal and time_ms_better:
        # Tie on primary axes but time improved — strictly better.
        return NO_GAP

    return SQLGapClass.MISSING_INDEX
