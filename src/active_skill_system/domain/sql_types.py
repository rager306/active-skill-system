"""L1 Domain — SQL query plan optimization types (M018 S01).

Domain profile for SQL query plan optimization. Mirrors the shape of
``compiler_types.py`` (M016 S01) but on a different problem class:
declarative SQL plans instead of imperative loop transformations. The
shared shape is what lets the Evolvable trait (D004) generalize across
both profiles.

Pure domain. NO I/O, NO infrastructure imports (R002). stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class SQLNodeKind(StrEnum):
    """Node types for SQL query plan optimization."""

    TABLE_SCAN = "table_scan"
    INDEX_SCAN = "index_scan"
    NESTED_LOOP = "nested_loop"
    HASH_JOIN = "hash_join"
    FILTER = "filter"
    SORT = "sort"
    AGGREGATE = "aggregate"
    # ── SQL plan transforms ────────────────────────────────────────────
    SQL_TRANSFORM_ADD_INDEX = "sql_transform_add_index"
    SQL_TRANSFORM_REORDER_JOINS = "sql_transform_reorder_joins"
    SQL_TRANSFORM_REWRITE_AS_JOIN = "sql_transform_rewrite_as_join"
    SQL_TRANSFORM_REPLAN_QUERY = "sql_transform_replan_query"


class SQLGapClass(StrEnum):
    """Classification of SQL plan optimization gaps.

    Mirrors the compiler ``CompilerGapClass`` taxonomy but scoped to the
    SQL profile. The ``SQLRepairPolicy`` maps each gap class to an
    ``SQLActionType``.
    """

    MISSING_INDEX = "missing_index"  # no candidate index tried yet
    FULL_TABLE_SCAN = "full_table_scan"  # scan where index would be better
    WRONG_JOIN_ORDER = "wrong_join_order"  # join order hurts rows_examined
    INEFFICIENT_AGGREGATE = "inefficient_aggregate"  # aggregate runs before filter
    COST_REGRESSION = "cost_regression"  # overall plan_cost regressed


class SQLActionType(StrEnum):
    """Type of repair action for an SQL plan gap."""

    ADD_INDEX = "add_index"
    REORDER_JOINS = "reorder_joins"
    REWRITE_AS_JOIN = "rewrite_as_join"
    REPLAN_QUERY = "replan_query"


@dataclass(frozen=True)
class SQLTransformParams:
    """Parameters for a specific SQL plan transform.

    Carries:
      - transform_type: one of SQLNodeKind (SQL_TRANSFORM_* kind).
      - params: transform parameters (e.g. {"index_col": "user_id"}).
      - legal: whether the transform is legal given current schema/indexes.
    """

    transform_type: SQLNodeKind
    params: dict[str, Any]
    legal: bool = True

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.transform_type, SQLNodeKind):
            errors.append(
                f"transform_type must be a SQLNodeKind (got {type(self.transform_type).__name__})"
            )
        transform_kinds = {
            SQLNodeKind.SQL_TRANSFORM_ADD_INDEX,
            SQLNodeKind.SQL_TRANSFORM_REORDER_JOINS,
            SQLNodeKind.SQL_TRANSFORM_REWRITE_AS_JOIN,
            SQLNodeKind.SQL_TRANSFORM_REPLAN_QUERY,
        }
        if self.transform_type not in transform_kinds:
            errors.append(
                f"transform_type must be a SQL_TRANSFORM_* kind (got {self.transform_type!r})"
            )
        if not isinstance(self.params, dict):
            errors.append(f"params must be a dict (got {type(self.params).__name__})")
        if not isinstance(self.legal, bool):
            errors.append(f"legal must be a bool (got {type(self.legal).__name__})")
        if errors:
            raise ValueError("SQLTransformParams invariant violation: " + "; ".join(errors))


# ── sql metrics (M018 S01) ───────────────────────────────────────────────


@dataclass(frozen=True)
class SQLMetrics:
    """Measured SQL plan metrics after applying (or not) a transformation.

    Carries:
      - rows_examined: total rows touched (int, >= 0; lower = better).
      - rows_returned: total rows returned to caller (int, >= 0; lower = better
        after the WHERE clause, since fewer excess rows = better).
      - time_ms: wall-clock query time in milliseconds (float, >= 0.0; lower = better).
      - plan_cost: optimizer-estimated cost (float, >= 0.0; lower = better).
      - is_valid: False if the plan is invalid (e.g. illegal transform produced
        an unschedulable plan).
    """

    rows_examined: int
    rows_returned: int
    time_ms: float
    plan_cost: float
    is_valid: bool = True

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not isinstance(self.rows_examined, int) or isinstance(self.rows_examined, bool) or self.rows_examined < 0:
            errors.append(f"rows_examined must be a non-negative int (got {self.rows_examined!r})")
        if not isinstance(self.rows_returned, int) or isinstance(self.rows_returned, bool) or self.rows_returned < 0:
            errors.append(f"rows_returned must be a non-negative int (got {self.rows_returned!r})")
        if not isinstance(self.time_ms, (int, float)) or isinstance(self.time_ms, bool) or float(self.time_ms) < 0.0:
            errors.append(f"time_ms must be a non-negative number (got {self.time_ms!r})")
        if not isinstance(self.plan_cost, (int, float)) or isinstance(self.plan_cost, bool) or float(self.plan_cost) < 0.0:
            errors.append(f"plan_cost must be a non-negative number (got {self.plan_cost!r})")
        if not isinstance(self.is_valid, bool):
            errors.append(f"is_valid must be a bool (got {type(self.is_valid).__name__})")
        if errors:
            raise ValueError("SQLMetrics invariant violation: " + "; ".join(errors))

    def better_than(self, other: SQLMetrics) -> bool:
        """True if this metrics is strictly better than other.

        An invalid plan is never better than a valid one. Among valid plans,
        better means strictly lower rows_examined, OR same rows_examined with
        strictly lower rows_returned, OR same rows_examined + rows_returned
        with strictly lower time_ms. plan_cost is reported but not in the
        ranking (kept as a side observation, mirrors reg_pressure in M016).
        """
        if not isinstance(other, SQLMetrics):
            return False
        if not self.is_valid and other.is_valid:
            return False
        if self.is_valid and not other.is_valid:
            return True
        if self.rows_examined < other.rows_examined:
            return True
        if self.rows_examined == other.rows_examined:
            if self.rows_returned < other.rows_returned:
                return True
            if self.rows_returned == other.rows_returned and float(self.time_ms) < float(other.time_ms):
                return True
        return False
