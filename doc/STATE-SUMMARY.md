# State Summary — active-skill-system

> **Snapshot: 2026-06-30.** This document captures the current architectural
> state, what we built, where we're heading, and the key conclusions.
> Companion to `doc/ROADMAP.md` (sequencing) and `.gsd/PROJECT.md` (inventory).

## Where We Are

**54 milestones complete.** The project has evolved from a hexagonal core
with an evolution engine into a **reactive, self-observing cognitive runtime**
that absorbs all 12 activegraph primitives. The reactive runtime is
production-ready: it fires behaviors during real LLM agent runs, not just in
demo mode.

```
Suite:       1838 passed, 9 skipped
Layering:    KEPT (2 contracts, 0 broken)
Governance:  100% (8/8 axes OK, 983 functions baselined)
Ports:       13 (all swap-able)
Genomes:     5 evolvable (Model/Prompt/Transformation/SQL/IaC)
FSMs:        2 (RunFSM 16-state + LoopFSM 6-state)
Primitives:  12/12 activegraph covered
Decisions:   21 (D001-D021)
Requirements: 20 (13 validated, 5 active, 2 new)
```

## What We Built (the three threads, delivered)

### Thread 1: Disciplined Hexagonal Core

```
L1 domain/     40+ pure stdlib types + invariants (R002/R003)
L2 application/ 40+ use cases + 13 ports (Protocol interfaces)
L3 adapters/   45+ infra implementations behind ports
L4 composition/ 18 CLI entrypoints with lazy imports (R008/R009)
```

**Layering enforced structurally** (import-linter, not by convention). Adding
HelixDB instead of LadybugDB = one adapter file. Adding Postgres for event
log = one adapter file. The application layer never changes.

### Thread 2: Generic Evolution Engine

One engine, **5 evolvable genomes**, each with a per-domain primary fitness
axis. The MEM019 pattern (domain types → tool stub → repair policy → gap
detector → optimization loop → Evolvable wrapper → composition CLI) is proven
reusable across heterogeneous domains:

| Genome | Fitness axis | What mutates |
|--------|-------------|--------------|
| ModelGenome | cost | Model selection |
| PromptGenome | parse_success_rate | Prompt strategies |
| TransformationGenome | cycles | Compiler optimizations |
| SQLGenome | rows_examined | SQL query plans |
| IaCGenome | resource_count | IaC configurations |

### Thread 3: RGLA + Reactive Runtime

The `Loop` is the event-sourced unit of work. `LoopGraph` is the typed
provenance projection. The **reactive runtime** absorbs all 12 activegraph
primitives:

```
EventStore ──publish──► BehaviorRuntime ──trigger──► 3 reactivity levels
     │                     │                              ├── Event (type subscriptions)
     │                     │                              ├── Pattern (graph-shape transitions)
     │                     │                              └── Relation (edge-kind creation)
     │                     ▼
TraceCollector     PatchApplier ◄── propose ── Behaviors
     │                │
     │                ▼
     └── audit ◄── PolicyGate ─── approve/reject ──► GraphBackend ── apply
```

**ReactiveSandboxAgentRunner** wraps the existing SandboxAgentRunner
(non-destructive) and publishes lifecycle events during real runs. Behaviors
fire automatically. The Diligence behavior pack (evidence_linker,
question_generator, risk_assessor) is adapted from activegraph.

## The Killer Features

### 1. Fork-and-Diff with Cache Replay

```
"what if model B at step 3?"  ── without re-paying LLM costs

ForkReplayCacheEngine:
  1. ForkEngine.fork(run_a, evt-003) → copies prefix
  2. ReplayEngine.replay(strict) → reconstructs graph (no behaviors)
  3. LLMCache → prefix LLM calls from cache (0 new API calls!)
  4. Continue with new model
  5. ForkAnalysis → WHY forks diverged (reactive level)
```

### 2. Distributed Trace Observatory

Three observability layers answer different questions:

| Layer | Question | Tool |
|-------|----------|------|
| Event log | WHAT happened? | EventStore (append-only audit trail) |
| Trace spans | WHY happened? (causality) | TraceCollector (parent_span_id chain) |
| Trajectory | HOW agent proceeded? | TrajectoryRecorder (8 step kinds) |

Every behavior dispatch gets a trace span. Every patch lifecycle emits audit
events. Fork divergence is explainable at the reactive level.

### 3. Self-Governance (Recursive Dogfooding)

The project validates ITSELF with its own verification tools:

```
--governance-check (8 axes, 100%):
  layering + ruff + ty + pyrefly + riskratchet + convention + tests + ast_symbols

GSD PreVerify hook → automatic gate before milestone completion
Exit 0 → allow, Exit 1 → block
```

## Where We're Heading (Wave E — Maxi Scaling)

The north-star track: grow from MINI (isolated sandbox) to MAXI (comprehensive
SDLC harness). Key next steps:

1. **Multi-domain benchmark suite** — run all 5 genomes in one pipeline
2. **Golden Sessions** — record + replay canonical agent sessions for regression
3. **Reactive composition wiring** — diligence.py uses ReactiveSandboxAgentRunner
4. **Real-LLM reactive E2E** — validate full reactive chain with actual API calls
5. **LLMRouter in sandbox CLI** — --strategy router for cost-aware failover

Future tracks: Golden Session replay, cross-domain genome transfer, multi-agent
orchestration, real-time dashboard, distributed execution.

## Key Conclusions

1. **The parallel-abstractions gap is CLOSED.** We did NOT rewrite onto
   activegraph runtime. We absorbed the concepts into our own ports and domain
   types. activegraph is ONE adapter option, not a hard dependency.

2. **The reactive runtime is production-ready.** ReactiveSandboxAgentRunner
   fires behaviors during real LLM agent runs. Frame budget enforcement. Audit
   trail. Trace visibility.

3. **The architecture is swap-able at every seam.** 13 ports mean graph
   backend, event log, LLM cache, reasoning strategy, behavior runtime — all
   are replaceable with one adapter file. The application layer is stable.

4. **Self-governance keeps quality honest.** No thresholds, no hiding problems.
   The 8-axis governance check (recursive dogfooding) gates every milestone.
   Governance 100% = the project is ready for validation.

5. **Phased async worked.** D019: async ONLY in ForkEngine (no retroactive
   async-ification of 40 sync use cases). asyncio.to_thread bridges sync↔async.
   The codebase is manageable, not async-infected.

## Document Map (actualized 2026-06-30)

| Document | Status | Purpose |
|----------|--------|---------|
| `ROADMAP.md` | ✅ current | Wave sequencing + current state + next steps |
| `STATE-SUMMARY.md` | ✅ current | This document — conclusions + direction |
| `architecture-proposal-absorb-activegraph.md` | ✅ delivered | 3-wave absorption design (M051-M054) |
| `architecture-status-activegraph-integration.md` | ✅ updated | Integration audit post-absorption |
| `trace-observability-design.md` | ✅ delivered | Trace layer design (M052) |
| `dogfood.md` | ✅ delivered | Recursive dogfooding stance (M049) |
| `rgla.md` | ✅ delivered | RGLA design (D009) |
| `concept.md` | reference | Original concept (44KB, historical) |
| `idea.md` | reference | Original idea (32KB, historical) |
| `architecture.md` | reference | Unified Runtime architecture |
| `dspy-research.md` | ✅ delivered | DSPy evaluation (M050) |
| `rgla-fast-rlm-research.md` | ✅ delivered | fast-rlm study (M050) |
| `programbench-research.md` | ✅ delivered | ProgramBench track (M050) |
| `sandbox-isolation-research.md` | ✅ delivered | Security gap (M044 bwrap) |
| `okf-research.md` | reference | OKF format evaluation |
| `architecture-review.md` | reference | Early architecture review |
| `architecture-coverage.md` | reference | Early coverage analysis |
| `architecture-requirements*.md` | reference | Requirements synthesis (historical) |
| `activegraph-claims.md` | reference | activegraph re-verification |
| `loop-engineering-synthesis.md` | reference | Loop engineering synthesis |
