# Recursive Graph Loop Architecture (RGLA) — Design Document

> Status: **design / research artifact**. No production code yet. This document
> synthesizes a conceptual proposal ("Recursive Graph Loop Architecture") into an
> engineering architecture for `active-skill-system`, grounded in what the project
> already implements and what it does not.
>
> Companion decision: D009 (RGLA adoption scope and sequencing).
> Inputs: Loop Engineering, Harness Engineering, RLM/OpenProse, SkillGenome,
> SkillNet/EvoSkill, ActiveGraph.

## 1. TL;DR

RGLA proposes **Loop** as the primary unit of an agent system — not task, not
agent, not skill. A Loop is an event-sourced, self-describing unit of work that
carries Intent, State, Skills, Memory, Policies, Context, and Metrics, and that
can be observed, replayed, compared, and evolved. The distinctive claim is a
**LoopGraph**: a provenance graph over Loop execution that makes the system's own
behaviour queryable (`VERIFIED_BY`, `LEARNS_FROM`, `FIXES`, `SUPERSEDES`).

This document converts that vision into a buildable architecture by:
(a) mapping RGLA concepts onto the existing layered + event-sourced + evolvable
system, (b) separating the load-bearing ideas from the premature ones,
(c) fixing contracts at the type level without writing runtime code, and
(d) keeping storage behind a port (with LadybugDB as the primary adapter
candidate) and deferring Rust and "marketplace" concerns behind explicit
revisit criteria.

## 2. Core thesis and the one load-bearing idea

The single idea worth building around:

> **Loop is a first-class, event-sourced domain entity with an explicit
> lifecycle, and the relationships between loops, skills, verifiers, failures,
> and policies form a queryable provenance graph (LoopGraph).**

Everything else in the original vision — self-modification, dual stores,
marketplace, RLM-over-graph — is either a generalization of something already
present, a deferred concern, or a risk to be contained. The LoopGraph is the
novel, valuable, and *missing* piece; making Loop a named entity is the
prerequisite.

Why this framing matters: it keeps RGLA **composable** with the existing
architecture (Layered + Event-sourced + Evolvable) instead of **replacing** it.
RGLA does not discard domain/application/adapters/composition; it adds a Loop
domain and a provenance projection.

## 3. Mapping onto the existing system

A large part of RGLA is already present, just not named "Loop". Recognising this
prevents reimplementation and scopes the real gap.

| RGLA concept | Already in project | Status |
|--------------|--------------------|--------|
| Loop = event-sourced | `RuntimePort.replay`, ActiveGraph event log, M039 `--emit-runlog` | present, unnamed-as-Loop |
| Skill = executable graph | `domain/runtime/graph.py`, `nodes.py`, `edges.py`, `fsm.py` | present |
| Verification / anti-fancy | `VerifiedToolResult`, `EvidenceLedger`, repair policies | present |
| Evolution of skills | `EvolutionEngine`, `MultiEvolvableEngine`, 12 Evolvable genomes | present |
| SkillGenome | `model_genome.py`, `prompt_genome.py`, `*_types.py` | present |
| Thin harness | `harness/AGENTS.md`, `harness/loader.py` (M033) | present |
| Failure → knowledge | `ratchet/ledger.py` (append-only) | present, not graph-linked |
| **Loop domain entity** | — | **GAP** |
| **LoopGraph provenance** | — | **GAP** |
| Loop-level self-critique/optimization | `EvolutionEngine` (skill-level only) | partial |

**Conclusion:** the gap RGLA fills is (1) a named `Loop` domain entity with a
lifecycle, and (2) a provenance graph linking loops to the skills/verifiers/
failures/policies that produced and refined them. These two are the build
targets. Storage is behind a port (LadybugDB candidate, §7); Rust and
marketplace are explicitly out of scope until their revisit criteria fire (§6).

## 4. Contracts (type-level, no runtime code)

### 4.1 Loop domain entity

```
Loop {
  id            : LoopId
  intent        : Intent           # what the loop is for (declarative)
  state         : LoopState        # FSM: PENDING → RUNNING → VERIFYING → (DONE | FAILED | RETAINED)
  lifecycle     : list<LoopEvent>  # append-only journal of state transitions
  skills        : set<SkillRef>    # skills the loop is composed of
  memory        : ContextRef       # pointer, not inline blob
  policies      : set<PolicyRef>   # budget, termination, safety
  context       : ContextRef       # assembled context graph (§4.3)
  metrics       : LoopMetrics      # cost, iterations, fitness
  budget        : Budget           # termination guarantee — REQUIRED
}
```

Invariants (to be enforced when implemented):
- Every Loop has a non-null `Budget` and a termination policy. **A Loop that
  "never ends" is a contract violation, not a feature.**
- `lifecycle` is append-only; state transitions are derived, never mutated.
- `state` is a projection of `lifecycle`, not independent storage.

### 4.2 LoopGraph (provenance projection)

Vertex types: `Intent, Loop, Skill, Context, Failure, Verifier, Policy,
Benchmark, Memory, Pack`.

Edge types (typed, not free-form):
```
USES(loop, skill)
VERIFIED_BY(loop, verifier)
CREATED(loop, intent)
LEARNS_FROM(loop_a, loop_b | failure)
FIXES(loop, failure)
SUPERSEDES(loop_a, loop_b)
DEPENDS_ON(loop_a, loop_b)
MUTATED_BY(loop, evolution_run)
```

Critical distinction — **two read/write profiles**:
- **Runtime edges** (`USES`, `DEPENDS_ON`): written during execution, may change.
- **Provenance edges** (`VERIFIED_BY`, `FIXES`, `SUPERSEDES`, `LEARNS_FROM`):
  append-only, written once on loop completion. This separation prevents the
  high-coupling failure mode where editing one loop invalidates many.

The LoopGraph is a **projection/read-model** (mirrors ActiveGraph claim C8),
rebuildable from the event log. It is not the source of truth.

### 4.3 Context Graph (not "a prompt")

A Loop's context is a small assembled graph, not a flat string:
```
ContextGraph {
  current_intent, relevant_events, relevant_skills, memory,
  policies, graph_neighbourhood, active_hypothesis, budget
}
```
The LLM receives a *rendering* of this graph, not raw text. This is a contract
for a future `ContextAssembler` port; the rendering strategy is deferred.

## 5. What we build vs. what we defer

### Build (first milestone, when authorized)
1. `domain/loop.py` — `Loop` entity + `LoopState` FSM + `LoopEvent` journal,
   with invariants and a REQUIRED `Budget` (no infinite loops).
2. `domain/loop_graph.py` — vertex/edge type definitions + a pure projection
   function `project(events) -> LoopGraph`. Read-only query API (`query(pattern)`).
3. Tests proving: append-only lifecycle, termination-budget invariant, provenance
   edges derived from events, projection is rebuildable.

### Defer (with revisit criteria — do NOT build before these fire)
| Deferred item | Revisit criterion |
|---------------|-------------------|
| Self-modifying loop (Critic→Optimizer chain) | A working Loop domain exists AND a benchmark shows skill-level evolution alone misses system-level regressions. |
| RLM-over-graph (recursive graph queries) | A concrete decomposition need that file-RLM cannot serve AND where the decomposition is **model-picked** (hardcoded map-reduce is NOT sufficient — it fails the RLM rubric); plus recursion-depth safeguards (REQUIRED Budget on each recursive Loop) designed. |
| Dual/multi-store (PostgreSQL + a second store) | The LadybugDB adapter is proven insufficient at measured scale; cross-store consistency cost justified (§7.4). |
| Rust/PyO3 Loop runtime | Profiler shows the Python Loop/event path is a hot spot. |
| Loop Marketplace / Transfer | Two real projects share an identical Loop schema and manual transfer is painful. |

The revisitable decisions are recorded in D009 (RGLA scope) and D010 (LadybugDB
as storage candidate).

## 6. Risks and mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| Second-system effect: building all 12 subsystems at once | High | Strict §5 build/defer split; one Loop domain + projection first. |
| High coupling via single LoopGraph | High | Separate runtime vs provenance edges (§4.2); provenance append-only. |
| Infinite/self-modifying loops | High | REQUIRED `Budget` + termination policy as an invariant, not a nicety. |
| Polyglot persistence burden | Medium | Defer to single store; revisit only on measured scale. |
| Conceptual recursion (pack-with-harness) | Medium | Harness is the *kernel*; pack is *data/skills*, never a nested harness. |
| Provenance graph rebuild cost | Medium | LoopGraph is a projection; rebuildable from events, can be snapshotted. |

## 7. Storage strategy

**Storage is a port; LadybugDB is the primary adapter candidate.** The domain
never imports a database (R002); it depends on a `GraphStore` Protocol (and a
narrower `LoopStore` view). Concrete adapters live in L3 and are wired at
composition time.

### 7.1 Primary candidate — LadybugDB

[LadybugDB](https://docs.ladybugdb.com) is an **embedded graph database** (the
Kùzu lineage; Kùzu was acquired by Apple and LadybugDB carries the vision
forward). Verified installable and working in this environment via the PyPI
package `ladybug` (v0.17.1): `:memory:` mode, Cypher, and **typed relationship
tables** — a smoke test created a `Loop` node table, a Cypher MATCH query, and a
typed `VERIFIED_BY(FROM Loop TO Loop)` provenance edge, all in-memory.

Why it fits RGLA specifically:

| RGLA need | LadybugDB provides |
|-----------|--------------------|
| LoopGraph vertices + typed edges | Native property graph + typed `REL TABLE` |
| Queryable provenance (`VERIFIED_BY`, `LEARNS_FROM`, `SUPERSEDES`) | Cypher `MATCH` |
| Deterministic, serverless test suite | `:memory:` mode (like SQLite for graphs) |
| Context Graph / semantic search | Built-in vector indices + full-text search |
| Offline evolution without external services | Embedded, no server process |

One embedded store therefore covers graph + vectors + tests, instead of the
earlier in-memory + JSONL + separate-vector-store sketch.

### 7.2 Layering (non-negotiable)

```
application/ports/graph_store.py   # GraphStore Protocol (infra-free)
adapters/ladybug_graph_store.py     # LadybugDB adapter (L3)
composition/...                     # wires adapter → port
```

`domain/loop.py` and `domain/loop_graph.py` depend on **no** database. The
LoopGraph *type* lives in the domain; its *persistence* lives behind the port.
This preserves R002 (domain/application infra-free) under import-linter
enforcement — the same discipline applied to every adapter since M005.

### 7.3 Maturity caveat (recorded, not blocking)

LadybugDB is young (v0.17; Kùzu→Apple transition). For a research/exploration
project like active-skill-system this is acceptable; for production it is a
risk. The port abstraction is the mitigation: if LadybugDB stalls, a different
`GraphStore` adapter (Neo4j, DuckDB+graphs, or even an in-process dict) can
replace it without touching the domain. The revisit criterion for swapping is
"LadybugDB fails to meet a measured RGLA query/throughput need or stops active
maintenance."

### 7.4 What stays deferred

- **Dual PostgreSQL + FalkorDB**: not adopted. One embedded store is sufficient
  until a measured need (cross-store transactions, separate OLTP/OLAP scale)
  appears — §5 revisit criterion unchanged.
- **Persistence-on-disk for the suite**: tests use `:memory:`; disk (`.lbdb`) is
  an opt-in composition choice, never required to run the suite.

## 8. Relationship to ActiveGraph

ActiveGraph remains the **production event-sourced runtime** (claims C5–C9,
`RuntimePort`): it owns fork/diff/replay/behaviors and the live graph. RGLA's
`Loop` is a **domain-level abstraction over runs**, and the LoopGraph is a
**provenance projection** — neither replaces ActiveGraph. The integration seam is
the existing `RuntimePort`: a Loop's lifecycle events can be sourced from
ActiveGraph events via the `ActivegraphEventSink`/`RuntimePort.replay` contract.
RuVector (D008) is unaffected: it stays an offline test container, not the Loop
store.

## 9. Open questions (to resolve before the build milestone)

1. Is a `Loop` one ActiveGraph *run*, or a finer-grained unit? (Affects LoopGraph
   cardinality and replay semantics.)
2. Who writes provenance edges — the loop itself on completion, or a separate
   observer (cleaner separation, harder to keep consistent)?
3. Does the Context Graph require a new port, or can it reuse `RuntimePort` +
   a `ContextAssembler`? RLM research (§10) indicates a dedicated externalized-context
   port is warranted: the model operates on the context symbolically rather than
   reading it into the window.
4. What is the minimal termination policy set (budget calls, budget cost,
   max iterations, deadline) that is REQUIRED vs. configurable?

These are design questions, not blockers — they should be answered in the first
build milestone's CONTEXT, not before it.

## 10. Relationship to Recursive Language Models (RLM)

RLM (Recursive Language Models, arXiv:2512.24601; OpenProse / "Recursive Coding
Agents", Weitekamp 2026) is not a competing paradigm — it is the **reasoning
mechanism that makes a Loop genuinely recursive**. Without RLM, a Loop is an
event-sourced workflow (which this project already has via `RuntimePort`). With
RLM, a Loop can decompose its own Intent into sub-Loops.

### 10.1 What RLM adds to RGLA

The RLM rubric (executable env / prompt externalized / code calls model /
**model picks decomposition** / state stays symbolic) maps directly onto RGLA:

| RLM rubric | RGLA realisation |
|------------|------------------|
| Executable env | Loop runs in the harness runtime (M033) |
| Prompt externalized | Loop's Intent + Context Graph are graph nodes, not inline text (§4.3) |
| Code calls model | `LLMProviderPort` / `LLMRouter` (M011/M038) |
| Model picks decomposition | **GAP** — EvolutionEngine is currently deterministic, not LLM-driven |
| State stays symbolic | Loop state is event-sourced; LoopGraph is a projection (§4.2) |

The single gap is *model-picked decomposition*. Closing it is the RLM step for
RGLA — but it remains deferred behind the §5 revisit criterion (now narrowed:
map-reduce is NOT enough; the decomposition must be model-chosen).

### 10.2 Golden Sessions → Programs (new capability, not yet built)

RLM's most transferable pattern for this project is **Golden Sessions →
Programs**: take a successful run and have an agent compile it into a reusable
workflow. This is the missing bridge between pieces the project already has:

```
run-log (M039) + evidence ledger + ratchet  →  Golden Session  →  fat-skill (.prose/.md)
```

Today these are disconnected: run-logs record history, fat-skills are hand-
authored. A Golden Session compiler would turn a promoted evolution run into a
reproducible skill — composing RLM with the existing evolution engine.

### 10.3 RLM rubric as an evaluation framework

The 7-gate RLM rubric is a ready-made checklist for auditing this project's
harness: which gates pass, which sag. Running the current harness/evolution
workflow through it is a low-cost way to prioritise the next milestone (and is
explicitly out of scope for this document — it is a follow-up action).

### 10.4 Discipline RLM does NOT relax

RLM's "trust = reliability" thesis is orchestration-level, not proof-level. It
 does not remove any RGLA safeguard:
  - **REQUIRED Budget** on every recursive Loop (recursion without a budget is a
    contract violation — D009). RLM recursion-depth guards reinforce this.
  - **Verification** (`VerifiedToolResult`, `EvidenceLedger`) stays mandatory;
    OpenProse's "logical English" is trust-through-orchestration, not
    trust-through-proof.
  - **Provenance** (LoopGraph) is unchanged; it is what makes a Golden Session
    compilable in the first place.
  - **Typed sub-Loop contracts** (new, from §10.6 case study): every sub-Loop
    return must be typed (schema-validated), not free-text. The free-text
    fan-out failure mode shows *why* — untyped boundaries confound the
    aggregator. The typed payload **is** the LoopGraph provenance edge payload.

### 10.5 Decision recorded

D011 captures the RLM integration stance: RLM is the reasoning mechanism for the
Loop; Golden Sessions→Programs is a future capability; the 7-gate rubric is the
evaluation framework; no RLM-over-graph build until its (narrowed) revisit
criterion fires and Budget safeguards exist on every recursive Loop. The fast-rlm
structured-output case study (§10.6 / `doc/rgla-fast-rlm-research.md` §5) adds:
typed evidence at sub-Loop boundaries is the **durable layer** that outlives any
RLM engine — engines are swappable L3 adapters, typed provenance is the asset.

### 10.6 Reference implementation: fast-rlm

[avbiswas/fast-rlm](https://github.com/avbiswas/fast-rlm) (PyPI `fast-rlm`) is a
concrete, installable RLM implementation studied as a reference (not adopted as
a dependency). It validates several RGLA decisions and offers transferable
patterns. Full notes: `doc/rgla-fast-rlm-research.md`.

**How it realises the RLM rubric:** an LLM writes code into an external REPL
(sandboxed via **Deno + Pyodide**) that operates on the prompt symbolically —
the prompt is never loaded whole into the context window. Sub-agent responses
are returned as **symbols/variables in the parent REPL**, not auto-streamed
into the parent context (the crux of RLM's infinite-context property).

**Transferable patterns confirmed against this project:**

| fast-rlm mechanism | RGLA / project analogue |
|-------------------|-------------------------|
| `--max-depth`, `--max-calls`, `--max-global-calls` budget flags | **Validates D009's REQUIRED Budget** — recursion is budget-bounded, not unbounded. fast-rlm ships exactly the guardrails D009 demands. |
| `output_schema` validation on every `FINAL(...)` with retry-on-failure | Mirrors our `VerifiedToolResult` / anti-fancy; schema validation is the RLM analogue of our verification layer. **Case study (research §5):** free-text sub-agent fan-out *fails* on distributed/implicit facts; typed JSON-schema routing *succeeds* — acting as external sparsification. This makes typed sub-Loop contracts a REQUIRED RGLA discipline, not optional. |
| `primary_agent` is REQUIRED (no default model) | Matches our injected-provider discipline (R002 / M038 `LLMRouter` — providers injected, no ambient default). |
| Backend-agnostic (OpenAI-compatible / Vertex / Anthropic / **ACP** `acp:codex`) | Matches our `LLMProviderPort` abstraction; the ACP mode (driving local coding agents read-only) is a future adapter candidate. |
| Tools as ordinary Python callables in the REPL namespace | Aligns with our `ToolRegistry` + `ToolCapability`; tools are functions, not a separate calling API. |
| Structured input: `dict` query → flat schema probe at step 0 | Informs the Context Graph port (§9 Q3): externalised context is presented structurally, not stringified. |

**Engineering caveats (recorded honestly):**
  - The Deno + Pyodide runtime is a **heavy native dependency** (Deno 2+); it
    would live behind an L3 adapter, never in domain/application (R002).
  - fast-rlm's sandbox executes model-written code — a **code-execution trust
    boundary** that our `VerifiedToolResult`/`EvidenceLedger` must still gate;
    RLM does not waive verification (§10.4).
  - It is a single-author, fast-moving reference; adopting it as a runtime
    dependency is **out of scope**. It is studied for patterns, not vendored.

**Net effect on decisions:** fast-rlm *strengthens* D009 (Budget guardrails
exist in practice) and D011 (verification is not relaxed) without changing
them. It sharpens the Context Graph port shape (§9 Q3) and adds ACP-mode as a
future adapter candidate — both are follow-ups, not blockers.
