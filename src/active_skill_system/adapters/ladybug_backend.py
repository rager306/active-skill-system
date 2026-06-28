"""L3 Adapter — LadybugBackend (M051 S01, Wave A).

Implements the generic ``GraphBackend`` port over LadybugDB (Kùzu-lineage
embedded graph DB). Speaks GENERIC ``Vertex``/``Edge`` types; translates to
LadybugDB Cypher internally. This is the dialect layer — the application
never sees Cypher.

Refactored from ``adapters/ladybug_graph_store.py`` (M041). The old module
remains as a thin wrapper for backward compatibility (it implements the
legacy ``GraphStore`` Protocol by delegating to this backend).

Design:
  - ``ladybug`` is imported ONLY here (L3). Domain/application never import
    a database (R002) — an AST guard enforces this.
  - Env-based defaults (M049): ``SANDBOX_GRAPH_PATH``, ``LADYBUG_AUTO_CHECKPOINT``.
  - Idempotent upsert via ``MERGE`` on vertex id and (kind, src, dst).
  - Generic schema: ``RglaVertex(id, type, data_b64)`` and
    ``RglaEdge(ekind, data_b64)`` — no Loop-specific columns.

Failure discipline: Cypher errors caught and re-raised as ``ToolError``
with context.
"""

from __future__ import annotations

import json
import os

from active_skill_system.application.ports.graph_backend import GraphBackend
from active_skill_system.domain.errors import ToolError
from active_skill_system.domain.graph_primitives import Edge, Vertex

_NODE_TABLE = "RglaVertex"
_REL_TABLE = "RglaEdge"


def _encode(data):
    """Serialise a dict to base64-encoded JSON (Cypher-map-proof)."""
    raw = json.dumps(data, default=str).encode("utf-8")
    import base64 as _b64
    return _b64.b64encode(raw).decode("ascii")


def _decode(b64):
    """Inverse of _encode. Returns {} on any decode failure."""
    if not b64:
        return {}
    try:
        import base64 as _b64
        raw = _b64.b64decode(b64.encode("ascii")).decode("utf-8")
        out = json.loads(raw)
        return out if isinstance(out, dict) else {}
    except (ValueError, json.JSONDecodeError):
        return {}



class LadybugBackend:
    """GraphBackend backed by an embedded LadybugDB (Kùzu) graph.

    Stores generic Vertex/Edge. Translates to/from LadybugDB Cypher.
    """

    def __init__(
        self,
        path: str | None = None,
        *,
        auto_checkpoint: bool | None = None,
        checkpoint_threshold: int | None = None,
    ) -> None:
        if path is None:
            path = os.environ.get("SANDBOX_GRAPH_PATH", ":memory:")
        if auto_checkpoint is None:
            auto_checkpoint = os.environ.get("LADYBUG_AUTO_CHECKPOINT", "true").lower() == "true"
        if checkpoint_threshold is None:
            try:
                checkpoint_threshold = int(os.environ.get("LADYBUG_CHECKPOINT_THRESHOLD", "100000"))
            except ValueError:
                checkpoint_threshold = 100000
        if not isinstance(path, str) or not path.strip():
            raise ValueError(f"path must be a non-empty string (got {path!r})")
        self._path = path
        self._auto_checkpoint = auto_checkpoint
        self._checkpoint_threshold = checkpoint_threshold
        self._db = None
        self._conn = None
        self._initialised = False

    # ── lazy connection ───────────────────────────────────────────────

    def _connection(self):  # type: ignore[no-untyped-def]
        if self._conn is None:
            import ladybug

            self._db = ladybug.Database(
                self._path,
                auto_checkpoint=self._auto_checkpoint,
                checkpoint_threshold=self._checkpoint_threshold,
            )
            self._conn = ladybug.Connection(self._db)
        return self._conn

    def _ensure_schema(self) -> None:
        if self._initialised:
            return
        conn = self._connection()
        try:
            conn.execute(
                f"CREATE NODE TABLE IF NOT EXISTS {_NODE_TABLE}"
                "(id STRING PRIMARY KEY, type STRING, data_b64 STRING)"
            )
            conn.execute(
                f"CREATE REL TABLE IF NOT EXISTS {_REL_TABLE}"
                f"(FROM {_NODE_TABLE} TO {_NODE_TABLE}, ekind STRING, data_b64 STRING)"
            )
        except Exception as e:  # noqa: BLE001
            raise ToolError(f"ladybug schema init failed: {e}", phase="graph_backend") from None
        self._initialised = True

    def close(self) -> None:
        import contextlib

        if self._db is not None:
            with contextlib.suppress(Exception):
                self._db.__del__()  # type: ignore[no-untyped-call]
            self._db = None
            self._conn = None
            self._initialised = False

    # ── GraphBackend implementation ───────────────────────────────────

    def upsert_vertex(self, v: Vertex) -> None:
        self._ensure_schema()
        try:
            self._connection().execute(
                f"MERGE (v:{_NODE_TABLE} {{id: $id}})"
                " SET v.type = $type, v.data_b64 = $data_b64",
                {
                    "id": v.id,
                    "type": v.type,
                    "data_b64": _encode(v.data),
                },
            )
        except Exception as e:  # noqa: BLE001
            raise ToolError(f"upsert_vertex failed: {e}", phase="graph_backend") from None

    def upsert_edge(self, e: Edge) -> None:
        self._ensure_schema()
        try:
            self._connection().execute(
                f"MERGE (a:{_NODE_TABLE} {{id: $src}})"
                f" MERGE (b:{_NODE_TABLE} {{id: $dst}})"
                f" MERGE (a)-[r:{_REL_TABLE} {{ekind: $ekind}}]->(b)"
                " SET r.data_b64 = $data_b64",
                {
                    "src": e.src,
                    "dst": e.dst,
                    "ekind": e.kind,
                    "data_b64": _encode(e.data),
                },
            )
        except Exception as e:  # noqa: BLE001
            raise ToolError(f"upsert_edge failed: {e}", phase="graph_backend") from None

    def get_vertex(self, vid: str) -> Vertex | None:
        self._ensure_schema()
        try:
            res = self._connection().execute(
                f"MATCH (v:{_NODE_TABLE} {{id: $id}}) RETURN v.type, v.data_b64",
                {"id": vid},
            )
            if not res.has_next():
                return None
            row = res.get_next()
            vtype, data_b64 = row[0], row[1]
            try:
                data = _decode(data_b64)
            except (json.JSONDecodeError, TypeError):
                data = {}
            return Vertex(id=vid, type=vtype, data=data)
        except Exception as e:  # noqa: BLE001
            raise ToolError(f"get_vertex failed: {e}", phase="graph_backend") from None

    def neighbours(self, vid: str, *, direction: str = "out") -> tuple[Vertex, ...]:
        self._ensure_schema()
        out: list[Vertex] = []
        try:
            if direction == "out":
                pattern = f"MATCH (a:{_NODE_TABLE} {{id: $id}})-[r]->(b:{_NODE_TABLE}) RETURN b.id, b.type, b.data_b64"
            elif direction == "in":
                pattern = f"MATCH (a:{_NODE_TABLE})-[r]->(b:{_NODE_TABLE} {{id: $id}}) RETURN a.id, a.type, a.data_b64"
            else:
                pattern = (
                    f"MATCH (a:{_NODE_TABLE} {{id: $id}})-[r]->(b:{_NODE_TABLE}) "
                    f"RETURN b.id, b.type, b.data_b64"
                )
            res = self._connection().execute(pattern, {"id": vid})
            while res.has_next():
                row = res.get_next()
                nid, ntype, data_b64 = row[0], row[1], row[2]
                try:
                    data = _decode(data_b64)
                except (json.JSONDecodeError, TypeError):
                    data = {}
                out.append(Vertex(id=nid, type=ntype, data=data))
        except Exception as e:  # noqa: BLE001
            raise ToolError(f"neighbours failed: {e}", phase="graph_backend") from None
        return tuple(out)

    def has_edge(self, kind: str, src: str, dst: str) -> bool:
        self._ensure_schema()
        try:
            res = self._connection().execute(
                f"MATCH (a:{_NODE_TABLE} {{id: $src}})-[r:{_REL_TABLE} {{ekind: $ekind}}]->"
                f"(b:{_NODE_TABLE} {{id: $dst}}) RETURN count(r)",
                {"src": src, "dst": dst, "ekind": kind},
            )
            return bool(res.has_next() and int(res.get_next()[0]) > 0)
        except Exception as e:  # noqa: BLE001
            raise ToolError(f"has_edge failed: {e}", phase="graph_backend") from None

    def count_vertices(self) -> int:
        self._ensure_schema()
        try:
            res = self._connection().execute(f"MATCH (v:{_NODE_TABLE}) RETURN count(v)")
            return int(res.get_next()[0]) if res.has_next() else 0
        except Exception as e:  # noqa: BLE001
            raise ToolError(f"count_vertices failed: {e}", phase="graph_backend") from None

    def count_edges(self) -> int:
        self._ensure_schema()
        try:
            res = self._connection().execute(f"MATCH ()-[r:{_REL_TABLE}]->() RETURN count(r)")
            return int(res.get_next()[0]) if res.has_next() else 0
        except Exception as e:  # noqa: BLE001
            raise ToolError(f"count_edges failed: {e}", phase="graph_backend") from None

    def all_vertex_ids(self) -> tuple[str, ...]:
        self._ensure_schema()
        try:
            res = self._connection().execute(f"MATCH (v:{_NODE_TABLE}) RETURN v.id")
            ids: list[str] = []
            while res.has_next():
                ids.append(str(res.get_next()[0]))
            return tuple(ids)
        except Exception as e:  # noqa: BLE001
            raise ToolError(f"all_vertex_ids failed: {e}", phase="graph_backend") from None

    def count_edges_of_kind(self, kind: str) -> int:
        self._ensure_schema()
        try:
            res = self._connection().execute(
                f"MATCH ()-[r:{_REL_TABLE}]->() WHERE r.ekind = $k RETURN count(r)",
                {"k": kind},
            )
            return int(res.get_next()[0]) if res.has_next() else 0
        except Exception as e:  # noqa: BLE001
            raise ToolError(f"count_edges_of_kind failed: {e}", phase="graph_backend") from None


# LadybugBackend structurally satisfies the GraphBackend Protocol.
_: GraphBackend = LadybugBackend()  # type: ignore[assignment]
