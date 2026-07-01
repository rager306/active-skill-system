# Architecture Proposal — Absorb ActiveGraph Core into Hexagonal/Onion (2026-06-28)

> Status: **DELIVERED** ✅. All 3 waves (A/B/C/D) complete as of M054 (2026-06-30).
> This document was the design; the implementation is now production-ready.
> See `doc/ROADMAP.md` for current state and `doc/architecture-status-activegraph-integration.md`
> for the updated integration audit.
>
> Originally this document designed how to absorb the 12 activegraph primitives
> into our hexagonal/onion architecture WITHOUT becoming a thin wrapper around
> activegraph runtime. It also solved the LadybugDB lock-in by introducing a
> layered port hierarchy that makes the backend (LadybugDB / HelixDB / FalkorDB /
> SQLite) swappable.

## 0. Why this document

After Waves 1-4 we have a working system (1417 tests, 4 ports, 3 strategies,
2 benchmarks, 11-axis verifier) but our `GraphStore` port is **a thin wrapper
around LadybugDB** and we are missing 7 of activegraph's 12 primitives (the
reactive/event-sourced/fork-and-diff half). The user asks: how do we absorb
those primitives in our hexagonal architecture, and how do we make the
backend swappable (HelixDB, FalkorDB, etc.)?

This document answers both. The TL;DR is at §6.

---

## 1. Where we are today (honest state)

### 1.1 Hexagonal/onion layout (KEPT across 50 milestones)

```
L1 domain/         pure stdlib types: Loop, LoopGraph, TrajectoryStep, Budget
L2 application/    use cases + ports (Protocol interfaces)
L3 adapters/       infra: ladybug_graph_store, plain_llm_strategy, dspy, ...
L4 composition/    CLI entrypoints wiring L3 into L2
```

Contracts enforced: R002 (domain/application infra-free), R007 (onion layers),
R008/R009 (composition side-effect-free on import).

### 1.2 The GraphStore port is the problem

Today `application/ports/graph_store.py` is a flat Protocol of methods:
`store_vertex`, `store_edge`, `query_neighbours`, `count_edges_by_kind`, ...

The **only** implementation is `LadybugGraphStore`, and that implementation
leaks LadybugDB assumptions:

- `count_edges_by_kind` issues **Cypher** (`MATCH ()-[r:RglaEdge]->() WHERE r.ekind = $k`).
- `list_vertex_ids` issues Cypher (`MATCH (v:RglaVertex) RETURN v.id`).
- The schema (`RglaVertex(id, kind, label)`, `RglaEdge(ekind)`) is **LadybugDB-specific**.

If we wanted HelixDB (Rust/vector graph DB, GraphQL+Cypher hybrid) or
FalkorDB (Redis-based, Cypher-compatible), the Protocol would compile, but
the **semantics assumed by callers** (Cypher dialect, MERGE idempotency,
property names like `ekind`) would silently break.

**This is the heart of the user's concern.** A "port" that assumes one
backend's dialect is not really a port.

### 1.3 The 12 activegraph primitives — coverage today

| # | Primitive | activegraph | Ours | Gap |
|---|-----------|-------------|------|-----|
| 1 | Graph (objects + typed relations) | BehaviorGraph.add_object/add_relation/apply_patch | LoopGraph (specialised) | **partial** — specialised, not general |
| 2 | Events (append-only log) | Event(id,type,payload,actor,...); object.created, behavior.failed, ... | LoopEvent (Loop lifecycle only) + TrajectoryStep | **partial** — no general event types |
| 3 | Behaviors (reactive) | Behavior.run(graph, event); subscriptions | imperative use cases | **absent** |
| 4 | Relations (typed edges with behaviors) | RelationBehavior — logic on edge | typed edges, no logic | **absent** |
| 5 | Patches (proposed mutations) | propose_patch, apply_patch, get_patch | direct upsert | **absent** |
| 6 | Views (scoped reads) | View(objects/relations/events) | query_neighbours + Cypher | **minimal gap** |
| 7 | Frames (bounded contexts) | Frame(goal,budget,behaviors) | Loop(intent,budget,skills) | **minimal gap** |
| 8 | Policies (approval/gating) | Policy, approval.proposed, approve | none | **absent** |
| 9 | Patterns (Cypher subscriptions) | graph-shape subscriptions with NOT EXISTS | Cypher reads only | **absent** |
| 10 | Replay | strict + permissive, LLM cache | permissive (project()) | **partial** |
| 11 | Fork-and-diff | Runtime.fork(at_event, llm_cache) | SandboxRunDiff (final-only) | **absent** ← killer |
| 12 | Failure model | behavior.failed = event | LoopEventKind.FAILED + ratchet | **minimal gap** |

We have 5 of 12 solidly; 2 partial; 5 absent. The absent ones (3,4,5,8,9,11)
are exactly the reactive + fork-diff half — the half that makes activegraph
"a graph runtime", not "a graph database client".

---

## 2. The core design decision

**Do not import `activegraph.Runtime` into our application layer.** That
would make us a thin wrapper and lock our domain to activegraph's event
ontology. Instead, **absorb the *concepts* into our own ports and domain
types**, and let `activegraph` (or any future runtime) be ONE adapter that
implements those ports.

Concretely:

- Our `domain/` gets new pure types: `GraphEvent`, `Behavior`, `Patch`,
  `Frame`, `Policy`, `Pattern`, `Fork`, `Diff`. These mirror activegraph's
  concepts but are **ours** — stdlib-only, frozen dataclasses, no activegraph
  import.
- Our `application/ports/` gets new ports: `EventStore`, `BehaviorRuntime`,
  `PatchApplier`, `ReplayEngine`, `ForkEngine`. These are Protocol interfaces.
- `adapters/activegraph_runtime/` becomes **one adapter** that implements
  those ports by delegating to `activegraph.Runtime`. If activegraph stalls,
  we can write a `adapters/native_runtime/` that implements them on our own
  event log.
- `adapters/ladybug_graph_store.py` becomes **one graph backend adapter**
  among many. The port it implements is `GraphBackend` (see §3), not the
  semantic `GraphStore`.

This keeps our investment (50 milestones, 1417 tests) and adds the missing
primitives as **ports**, not as framework lock-in.

---

## 3. Solving the LadybugDB lock-in: a two-layer port split

The current `GraphStore` Protocol conflates two concerns:

1. **Semantic operations** the application needs: "store this LoopGraph",
   "find neighbours of this loop", "count edges by kind".
2. **Backend dialect** the adapter speaks: Cypher, MERGE, property names.

We split these into two ports:

### 3.1 `GraphBackend` (L2 port) — the swappable seam

```python
# application/ports/graph_backend.py
class GraphBackend(Protocol):
    """Dialect-agnostic graph storage primitive.

    Every method takes/returns OUR domain types (Vertex, Edge). The adapter
    translates to whatever the backend speaks (Cypher, GraphQL, SQL, ...).

    Implementations: LadybugBackend, HelixBackend, FalkorBackend, SQLiteBackend.
    """
    def upsert_vertex(self, v: Vertex) -> None: ...
    def upsert_edge(self, e: Edge) -> None: ...
    def get_vertex(self, vid: str) -> Vertex | None: ...
    def neighbours(self, vid: str, direction: str = "out") -> tuple[Vertex, ...]: ...
    def has_edge(self, kind: str, src: str, dst: str) -> bool: ...
    def count_vertices(self) -> int: ...
    def count_edges(self) -> int: ...
    def all_vertex_ids(self) -> tuple[str, ...]: ...
    def count_edges_of_kind(self, kind: str) -> int: ...
    def query(self, cypher_or_gremlin: str) -> tuple[tuple, ...]: ...  # escape hatch
```

**Key change from today**: vertices/edges here are **generic** (`Vertex(id,
type, data)`, `Edge(kind, src, dst, data)`), not Loop-specific. The
Loop-specific projection (`LoopGraph` → `GraphBackend`) is a use case on top.

### 3.2 `EventStore` (L2 port) — the audit trail

```python
# application/ports/event_store.py
class EventStore(Protocol):
    """Append-only event log. Backend-agnostic.

    Backends: SQLiteEventStore, LadybugEventStore, in-memory, file JSONL.
    """
    def append(self, event: GraphEvent) -> None: ...
    def iter_events(self, run_id: str | None = None) -> Iterator[GraphEvent]: ...
    def events_since(self, event_id: str) -> tuple[GraphEvent, ...]: ...
    def events_until(self, event_id: str) -> tuple[GraphEvent, ...]: ...
```

This is what powers replay + fork. Today we have no such port; Loop's
`lifecycle` tuple is an in-memory event log but not persisted as a stream.

### 3.3 Why two ports, not one

- `GraphBackend` answers "where is the data?" (swappable: Ladybug/Helix/Falkor/SQLite).
- `EventStore` answers "what happened?" (swappable: SQLite/in-memory/JSONL).
- They are **orthogonal**. You can have LadybugDB graph + SQLite event log,
  or HelixDB graph + in-memory event log. Today they are accidentally coupled.

This solves the user's HelixDB/FalkorDB concern: **write a new
`GraphBackend` adapter, the application doesn't change.**

---

## 4. The 5 new ports and where each primitive lives

| Primitive | New domain type | New L2 port | Adapter |
|-----------|-----------------|-------------|---------|
| Events | `GraphEvent` (id, type, payload, actor, ts) | `EventStore` | SQLiteEventStore, LadybugEventStore, InMemoryEventStore |
| Behaviors | `Behavior` (Protocol: `run(graph, event)`) | `BehaviorRuntime` | ActivegraphRuntimeAdapter, NativeRuntimeAdapter |
| Patches | `Patch` (id, ops, state: proposed/applied/rejected) | `PatchApplier` | ActivegraphRuntimeAdapter, NativePatchApplier |
| Frames | `Frame` (goal, budget, behaviors) | (extend existing `Loop`) | — |
| Policies | `Policy` (rules), `Approval` | `PolicyEngine` | NativePolicyEngine |
| Patterns | `Pattern` (cypher subset + NOT EXISTS) | `PatternMatcher` | ActivegraphPatternAdapter, NativePatternMatcher |
| Replay | — | `ReplayEngine` | ActivegraphReplayAdapter, NativeReplayEngine |
| Fork-and-diff | `Fork`, `Diff` | `ForkEngine` | ActivegraphForkAdapter (uses Runtime.fork + LLM cache) |

The existing 4 ports stay:
- `LLMProviderPort` — unchanged.
- `ReasoningEnginePort` — unchanged.
- `CodeExecutorPort` — unchanged.
- `GraphStore` — **refactored**: becomes a thin facade that delegates to `GraphBackend` (§3.1). Existing callers (`LadybugGraphStore`) keep working; new callers go through `GraphBackend` directly.

---

## 5. How fork-and-diff lands concretely (the killer feature)

This is the one worth building first because it's "most agent frameworks
can't do this". The flow:

```
1. Run A executes, emits events to EventStore.
2. User: "fork run A at event #17, swap model to glm-5.2"
3. ForkEngine.fork(run_a_id, at_event="ev-17") → run_b_id
   - copies events 1..17 from A's log into B's log
   - replays them into a fresh Graph (permissive mode — no behavior re-fire)
   - returns a new BehaviorRuntime bound to run_b
4. BehaviorRuntime.run_goal(...) continues from event 17 with the new model.
   - LLM calls for the shared prefix (1..17) are served from LLMCache → no new LLM calls
   - only new behaviors (18+) call the LLM
5. ForkEngine.diff(run_a, run_b) → Diff
   - structural: which objects/relations diverged
   - event-level: where the traces split
```

Our types:
```python
@dataclass(frozen=True)
class Fork:
    parent_run_id: str
    fork_run_id: str
    at_event_id: str
    config_overrides: dict  # {model: "glm-5.2", ...}

@dataclass(frozen=True)
class Diff:
    divergent_objects: tuple[DivergentObject, ...]
    divergent_relations: tuple[DivergentRelation, ...]
    split_event_id: str  # first event where traces differ
```

The `LLMCache` is its own port (`LLMCachePort` with `get(prompt_key)`,
`record(prompt_key, response)`) so we can use activegraph's cache OR our own.

---

## 6. TL;DR recommendation

**Three-wave absorption, each wave adds ports and one reference adapter.**

### Wave A — Port split + EventStore (M051)
Solve the LadybugDB lock-in and lay the audit-trail foundation.

- New domain: `GraphEvent`, generic `Vertex`/`Edge`.
- New ports: `GraphBackend`, `EventStore`.
- Refactor: `GraphStore` delegates to `GraphBackend`. `LadybugGraphStore`
  becomes `LadybugBackend` (implements `GraphBackend`).
- New adapter: `SQLiteEventStore` (stdlib `sqlite3`, no LadybugDB dependency
  for the event log).
- **Outcome**: graph backend is now swappable. Adding HelixDB or FalkorDB =
  one new adapter file.

### Wave B — Fork-and-diff (M052)
The killer feature.

- New domain: `Fork`, `Diff`, `DivergentObject/Relation`.
- New ports: `ForkEngine`, `ReplayEngine`, `LLMCachePort`.
- New adapter: `ActivegraphForkAdapter` (delegates to `activegraph.Runtime.fork`
  + `activegraph.LLMCache`). This is the ONE place we lean on activegraph
  runtime, behind our port.
- Composition: `--fork <run_id> --at <event_id> --model <new>`.
- **Outcome**: hypothesis testing on agentic systems. "What if model B at
  step 3?" without re-paying LLM costs.

### Wave C — Reactive behaviors + patches (M053)
The reactive half.

- New domain: `Behavior` (Protocol), `RelationBehavior`, `Patch`, `Policy`,
  `Pattern`.
- New ports: `BehaviorRuntime`, `PatchApplier`, `PolicyEngine`,
  `PatternMatcher`.
- New adapter: `ActivegraphRuntimeAdapter` (full reactive runtime).
- New adapter: `NativeRuntimeAdapter` (our own minimal reactive loop, no
  activegraph dependency — for environments where activegraph's claude-pin
  is a blocker).
- **Outcome**: behaviors subscribe to events; relation-behaviors fire on
  edges; patches have audit trail. We can run WITHOUT activegraph (Native)
  OR WITH (Activegraph) depending on the use case.

### Why this order
- Wave A unblocks HelixDB/FalkorDB (your stated concern) and is the
  foundation for B and C (fork needs event log; behaviors need event log).
- Wave B is the single highest-value feature we lack.
- Wave C is the largest scope; doing it last means we've validated the port
  design on A and B before committing to the reactive rewrite.

### What we do NOT do
- We do **not** rewrite existing 50 milestones onto the new runtime. The
  existing `Loop`/`LoopGraph`/`SandboxAgentRunner` keep working; they
  become ONE way to drive the system. The new reactive runtime is a second
  way, for use cases that need it.
- We do **not** make activegraph a hard dependency. Every new port has a
  `Native*` adapter that works without activegraph.
- We do **not** delete `LadybugGraphStore` — it becomes `LadybugBackend`.

---

## 7. Decisions (2026-06-28, user-confirmed)

1. **Wave ordering**: A → B → C. Confirmed.
2. **EventStore abstraction**: the SQLiteEventStore needs its OWN abstraction
   so SQLite and PostgreSQL can be swapped. We introduce a third L2 port —
   `EventLogBackend` — with adapters `SQLiteEventLog`, `PostgresEventLog`,
   `InMemoryEventLog`. (See §7.1 below.)
3. **Activegraph as dependency (Wave B)**: lean toward the **adapter** — i.e.
   `ActivegraphForkAdapter` implements our `ForkEngine` port by delegating
   to `activegraph.Runtime.fork`. Acceptable. (A pure Native fork can be
   added later if we need to run without activegraph.)
4. **Backend priority**: **stay on LadybugDB** for the graph store. The
   abstraction (`GraphBackend`) is built so HelixDB/FalkorDB are possible
   later, but no second adapter is written in Wave A.
5. **Scope of Wave C**: **full reactive** — behaviors + relation-behaviors +
   patterns + policies + patches. Confirmed as the richer, more flexible path.

### 7.1 The three-port split (Wave A, refined)

Because the user wants SQLite vs PostgreSQL swappable for the event log,
Wave A introduces **three** orthogonal ports instead of two:

```
GraphBackend     ← generic Vertex/Edge; adapters translate to graph dialect
                   (LadybugBackend now; HelixBackend/FalkorBackend later)
                   CURRENT: LadybugGraphStore becomes LadybugBackend.

EventStore       ← semantic event-log port (OUR GraphEvent type).
                   Methods: append, iter_events, events_since, events_until.

EventLogBackend  ← raw persistence seam (the new one).
                   Adapters: SQLiteEventLog (stdlib sqlite3),
                             PostgresEventLog (psycopg3 when needed),
                             InMemoryEventLog (tests).
                   EventStore delegates to EventLogBackend.
```

Why two layers (EventStore + EventLogBackend) for events:
- `EventStore` is semantic: it speaks `GraphEvent` objects.
- `EventLogBackend` is dialect: it speaks rows/tuples for whatever DB.
- Mirrors the GraphBackend split: semantic port above, dialect adapter below.
- Swapping SQLite → Postgres = one new `EventLogBackend` adapter; EventStore
  and everything above it are unchanged.

Wave A deliverables (M051):
- domain: `GraphEvent`, generic `Vertex`, generic `Edge`.
- ports: `GraphBackend`, `EventStore`, `EventLogBackend`.
- adapters: `LadybugBackend` (from existing LadybugGraphStore),
  `SQLiteEventLog`, `InMemoryEventLog`.
- refactor: existing `GraphStore` Protocol becomes a thin facade delegating
  to `GraphBackend`, so 50 milestones of callers keep working unchanged.
- Composition wiring: `--event-log sqlite:<path>` flag.

This document was the design. All waves are now DELIVERED:
- Wave A (M051) ✅ — GraphBackend + EventStore + EventLogBackend
- Wave B (M052) ✅ — ForkEngine + LLMCache + TraceCollector + AsyncForkEngine
- Wave C (M053) ✅ — BehaviorRuntime + PatchApplier + PolicyGate + PatternMatcher
- Wave D (M054) ✅ — RelationBehaviorRuntime + GraphViewBuilder + ReactiveFrame + ReplayEngine + real-run integration

All 12 activegraph primitives absorbed. 13 ports. 1838 tests. Governance 100%.
