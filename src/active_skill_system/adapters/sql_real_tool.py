"""L3 Adapter — SQLRealTool (M037 S01).

Real-instrument SQL tool backed by an in-memory ``sqlite3`` database.
Materialises a schema, optionally applies a transform (CREATE INDEX), runs a
real ``EXPLAIN QUERY PLAN``, and parses native plan estimates into
``SQLMetrics`` — giving the SQL evolution loop source-of-truth fitness
instead of synthetic formulae.

Same ``invoke`` contract as ``SQLToolStub`` (M018 S02) so the composition
layer can swap them behind a ``--real`` flag. ``baseline`` is augmented with
optional ``query`` (SQL) and ``setup`` (DDL + seed inserts). When absent, a
deterministic pedagogical schema is used. Failure modes return
``ToolResult(success=False)`` (no exceptions, per D007). ≤200 LOC (R006).
"""

from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

from active_skill_system.application.ports.tool import (
    ToolCapability,
    ToolProfile,
    ToolResult,
)
from active_skill_system.domain.sql_types import SQLMetrics, SQLNodeKind

# Newer SQLite emits "(~N rows)"; older builds stash an estimate in col #3.
_ROWS_RE = re.compile(r"~(\d+)\s*rows", re.IGNORECASE)
_DEFAULT_COLS = ["user_id", "status", "amount"]
_DEFAULT_QUERY = "SELECT amount FROM orders WHERE user_id = 7"
_DEFAULT_SETUP = [
    "CREATE TABLE orders (id INTEGER PRIMARY KEY, user_id INTEGER, amount REAL, status TEXT)",
    "INSERT INTO orders (user_id, amount, status) "
    "WITH RECURSIVE seq(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM seq WHERE x < 1000) "
    "SELECT (x % 50) + 1, x * 1.5, CASE WHEN x % 3 = 0 THEN 'paid' ELSE 'open' END FROM seq",
]


def _metrics_from_dict(d: dict[str, Any]) -> SQLMetrics:
    try:
        return SQLMetrics(
            rows_examined=int(d["rows_examined"]),
            rows_returned=int(d["rows_returned"]),
            time_ms=float(d["time_ms"]),
            plan_cost=float(d["plan_cost"]),
            is_valid=bool(d.get("is_valid", True)),
        )
    except (KeyError, TypeError, ValueError) as e:
        raise ValueError(f"baseline has invalid values: {e}") from None


def _metrics_to_dict(m: SQLMetrics) -> dict[str, Any]:
    return {
        "rows_examined": m.rows_examined,
        "rows_returned": m.rows_returned,
        "time_ms": m.time_ms,
        "plan_cost": m.plan_cost,
        "is_valid": m.is_valid,
    }


def _explain_rows_examined(conn: sqlite3.Connection, query: str) -> int:
    """Sum plan-level row estimates from EXPLAIN QUERY PLAN.

    Prefers the explicit ``~N rows`` token; falls back to the estimate in the
    third column (documented as "notused" but carrying the cost in practice,
    incl. SQLite 3.50). A bare ``SCAN`` with no estimate charges the table
    size. Result clamped to >= 1.
    """
    cur = conn.execute(f"EXPLAIN QUERY PLAN {query}")
    total = 0
    any_node = False
    for row in cur.fetchall():
        detail = str(row[3]) if len(row) >= 4 else ""
        col3 = row[2] if len(row) >= 3 else 0
        any_node = True
        m = _ROWS_RE.search(detail)
        if m:
            total += int(m.group(1))
        elif isinstance(col3, int) and col3 > 0:
            total += col3
        elif "SCAN" in detail.upper():
            total += conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    if not any_node or total <= 0:
        total = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    return max(1, total)


def _build_db(setup: list[str], index_cols: list[str] | None) -> sqlite3.Connection:
    """Create an in-memory DB, run setup, optionally CREATE INDEX."""
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    for stmt in setup:
        cur.execute(stmt)
    if index_cols:
        cur.execute(
            f"CREATE INDEX IF NOT EXISTS idx_real_transform ON orders ({', '.join(index_cols)})"
        )
    conn.commit()
    return conn


class SQLRealTool:
    """Real SQL tool backed by an in-memory SQLite database.

    capabilities: {compute}  profile: NORMAL
    invoke({"transform_type": ..., "params": {...}, "baseline": {...},
           "query": "...", "setup": ["...", ...]}) → ToolResult(json, success)
    """

    name = "sql_apply_transform_real"
    capabilities = frozenset({ToolCapability.COMPUTE})
    profile = ToolProfile.NORMAL

    def invoke(self, args: dict[str, Any]) -> ToolResult:
        if not isinstance(args, dict):
            return ToolResult(text="", evidence_id=None, success=False)

        kind_raw = args.get("transform_type")
        params_raw = args.get("params", {})
        baseline_raw = args.get("baseline")
        query = str(args.get("query") or _DEFAULT_QUERY)
        setup = list(args.get("setup") or _DEFAULT_SETUP)

        # MISSING_INDEX gap case: no transform → return baseline unchanged.
        if kind_raw is None:
            try:
                baseline = _metrics_from_dict(baseline_raw if isinstance(baseline_raw, dict) else {})
            except ValueError:
                return ToolResult(text="", evidence_id=None, success=False)
            return ToolResult(
                text=json.dumps(_metrics_to_dict(baseline), sort_keys=True),
                evidence_id="missing_transform",
                success=True,
            )

        try:
            kind = SQLNodeKind(kind_raw) if not isinstance(kind_raw, SQLNodeKind) else kind_raw
        except ValueError:
            return ToolResult(text="", evidence_id=str(kind_raw), success=False)

        try:
            baseline = _metrics_from_dict(baseline_raw if isinstance(baseline_raw, dict) else {})
        except ValueError:
            return ToolResult(text="", evidence_id=str(kind_raw), success=False)

        if not isinstance(params_raw, dict) or params_raw.get("legal", True) is False:
            return ToolResult(text="", evidence_id=str(kind_raw), success=False)

        # Materialise ADD_INDEX as a real index; other transforms re-plan only.
        index_cols: list[str] | None = None
        if kind is SQLNodeKind.SQL_TRANSFORM_ADD_INDEX:
            cols = params_raw.get("cols", 1)
            if not isinstance(cols, int) or cols < 1:
                return ToolResult(text="", evidence_id=str(kind_raw), success=False)
            index_cols = _DEFAULT_COLS[:cols]

        try:
            conn = _build_db(setup, index_cols)
            rows_examined = _explain_rows_examined(conn, query)
            conn.close()
        except sqlite3.Error:
            return ToolResult(text="", evidence_id=str(kind_raw), success=False)

        # Real instrument drives the primary axis; secondary axes from baseline.
        new_metrics = SQLMetrics(
            rows_examined=rows_examined,
            rows_returned=baseline.rows_returned,
            time_ms=baseline.time_ms,
            plan_cost=float(rows_examined) / 10.0,
            is_valid=True,
        )
        return ToolResult(
            text=json.dumps(_metrics_to_dict(new_metrics), sort_keys=True),
            evidence_id=str(kind_raw),
            success=True,
        )
