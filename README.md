# active-skill-system

> A typed-skill / cognitive-runtime framework evolving toward a self-observing,
> self-improving software-development harness. **Work in progress.**

`active-skill-system` synthesizes three threads:

1. **A disciplined hexagonal/onion core** — domain and application layers fully
   isolated from infrastructure, enforced structurally (not by convention).
2. **A generic evolution engine** — mutates, evaluates, and promotes tunable
   artefacts (genomes) against a baseline, proven across 12 heterogeneous
   domain profiles.
3. **RGLA (Recursive Graph Loop Architecture)** — `Loop` as the event-sourced
   unit of work, `LoopGraph` typed provenance, stored behind a swappable graph
   port. RLM provides the reasoning mechanism; LoopGraph is the durable
   evidence-routing layer.

## Why

The interesting problem is not "an agent that writes code" — it is a system that
**observes its own behaviour, accumulates permanent improvements, and evolves
its skills from real data**. This project builds the substrate for that: loops
with budgets, typed provenance, verifiable evolution, and a dogfood path
(D012/D013) where the framework measures itself.

## What's here

- **Layered core** (`src/active_skill_system/{domain,application,adapters,composition}`)
  — import-linter-enforced inward-only dependencies (R001/R002).
- **Evolution engine** — `EvolutionEngine` / `MultiEvolvableEngine` /
  `WeightedFitnessAggregator`; 10 domain profiles with per-domain primary
  fitness axes; per-stage transformation selectors.
- **RGLA** — `domain/loop.py` (Loop + FSM + **REQUIRED Budget** — unbounded
  loops are a contract violation), `domain/loop_graph.py` (typed RUNTIME vs
  PROVENANCE edges + `project()`), `application/ports/graph_store.py`,
  `adapters/ladybug_graph_store.py` (real Cypher, `:memory:` for tests).
- **Resilient LLM routing** — `LLMRouter` (cost-aware multi-provider selection
  + retry + exponential backoff + fallback); `MiniMaxProvider` with a
  per-call retry floor and `recognizes_model` override.
- **Observability** — loguru-intercepted logging backbone (`LOG_DIR/app.log`),
  typed domain errors, `--emit-runlog` JSONL per evolution run.
- **Real instruments** — `SQLRealTool` drives fitness from real SQLite
  `EXPLAIN QUERY PLAN` (not synthetic formulae).
- **Harness + skills** — thin `harness/`, append-only `ratchet/` ledger,
  agent-loadable fat-skills (`.agents/skills/*`), `ruvector/` offline container.

## Status

41 milestones, 1239 offline tests (7 real-LLM gated), 0 regressions, layering
KEPT. Architecture decisions D001–D014 recorded in `.gsd/DECISIONS.md`.

## Direction

| Track | What | State |
|-------|------|-------|
| **MINI** | Isolated sandbox: one feature-slice benchmark across multiple models → fitness + LoopGraph + ratchet | next build milestone |
| **ProgramBench (D014)** | 1-2 smallest CLI tasks as an external validator (frontier ≈ 0.5% Resolved) | research complete, run pending |
| **MAXI (D013)** | A comprehensive SDLC harness (project-own GSD-equivalent), grown from mini experience | north star, not built directly |

## Run

```bash
uv sync
uv run pytest -q                      # offline suite (deterministic)
uv run pytest --runllm -q             # + real-LLM gated tests (needs gateway creds)
uv run lint-imports                   # layering contracts (R001/R002)
uv run ruff check                     # lint
uv run python -m active_skill_system.composition.sql_evolution --real --emit-runlog
uv run python -m active_skill_system.composition.loop_graph_store
```

## Documentation

- `doc/architecture.md` — Unified Runtime architecture
- `doc/rgla.md` — RGLA design (D009) + RLM integration (D011) + fast-rlm study
- `doc/dogfood.md` — dogfooding stance (D012, sandbox-observer)
- `doc/programbench-research.md` — ProgramBench benchmark track (D014)
- `.gsd/DECISIONS.md` — D001–D014 architecture decisions
- `.gsd/REQUIREMENTS.md` — capability contract (R001–R012)

## License

Apache-2.0 (see `ruvector/`; project code follows the same terms).
