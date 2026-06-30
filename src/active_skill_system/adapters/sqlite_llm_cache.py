"""L3 Adapter — SQLiteLLMCache (M052 S05).

LLM response cache backed by stdlib sqlite3. Persists to disk so cache
survives across process invocations — critical for fork-and-diff where
the fork re-runs in a new process.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from active_skill_system.application.ports.llm_cache import LLMCache
from active_skill_system.domain.errors import ToolError


class SQLiteLLMCache:
    """LLMCache over stdlib sqlite3. Persists to disk."""

    def __init__(self, path: str = ":memory:") -> None:
        self._path = path
        try:
            self._conn = sqlite3.connect(path)
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS llm_cache (
                    key        TEXT PRIMARY KEY,
                    response   TEXT NOT NULL,
                    created_ns INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            self._conn.commit()
        except sqlite3.Error as e:
            raise ToolError(f"sqlite llm cache init failed: {e}", phase="llm_cache") from None

    def get(self, key: str) -> Any | None:
        try:
            cur = self._conn.execute("SELECT response FROM llm_cache WHERE key = ?", (key,))
            row = cur.fetchone()
            if row is None:
                return None
            return json.loads(row[0])
        except (sqlite3.Error, json.JSONDecodeError):
            return None

    def has(self, key: str) -> bool:
        try:
            cur = self._conn.execute("SELECT COUNT(*) FROM llm_cache WHERE key = ?", (key,))
            return int(cur.fetchone()[0]) > 0
        except sqlite3.Error:
            return False

    def record(self, key: str, response: Any) -> None:
        try:
            import time

            self._conn.execute(
                "INSERT OR REPLACE INTO llm_cache (key, response, created_ns) VALUES (?, ?, ?)",
                (key, json.dumps(response, default=str), int(time.time() * 1_000_000_000)),
            )
            self._conn.commit()
        except sqlite3.Error as e:
            raise ToolError(f"llm cache record failed: {e}", phase="llm_cache") from None

    def count(self) -> int:
        try:
            cur = self._conn.execute("SELECT COUNT(*) FROM llm_cache")
            return int(cur.fetchone()[0])
        except sqlite3.Error:
            return 0

    def close(self) -> None:
        import contextlib

        with contextlib.suppress(sqlite3.Error):
            self._conn.close()


# SQLiteLLMCache structurally satisfies LLMCache.
_: LLMCache = SQLiteLLMCache()  # type: ignore[assignment]
