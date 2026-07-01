# active-skill-system

> A typed-skill / cognitive-runtime framework that observes its own behaviour,
> accumulates permanent improvements, and evolves its skills from real data.
> **Work in progress — reactive runtime production-ready.**

`active-skill-system` synthesizes three threads:

1. **A disciplined hexagonal/onion core** — domain and application layers fully
   isolated from infrastructure, enforced structurally (import-linter, not by
   convention). 13 swap-able ports.
2. **A generic evolution engine** — mutates, evaluates, and promotes tunable
   artefacts (genomes) against a baseline, proven across 5 heterogeneous
   domain profiles with per-domain primary fitness axes.
3. **RGLA (Recursive Graph Loop Architecture) + reactive runtime** — `Loop` as
   the event-sourced unit of work, `LoopGraph` typed provenance, a reactive
   runtime absorbing all 12 activegraph primitives, fork-and-diff with zero-cost
   cache replay, and a self-governing dogfood loop.

## Why

The interesting problem is not "an agent that writes code" — it is a system that
**observes its own behaviour, accumulates permanent improvements, and evolves
its skills from real data**. This project builds the substrate for that: loops
with budgets, typed provenance, verifiable evolution, a reactive runtime that
fires behaviors automatically on events/graph-changes, and a dogfood path
(D012/D013) where the framework measures itself.

## What's here

- **Layered core** (`src/active_skill_system/{domain,application,adapters,composition}`)
  — import-linter-enforced inward-only dependencies (R001/R002/R007). 13 ports.
- **Evolution engine** — `EvolutionEngine` / `MultiEvolvableEngine` /
  `WeightedFitnessAggregator`; 5 evolvable genomes (Model, Prompt, Transformation,
  SQL, IaC) with per-domain primary fitness axes; per-stage transformation selectors.
- **RGLA** — `domain/loop.py` (Loop + LoopFSM + **REQUIRED Budget** — unbounded
  loops are a contract violation), `domain/runtime/fsm.py` (RunFSM, 16-state
  cognitive lifecycle), `domain/loop_graph.py` (typed RUNTIME vs PROVENANCE edges
  + `project()`), GraphBackend port (LadybugBackend adapter).
- **Reactive runtime (Waves B/C/D)** — BehaviorRuntime (event/pattern/relation
  triggers), PatchApplier (propose→approve→apply), PolicyGate (4 rules),
  PatternMatcher (graph-shape subscriptions), ReplayEngine (strict/permissive),
  ReactiveFrame + FrameBudget, ReactiveSandboxAgentRunner (reactive during REAL
  runs), Diligence behavior pack (evidence_linker, question_generator, risk_assessor).
- **Fork-and-diff** — ForkEngine + AsyncForkEngine (asyncio.gather concurrent
  fork), ForkReplayCacheEngine (fork + replay + LLMCache = zero-cost prefix),
  ForkAnalysis (explains WHY forks diverge at reactive level).
- **Observability** — EventStore + EventLogBackend (audit trail), TraceCollector
  (distributed trace spans with causality), TrajectoryRecorder (8 step kinds),
  structured loguru logging, typed domain errors.
- **Resilient LLM routing** — `LLMRouter` (cost-aware multi-provider selection
  + retry + exponential backoff + fallback); `RouterBackedReasoningEngine`
  (M038 gap closed); `MiniMaxProvider` with per-call retry floor.
- **Real instruments** — `SQLRealTool` drives fitness from real SQLite
  `EXPLAIN QUERY PLAN` (not synthetic formulae).
- **Self-governance** — `--governance-check` (8 axes: layering, ruff, ty,
  pyrefly, riskratchet, GitNexus convention, pytest, AST docstrings). GSD
  PreVerify hook gates milestone verification automatically. Recursive dogfooding.
- **Harness + skills** — thin `harness/`, append-only `ratchet/` ledger,
  agent-loadable fat-skills (`.agents/skills/*`), `ruvector/` offline container.

## Status

54 milestones, 1838 offline tests (real-LLM gated subset), 0 regressions,
layering KEPT, governance 100%. Architecture decisions D001–D021 recorded in
`.gsd/DECISIONS.md`. All 12 activegraph primitives absorbed.

## Direction

| Track | What | State |
|-------|------|-------|
| **MINI** | Isolated sandbox: one feature-slice benchmark across multiple models → fitness + LoopGraph + ratchet | ✅ built |
| **Reactive (Waves B/C/D)** | Reactive runtime: events trigger behaviors, patches gated by policies, fork-and-diff with cache replay | ✅ production-ready |
| **MAXI (D013)** | A comprehensive SDLC harness (project-own GSD-equivalent), grown from mini experience | ⏭️ Wave E (next) |

## Run

```bash
uv sync
uv run pytest -q                      # offline suite (deterministic)
uv run pytest --runllm -q             # + real-LLM gated tests (needs gateway creds)
uv run lint-imports                   # layering contracts (R001/R002/R007)
uv run ruff check                     # lint
uv run python -m active_skill_system.composition.mini_sandbox --governance-check  # self-validation
uv run python -m active_skill_system.composition.mini_sandbox --behavior-demo     # reactive demo
uv run python -m active_skill_system.composition.mini_sandbox --model minimax/MiniMax-M3  # sandbox run
uv run python -m active_skill_system.composition.sql_evolution --real --emit-runlog
```

## Architecture at a Glance

```
L1 domain/          pure types + invariants (stdlib only): Loop, GraphEvent,
                    Behavior, Relation, Pattern, Patch, Fork, Diff, ReactiveFrame,
                    RunFSM (16 states), LoopFSM (6 states), 5 genomes
L2 application/     use cases + 13 ports (Protocol interfaces)
L3 adapters/        infra: LadybugBackend, MiniMax, DSPy, FastRLM, SQLite,
                    reactive runtimes (InMemory/Pattern/Relation/EventEmitting)
L4 composition/     CLI wiring, lazy imports, GSD hooks, reactive stack builder
```

**13 ports (all swap-able):** LLMProvider, ReasoningEngine, CodeExecutor,
GraphStore, GraphBackend, EventStore, EventLogBackend, LLMCache, TraceCollector,
ForkEngine, ReplayEngine, BehaviorRuntime, PatchApplier. Adding HelixDB instead
of LadybugDB = one adapter file. Adding Postgres for event log = one adapter file.

## Documentation

- `doc/architecture.md` — Unified Runtime architecture
- `doc/architecture-proposal-absorb-activegraph.md` — 3-wave activegraph absorption plan
- `doc/trace-observability-design.md` — Distributed tracing design (D020)
- `doc/rgla.md` — RGLA design (D009) + RLM integration (D011)
- `doc/dogfood.md` — dogfooding stance (D012, sandbox-observer)
- `.gsd/DECISIONS.md` — D001–D021 architecture decisions
- `.gsd/REQUIREMENTS.md` — capability contract (R001–R018)
- `.gsd/PROJECT.md` — current-state inventory + roadmap

## License

Apache-2.0 (see `ruvector/`; project code follows the same terms).
