# Trace & Observability — Reactive/Async Debugging Foundation

> Status: **research / design**. Companion to D019 (reactive+async assessment).
> Source: activegraph 1.1.0 observability module + our EventStore (M051).
>
> Question: how do we get **traces** for debugging reactive/async processes,
> leveraging activegraph's state ideology while accounting for our hexagonal
> architecture?

## 1. What activegraph Already Provides

activegraph has a **mature observability layer** (`activegraph.observability`):

| Primitive | What it carries | Our equivalent |
|-----------|----------------|----------------|
| `EventSummary` | id, type, actor, timestamp | `GraphEvent` (id, type, payload, actor, run_id, caused_by, timestamp_ns) |
| `FrameSnapshot` | id, name (frame context) | `Loop` (intent, budget, skills) |
| `RuntimeStatus` | run_id, state, queue_depth, events_processed, budget, frame, registered_behaviors, recent_events | **NONE** — we don't have a runtime status snapshot |
| `BehaviorInfo` | name, kind, subscribed_to, pattern, activate_after | **NONE** — no behaviors yet (Wave C) |
| `BudgetSnapshot` | used, limits, cost_used_usd, cost_limit_usd, exhausted_by | `Budget` (domain) — but no snapshot serializer |
| `Metrics` (Protocol) | counter, gauge, histogram | **NONE** — only loguru file sink |
| `runtime_log_extra` | builds `extra=` dict for structured logs | **NONE** — our logs are plain format strings |
| `Runtime.export_trace(path)` | exports full event trace to file | EventStore.iter_events (but no export-to-file) |
| `Runtime.print_trace()` | prints trace to console | **NONE** |

### Key insight: activegraph's trace = event log + status snapshots

activegraph's debugging model is:
1. **Event log** = append-only history of everything that happened
2. **RuntimeStatus** = point-in-time snapshot of the runtime state
3. **export_trace** = dump the event log to a file for offline analysis
4. **Metrics** = counters/gauges/histograms for quantitative observability

We already have #1 (EventStore from M051). We're missing #2, #3, #4.

## 2. Our Specifika (Hexagonal Constraints)

activegraph's observability lives in the **runtime layer** — it sees everything
because the runtime IS the central coordinator. Our architecture is different:

```
activegraph:  Runtime → Behaviors → Graph (one central coordinator)
ours:         Composition → Use Cases → Ports → Adapters (distributed)
```

This means:
- We can't just "add a RuntimeStatus" — there's no single runtime to snapshot.
- Our traces must span **multiple layers**: CLI invocation → use case → port → adapter → LLM/DB.
- Our async/reactive (Wave B/C) will have **concurrent operations** — traces must
  carry **causality** (which event caused which) to reconstruct ordering.

## 3. What We Need: A Trace Layer

### 3.1 TraceEnvelope (domain)

```python
@dataclass(frozen=True)
class TraceEnvelope:
    """A traced operation spanning multiple layers.

    Carries:
      - trace_id: unique per top-level operation (e.g. one sandbox run).
      - span_id: unique per sub-operation (e.g. one LLM call, one graph query).
      - parent_span_id: causality chain (None for root).
      - layer: which architectural layer (composition/application/adapter).
      - operation: what happened (e.g. "llm.complete", "graph.query", "verify").
      - started_at / ended_at: timing.
      - status: ok / error / timeout.
      - attributes: structured key-value (model, tokens, exit_code, etc.).
    """
    trace_id: str
    span_id: str
    parent_span_id: str | None
    layer: str           # "composition" | "application" | "adapter"
    operation: str       # "llm.complete" | "graph.upsert_vertex" | ...
    started_at: int      # ns
    ended_at: int | None
    status: str          # "ok" | "error" | "timeout"
    attributes: dict[str, Any]
```

### 3.2 TraceCollector port (application)

```python
class TraceCollector(Protocol):
    """Collects trace spans across layers. Pure application port."""
    def start_span(self, operation: str, *, parent: str | None = None,
                   layer: str = "application", **attrs) -> str: ...
    def end_span(self, span_id: str, *, status: str = "ok", **attrs) -> None: ...
    def export(self, path: str) -> None: ...
    def iter_spans(self, trace_id: str | None = None) -> Iterator[TraceEnvelope]: ...
```

### 3.3 Adapters

- **InMemoryTraceCollector** — tests, default.
- **EventStoreTraceCollector** — bridges to our EventStore (M051): each span = a GraphEvent.
- **ActivegraphTraceAdapter** — bridges to activegraph's export_trace + RuntimeStatus.
- **OpenTelemetryTraceAdapter** — for production (OTLP export to Jaeger/Tempo).

### 3.4 Instrumentation points

```
Composition layer:
  _dispatch()           → start trace_id
  _run_single_model()   → span "sandbox.run"
  _run_governance_check → span "governance.check"

Application layer:
  SandboxAgentRunner.run()    → span "agent.run" (parent: sandbox.run)
  verify_candidate()          → span "verify" (11 sub-spans for 11 axes)
  emit_trajectory_events()    → span "emit.events"

Adapter layer:
  MiniMaxProvider.complete()  → span "llm.complete" (model, tokens, latency)
  LadybugBackend.upsert_vertex → span "graph.upsert" (vertex_id)
  BwrapExecutor.execute()     → span "code.execute" (exit_code, duration)
```

## 4. How This Amplifies activegraph's State Ideology

activegraph's "state ideology" = **the event log IS the state**. Every mutation
is an event; replay reconstructs state. Our trace layer AMPLIFIES this:

| activegraph | Our enhancement |
|-------------|-----------------|
| Event log (what happened) | + Trace spans (WHY it happened, causality chain) |
| RuntimeStatus (current state) | + TraceCollector.export (full timeline for offline analysis) |
| export_trace (dump to file) | + EventStoreTraceCollector (persist spans in our EventStore) |
| Metrics (counters/gauges) | + Governance axes (our 8 quality metrics as gauges) |
| runtime_log_extra (structured logs) | + TraceEnvelope.attributes (structured per-span data) |

The result: we get **distributed tracing** across our hexagonal layers, while
activegraph gets **causality-aware spans** that it doesn't have today.

## 5. Practical Debugging Scenarios

### Scenario A: "Why did fork produce different output?"

```
Trace shows:
  trace_id=fork-run-abc
    span "fork.create" parent=fork-run-abc → split at event evt-017
    span "llm.complete" model=glm-5.2 parent=fork-run-abc → different response
    span "verify" parent=fork-run-abc → score 0.8 (parent had 1.0)
  → The fork diverged at the LLM call (different model → different code → lower score)
```

### Scenario B: "Why is governance check slow?"

```
Trace shows:
  trace_id=governance-xyz
    span "layering"     duration=5s
    span "ruff"         duration=2s
    span "ty"           duration=8s    ← bottleneck
    span "pyrefly"      duration=0s    ← cached
    span "riskratchet"  duration=15s   ← bottleneck (pytest --cov)
    span "convention"   duration=0.3s
    span "tests"        duration=80s   ← biggest
    span "ast_symbols"  duration=0.1s
  → tests + riskratchet dominate; parallelize them for 2x speedup
```

### Scenario C: "Which behavior fired and why?" (Wave C reactive)

```
Trace shows:
  trace_id=reactive-run-def
    span "event.object_created" type=claim
    span "behavior.evidence_check" triggered_by=object.created pattern="claim"
      → subscribed to pattern, fired automatically
    span "behavior.failed" reason="no evidence found"
  → The evidence_check behavior fired on claim creation but failed (no evidence)
```

## 6. Recommendation

**Add TraceCollector port + TraceEnvelope domain type as the FIRST slice of Wave B.**

Rationale:
- Wave B (fork-and-diff) needs traces to debug "why did fork diverge?"
- Wave C (reactive) needs traces to debug "which behavior fired?"
- async needs traces to debug "where is the event loop blocked?"
- Without traces, reactive/async is a black box — we'd be debugging blind.

The trace layer is CHEAP to add (one port + one domain type + InMemory adapter)
and IMMEDIATELY useful (instrument governance check, sandbox runs, LLM calls).
It bridges to activegraph's export_trace when we need vendor-level detail.

### Concrete plan

```
M052 S00 (pre-Wave B): Trace foundation
  - domain/trace.py: TraceEnvelope dataclass
  - application/ports/trace_collector.py: TraceCollector Protocol
  - adapters/inmemory_trace_collector.py: InMemoryTraceCollector
  - adapters/eventstore_trace_collector.py: bridge to EventStore
  - Instrument: _dispatch, _run_governance_check, SandboxAgentRunner.run, MiniMaxProvider.complete
  - CLI: --trace sqlite:runs/traces.db (export traces)
  - CLI: --trace-print <trace_id> (print span tree)

M052 S01+: ForkEngine uses TraceCollector for fork-divergence debugging
M053 S01+: BehaviorRuntime uses TraceCollector for behavior-trigger debugging
```
