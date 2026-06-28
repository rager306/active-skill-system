"""L3 Adapter — LadybugGraphStore (RGLA, D010).

Realises the ``GraphStore`` port (application/ports/graph_store.py) over an
embedded **LadybugDB** graph database (Kùzu lineage; PyPI ``ladybug``).
Stores the domain ``LoopGraph`` projection (D009 §4.2) as typed Cypher nodes +
relationship rows, queryable via Cypher ``MATCH``.

Design (D010):
  - ``ladybug`` is imported ONLY here (L3). Domain/application never import a
    database (R002) — an AST guard enforces this.
  - ``:memory:`` default keeps the test suite deterministic and serverless;
    disk persistence (``.lbdb``) is opt-in via the constructor path.
  - Idempotent upsert via ``MERGE`` on vertex id and (ekind, src, dst), so
    re-storing a LoopGraph after every Loop transition never duplicates.
  - The port is the swap seam: if LadybugDB stalls (D010 maturity caveat), a
    different ``GraphStore`` adapter replaces this module without touching
    domain/application.

Failure discipline: Cypher errors are caught and re-raised as the project's
``ToolError`` (M040) with context — they never leak to the domain. ≤200 LOC (R006).
"""

from __future__ import annotations

from active_skill_system.application.ports.graph_store import GraphStore
from active_skill_system.domain.errors import ToolError
from active_skill_system.domain.loop_graph import LoopEdge, LoopGraph, LoopVertex

_NODE_TABLE = "RglaVertex"
_REL_TABLE = "RglaEdge"


class LadybugGraphStore:
    """GraphStore backed by an embedded LadybugDB (Kùzu) graph.

    The node/rel tables are created lazily on first ``store_*`` call so a bare
    instance (e.g. for a quick ``query_neighbours`` in a fresh DB) does not error.
    """

    def __init__(
        self,
        path: str | None = None,
        *,
        auto_checkpoint: bool | None = None,
        checkpoint_threshold: int | None = None,
    ) -> None:
        # Resolve defaults from env (M049 cross-session persistence).
        import os
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
                "(id STRING PRIMARY KEY, kind STRING, label STRING)"
            )
            conn.execute(
                f"CREATE REL TABLE IF NOT EXISTS {_REL_TABLE}"
                f"(FROM {_NODE_TABLE} TO {_NODE_TABLE}, ekind STRING)"
            )
        except Exception as e:  # noqa: BLE001
            raise ToolError(f"ladybug schema init failed: {e}", phase="graph_store") from None
        self._initialised = True

    def close(self) -> None:
        import contextlib

        if self._db is not None:
            with contextlib.suppress(Exception):
                self._db.__del__()  # type: ignore[no-untyped-call]  # ty:ignore[unresolved-attribute]
            self._db = None
            self._conn = None
            self._initialised = False

    # ── GraphStore implementation ─────────────────────────────────────

    def store_vertex(self, vertex: LoopVertex) -> None:
        self._ensure_schema()
        try:
            self._connection().execute(
                f"MERGE (v:{_NODE_TABLE} {{id: $id}})"
                " SET v.kind = $kind, v.label = $label",
                {"id": vertex.id, "kind": vertex.kind.value, "label": vertex.label},
            )
        except Exception as e:  # noqa: BLE001
            raise ToolError(f"store_vertex failed: {e}", phase="graph_store") from None

    def store_edge(self, edge: LoopEdge) -> None:
        self._ensure_schema()
        try:
            self._connection().execute(
                f"MERGE (a:{_NODE_TABLE} {{id: $src}})"
                f" MERGE (b:{_NODE_TABLE} {{id: $dst}})"
                f" MERGE (a)-[r:{_REL_TABLE} {{ekind: $ekind}}]->(b)",
                {"src": edge.src, "dst": edge.dst, "ekind": edge.kind.value},
            )
        except Exception as e:  # noqa: BLE001
            raise ToolError(f"store_edge failed: {e}", phase="graph_store") from None

    def store_loop_graph(self, graph: LoopGraph) -> None:
        for v in graph.vertices:
            self.store_vertex(v)
        for e in graph.edges:
            self.store_edge(e)

    def get_vertex(self, vertex_id: str) -> LoopVertex | None:
        from active_skill_system.domain.loop_graph import LoopVertexKind

        self._ensure_schema()
        try:
            res = self._connection().execute(
                f"MATCH (v:{_NODE_TABLE} {{id: $id}}) RETURN v.kind, v.label", {"id": vertex_id}
            )
            # pyrefly: ignore [missing-attribute]
            if not res.has_next():
                return None
            # pyrefly: ignore [missing-attribute]
            row = res.get_next()
        except Exception as e:  # noqa: BLE001
            raise ToolError(f"get_vertex failed: {e}", phase="graph_store") from None
        return LoopVertex(id=vertex_id, kind=LoopVertexKind(row[0]), label=row[1])

    def query_neighbours(self, vertex_id: str, *, direction: str = "out") -> tuple[LoopVertex, ...]:
        from active_skill_system.domain.loop_graph import LoopVertexKind

        self._ensure_schema()
        if direction == "out":
            pattern = f"MATCH (a:{_NODE_TABLE} {{id: $id}})-[r]->(b:{_NODE_TABLE}) RETURN b.id, b.kind, b.label"
        elif direction == "in":
            pattern = f"MATCH (a:{_NODE_TABLE})-[r]->(b:{_NODE_TABLE} {{id: $id}}) RETURN a.id, a.kind, a.label"
        elif direction == "both":
            pattern = (
                f"MATCH (a:{_NODE_TABLE} {{id: $id}})-[r]-(b:{_NODE_TABLE}) "
                "RETURN b.id, b.kind, b.label"
            )
        else:
            raise ValueError(f"direction must be out/in/both (got {direction!r})")
        try:
            res = self._connection().execute(pattern, {"id": vertex_id})
            out: list[LoopVertex] = []
            # pyrefly: ignore [missing-attribute]
            while res.has_next():
                # pyrefly: ignore [missing-attribute]
                vid, kind, label = res.get_next()
                out.append(LoopVertex(id=vid, kind=LoopVertexKind(kind), label=label))
        except Exception as e:  # noqa: BLE001
            raise ToolError(f"query_neighbours failed: {e}", phase="graph_store") from None
        return tuple(out)

    def has_edge(self, kind: object, src: str, dst: str) -> bool:
        ekind = kind.value if hasattr(kind, "value") else str(kind)
        self._ensure_schema()
        try:
            res = self._connection().execute(
                f"MATCH (a:{_NODE_TABLE} {{id: $src}})-[r:{_REL_TABLE} {{ekind: $ekind}}]->"
                f"(b:{_NODE_TABLE} {{id: $dst}}) RETURN count(r)",
                {"src": src, "dst": dst, "ekind": ekind},
            )
            # pyrefly: ignore [missing-attribute]
            return res.get_next()[0] > 0
        except Exception as e:  # noqa: BLE001
            raise ToolError(f"has_edge failed: {e}", phase="graph_store") from None

    def count_vertices(self) -> int:
        self._ensure_schema()
        try:
            res = self._connection().execute(f"MATCH (v:{_NODE_TABLE}) RETURN count(v)")
            # pyrefly: ignore [missing-attribute]
            return int(res.get_next()[0])
        except Exception as e:  # noqa: BLE001
            raise ToolError(f"count_vertices failed: {e}", phase="graph_store") from None

    def count_edges(self) -> int:
        self._ensure_schema()
        try:
            res = self._connection().execute(f"MATCH ()-[r:{_REL_TABLE}]->() RETURN count(r)")
            # pyrefly: ignore [missing-attribute]
            return int(res.get_next()[0])
        except Exception as e:  # noqa: BLE001
            raise ToolError(f"count_edges failed: {e}", phase="graph_store") from None

    def list_vertex_ids(self) -> tuple[str, ...]:
        """Enumerate all stored vertex ids (M049 S01 ReportReader)."""
        self._ensure_schema()
        try:
            res = self._connection().execute(f"MATCH (v:{_NODE_TABLE}) RETURN v.id")
            ids: list[str] = []
            # pyrefly: ignore [missing-attribute]
            while res.has_next():
                # pyrefly: ignore [missing-attribute]
                ids.append(str(res.get_next()[0]))
            return tuple(ids)
        except Exception as e:  # noqa: BLE001
            raise ToolError(f"list_vertex_ids failed: {e}", phase="graph_store") from None

    def count_edges_by_kind(self, kind_value: str) -> int:
        """Count edges whose ekind matches ``kind_value``."""
        self._ensure_schema()
        try:
            res = self._connection().execute(
                f"MATCH ()-[r:{_REL_TABLE}]->() WHERE r.ekind = $k RETURN count(r)",
                {"k": kind_value},
            )
            # pyrefly: ignore [missing-attribute]
            return int(res.get_next()[0]) if res.has_next() else 0
        except Exception as e:  # noqa: BLE001
            raise ToolError(f"count_edges_by_kind failed: {e}", phase="graph_store") from None


# LadybugGraphStore structurally satisfies the GraphStore Protocol.
_: GraphStore = LadybugGraphStore()  # type: ignore[assignment]
