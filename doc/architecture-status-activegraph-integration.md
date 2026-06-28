# Architecture Status — ActiveGraph Integration Audit (2026-06-28)

**Context:** Project audit after Wave 1 (M047), Wave 2 (M048), Wave 3 (M049). All three waves closed; 1398 tests passing; layering KEPT. Goal: fix the structural misalignment between our implementation and the activegraph framework we depend on.

## TL;DR

We built **parallel abstractions** to activegraph instead of building **on** activegraph. About 70% of the activegraph surface area we depend on is **not wired into our composition flow**. Three adapters exist but are not called anywhere (dead code), one composition entrypoint imports the Diligence pack but does not invoke it. Real-LLM tests caught this drift; production-grade resilience (M038 LLMRouter) is missing from one composition path.

The architectural decision at M002 (or earlier) to build our own `Loop`/`LoopGraph`/`ToolRegistry`/`GraphStore`/`ReasoningEnginePort`/`CodeExecutorPort` was deliberate — the contracts are explicit ports (R002), the layering is enforced (R007), the ports compose via composition. But that choice means activegraph is mostly used as **LLM provider surface only**. We get the protocol conformance, the retry semantics, the structured-message types — and nothing else.

## What We Use From activegraph 1.1.0

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

## Recorded Decision (today)

We **continue with Wave 4 (DSPy/FastRLM adapters, M051-M053)** and **defer the activegraph-integration choice** to a future Wave 5 / Wave 6. The audit lives here so the next milestone can decide which option to take. No code changes — this is **fixation of state**.

## What This Means Going Forward

1. **Wave 4 (DSPy / FastRLM)** proceeds without touching activegraph. DSPy becomes a ReasoningEnginePort strategy behind our `PlainLLMStrategy`. FastRLM gets its own adapter. RLM / ACP delegation is M052.
2. **Future wave** may choose Option A, B, or C. Option B is the most likely compromise — keeps our investment in 4 ports + verifier, gets activegraph event log + tools + metrics.
3. **M038 LLMRouter gap** in `composition/diligence.py` remains an open issue. Mark as follow-up.
4. **Dead-code cleanup** is a 30-minute task (Option C) and can be done at any time without waiting for strategy.

## Cross-References

- M041 — LadybugGraphStore adapter (our GraphStore)
- M042-M046 — Sandbox (our verifier + reasoning executor)
- M047 — Disk persistence + graph queries + ratchet
- M048 — Trajectory logging (Wave 2)
- M049 — Insight & Feedback Loop (Wave 3)
- D009-D018 — RGLA, dogfood, Mini/Maxi, DSPy, CodeExecutor, ReasoningEngine, RLM
- Memory MEM062, MEM063 — Wave 1/2/3 closure notes
- Roadmap: HANDOFF.md Wave 1 ✅ / Wave 2 ✅ / Wave 3 ✅ / Wave 4 next / Wave 5+ TBD