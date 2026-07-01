# Architecture Status — ActiveGraph Integration Audit

> **Updated 2026-06-30** after Waves A/B/C/D (M051-M054) completion.
> Original audit was 2026-06-28 (pre-absorption); this is the post-absorption status.
>
> **TL;DR: All 12 activegraph primitives are now absorbed into our hexagonal
> architecture. The parallel-abstractions gap identified in the original audit
> is CLOSED. ActiveGraph is used as ONE adapter behind our ports, not imported
> directly. The reactive runtime is production-ready.**

## Original Problem (2026-06-28, now resolved)

We built **parallel abstractions** to activegraph instead of building **on**
activegraph. About 70% of the activegraph surface area we depended on was
**not wired into our composition flow**. Three adapters existed but were not
called anywhere (dead code), one composition entrypoint imported the Diligence
pack but did not invoke it.

The architectural decision at M002 to build our own `Loop`/`LoopGraph`/
`ToolRegistry`/`GraphStore`/`ReasoningEnginePort`/`CodeExecutorPort` was
deliberate — the contracts are explicit ports (R002), the layering is enforced
(R007). But that choice meant activegraph was mostly used as **LLM provider
surface only**.

## Resolution (Waves A/B/C/D, M051-M054)

We did NOT rewrite onto activegraph runtime. Instead, we **absorbed the
concepts** into our own ports and domain types:

- 12 activegraph primitives → our domain types + 13 ports
- activegraph becomes ONE adapter option behind ports
- Every new port has a Native* adapter (no activegraph dependency)
- Existing Loop/LoopGraph/SandboxAgentRunner keep working (one driver)
- New reactive runtime is a second driver (for use cases that need it)

## Current Surface Usage (2026-06-30)

| Surface | Files | Status |
|---|---|---|
| `activegraph.llm.anthropic` | adapters/llm/minimax/_provider.py | **Live**. MiniMaxProvider extends AnthropicProvider with `recognizes_model` override (M044 bugfix). |
| `activegraph.llm.types` | adapters/llm/minimax/_provider.py | **Live**. LLMMessage, LLMResponse, ToolCall. |
| `activegraph.llm.errors` | adapters/llm/minimax/_provider.py | **Live**. LLMBehaviorError classification. |
| `activegraph.packs.diligence` | composition/diligence.py | **Imported but NOT invoked from main flow.** M044 real-LLM: pack pins claude-*; fails stably on minimax/glm via proxy. xfail strict. |
| `activegraph.runtime.diff` | adapters/runtime/activegraph.py | **Imported, never called.** We have our own SandboxRunDiff (M049). |
| `activegraph` (Graph, Runtime, Event) | adapters/activegraph_event_sink.py, activegraph_experiment_workspace.py, runtime/activegraph.py | **Imported in dead adapters, no production callers.** |

## What activegraph Offers That We Re-Implemented

| activegraph feature | Our equivalent | Gap |
|---|---|---|
| `activegraph.store.SQLiteEventStore` + `open_store` + `replay_into` | `LadybugGraphStore` (M047) + `store_loop_graph` | Persists to LadybugDB not SQLite; no `replay_into` event log. |
| `activegraph.tools.get_tool_registry` + `make_graph_query_tool` | `ToolRegistry` in `application/ports/tool.py` | Tool graph query built by hand. |
| `activegraph.llm.RecordingLLMProvider` + `LLMCache` | none | No recording layer; no LLM cache for repeated prompts. |
| `activegraph.llm.parse_structured_response` + `schema_to_json` | none | Verifier axes parse raw text by hand. |
| `activegraph.runtime.scheduler` + `view_builder` + `patterns` | `SandboxAgentRunner.run()` is a hand-rolled scheduler | No declarative pattern matching. |
| `activegraph.packs.Pack` + `LLMBehavior` + `RelationBehavior` + `migrate` | `Evolvable` interface (M015) + `LoopGraph` projection | Different abstraction; not interoperable with activegraph packs. |
| `activegraph.observability.Metrics` + `PrometheusMetrics` + `OpenTelemetryMetrics` + `status` | none | No metrics exported; only loguru file sink. |
| `activegraph.cli.main` + `EXIT_CODES` | our `composition/cli_exit.py` (M049 S04) | Duplicated; not aligned with activegraph's exit codes. |
| `activegraph.runtime.budget` | our `Budget` in `domain/loop.py` (D011) | Reinvented with same intent. |
| `activegraph.core.patch` + `view` + `ids` | none | No patch protocol. |
| `activegraph.trace` | none | Empty subpackage — possibly future API. |

## Dead Code

Three adapters in `src/active_skill_system/adapters/` import activegraph but are **not referenced** by any composition entrypoint:

```
adapters/activegraph_event_sink.py            no callers
adapters/activegraph_experiment_workspace.py  no callers (Runtime.fork() requires SQLite)
adapters/runtime/activegraph.py                only Diff import, no callers
```

`composition/diligence.py` has the Diligence pack loaded but `main()` is not wired into `mini_sandbox.py`. After M044 real-LLM testing the Diligence path fails stably for non-claude models (`network_error` because M038 LLMRouter retry/fallback is **not wired into the Diligence composition** — pack uses MiniMaxProvider directly). The composition file exists, has tests, but does not run.

## M038 LLMRouter Gap (Surfaced by Real-LLM)

`M038` built cost-aware provider fallback (minimax → glm → gemini → kr) with retry/backoff. Wired into:
- `composition/mini_sandbox.py` via ReasoningEnginePort → LLMRouter (live)
- **NOT wired into** `composition/diligence.py` (uses MiniMaxProvider directly).

Consequence: if proxy returns 5xx for minimax during a Diligence run, retry does not happen; behavior.failed. Real-LLM test `test_real_tool_loop_no_2013` is xfail strict for this reason. This is a **production resilience gap** hidden by the framing "Diligence is experimental."

## Layering Constraint (R002/R007/R008/R009)

Our ports and use-cases are pure-domain (no activegraph imports in `application/` or `domain/`). All activegraph imports live in `adapters/` (L3) or `composition/` (L4). This is **good architecture** — it means we can swap out activegraph without touching business logic. It also means adapters that nobody calls are not "discovered" by the layering guard; they just sit there.

## Three Strategic Options (Not Committed)

These are recorded for future consideration, not for current scope. We chose to **record and continue** with Wave 4 (DSPy/FastRLM).

### Option A — Migrate composition to activegraph
Replace our `Loop`/`LoopGraph`/`GraphStore`/`ToolRegistry`/`composition/mini_sandbox.py` with activegraph.store.SQLiteEventStore + activegraph.packs.diligence + activegraph.cli.main. Use `replay_into` for provenance, `get_tool_registry` for tools, `Metrics` for fitness history, `scheduler` for batch runs.
- **Cost**: large refactor across 49 milestones; loses our generic ports and 11-axis verifier as separate concerns; requires fixing Diligence↔non-claude incompat.
- **Benefit**: full event log replay, structured metrics, declarative patterns, pack ecosystem.

### Option B — Hybrid (activegraph as second sink/tool layer)
Keep our 4 generic ports + 11-axis verifier. Add adapters that turn our `Loop` into `activegraph.Event` (the dead `activegraph_event_sink.py` becomes live). Add an `activegraph_tool_registry.py` adapter exporting our ToolRegistry via `make_graph_query_tool`. Use `SQLiteEventStore` as a parallel sink. Export `Metrics` for fitness history.
- **Cost**: medium work; two systems coexist; need careful naming to avoid confusion.
- **Benefit**: our abstractions preserved; activegraph surface becomes queryable; portable to projects without activegraph; layering KEPT.

### Option C — Delete dead code, document scope
Remove `activegraph_event_sink.py`, `activegraph_experiment_workspace.py`, `runtime/activegraph.py` (Diff only). Keep `composition/diligence.py` as `experimental` with a README warning. Document in `PROJECT.md` that activegraph is used as LLM provider surface only.
- **Cost**: minimal.
- **Benefit**: honest scope; no false promises; cleanup.
- **Trade-off**: leaves potential on the table; future option B becomes Option A later.

## Recorded Decision (RESOLVED)

The original audit deferred the activegraph-integration choice to a future wave.
**That choice was made and executed in Waves A/B/C/D (M051-M054):**

**Option B-Plus (Hybrid with full absorption) was implemented.** We kept our
4+ generic ports + 11-axis verifier AND absorbed all 12 activegraph primitives
into our own domain types + ports. activegraph becomes ONE adapter option
behind our ports. Dead adapters remain documented but not deleted (historical
reference). M038 LLMRouter gap CLOSED (M054 S08).

## 12 Primitive Coverage (2026-06-30)

| # | Primitive | Status | Port / Adapter |
|---|-----------|--------|----------------|
| 1 | Graph | ✅ | GraphBackend (LadybugBackend) |
| 2 | Events | ✅ | EventStore + EventLogBackend |
| 3 | Behaviors | ✅ | BehaviorRuntime (InMemory/Pattern/Relation/EventEmitting) |
| 4 | Relations | ✅ | RelationBehaviorRuntime |
| 5 | Patches | ✅ | PatchApplier (InMemory/EventEmitting) |
| 6 | Views | ✅ | GraphViewBuilder |
| 7 | Frames | ✅ | ReactiveFrame + FrameBudget |
| 8 | Policies | ✅ | PolicyGate (4 rules) |
| 9 | Patterns | ✅ | PatternMatcher (EXISTS/NOT_EXISTS) |
| 10 | Replay | ✅ | NativeReplayEngine (strict/permissive) |
| 11 | Fork-and-diff | ✅ | ForkEngine + AsyncForkEngine + ForkReplayCacheEngine |
| 12 | Failure model | ✅ | behavior.failed events + Loop FAILED |

## What This Means Going Forward

1. **All 12 primitives absorbed** — no more parallel-abstractions gap.
2. **Reactive runtime production-ready** — ReactiveSandboxAgentRunner fires
   behaviors during REAL LLM agent runs, not just demo mode.
3. **M038 LLMRouter gap CLOSED** — RouterBackedReasoningEngine (M054 S08).
4. **Dead adapters** remain documented (historical reference); not deleted.
5. **Next: Wave E (M055)** — Maxi scaling: multi-domain benchmarks, Golden Sessions.

## Cross-References

- M041 — LadybugGraphStore adapter (our GraphStore)
- M042-M046 — Sandbox (our verifier + reasoning executor)
- M047 — Disk persistence + graph queries + ratchet
- M048 — Trajectory logging (Wave 2)
- M049 — Insight & Feedback Loop (Wave 3)
- D009-D018 — RGLA, dogfood, Mini/Maxi, DSPy, CodeExecutor, ReasoningEngine, RLM
- Memory MEM062, MEM063 — Wave 1/2/3 closure notes
- Roadmap: HANDOFF.md Wave 1 ✅ / Wave 2 ✅ / Wave 3 ✅ / Wave 4 next / Wave 5+ TBD