# Architecture Review & Practical-Use Verification

Critical review of `doc/architecture.md` (M001-pgyf3y) and a walk-through of
practical usage scenarios. Written from the code/README reality of
`github.com/yoheinakajima/activegraph` (`27c2901b`), not from the spec alone.

## Overall verdict

**Sound and unusually well-grounded for a research/architecture spec — but its
ambition outruns what any first build can deliver.** The substrate choice is
excellent (ActiveGraph is purpose-built for exactly this). The composition
(Cognitive Runtime as top-level, Active Skill System inside it) is coherent
and resolves the idea↔concept tension cleanly. The honest risks are **scope,
two under-specified seams, and "research-grade" claims presented as design** —
not architectural incoherence.

## 1. Substrate fit — strong (verified against README + code)

ActiveGraph's own README describes it verbatim as:

> "An event-sourced reactive graph runtime for long-running, auditable,
> agentic systems. ... Every run is resumable, forkable, and diff-able from
> its event log." — and "Cache replay means the shared prefix doesn't
> re-execute (no new LLM calls)."

That is **precisely** the substrate the spec needs (event log = history §7.1
C7/C14; projection §C8; replay-determinism §C13; fork/diff §C10/C16). The
tagline *"The graph is the world. Behaviors are physics. The trace is the
proof"* even rhymes with the spec's "trace is the audit trail / event log is
execution history." This is not a forced fit — it is the framework's stated
purpose. ✅ This is the single biggest strength and it is real.

## 2. Strengths

1. **Substrate is purpose-matched** (above).
2. **Coherent center of gravity.** "Cognitive Runtime = control plane, Active
   Skill System = typed subsystem" cleanly reconciles idea.md (skills) and
   concept.md (runtime) without one subordinating the other awkwardly.
3. **Discipline about reality.** S01's mismatches are honored, not papered
   over: C11 (frames≠reconverge) dropped; C1/C4 (composition-root) and C15
   (fork-for-experiments) recorded as *project rules* wired to the real
   `PendingApproval` primitive.
4. **Genuine auditability.** Event log + provenance + replay-cache + fork/diff
   give real traceability and "what actually happened" — not just logging.

## 3. Risks and weaknesses (prioritized)

### R1 — The Task Graph ↔ ActiveGraph mapping is the crux, and it is under-specified. (HIGH)
ActiveGraph's graph is the **agent's world** (object/relation types mutated by
behaviors). The Cognitive Runtime's **Task Graph** is a *reasoning* structure
(Goal / Fact / Evidence / Constraint / Hypothesis / Gap / Mechanism). The spec
says "the adapter pack maps domain events ↔ ActiveGraph events" — but *how*
the reasoning graph is represented as ActiveGraph object types + behaviors is
left to the adapter. **This is the make-or-break technical decision and it is
not made.** Recommend: prototype this mapping (object types for the Task-Graph
node kinds + the behaviors that propose/validate/evidence them) before building
the full reasoning layer.

### R2 — "Determinism/reproducibility" is record-replay, not formal determinism. (MED)
The system is LLM-driven. Replay works by **serving cached LLM outputs**
(`LLMCache.from_events`); a fork **falls through on prompt divergence** and
re-calls the provider. So reproducibility = "replay the same cached
trajectory," and fork = "shared prefix + re-computed divergent tail." That is
genuinely useful (audit, branching experiments) but it is **not** "the same
inputs ⇒ the same outputs from first principles." A fork needing new LLM calls
is non-deterministic by definition. The spec's §8.4 "Reproducibility" should
be qualified to **replayable-from-log**, not stated as if it were formal.

### R3 — "Reachability/proof" is pragmatic gating, not verification. (MED)
concept.md §6 reachability ("valid path from accepted facts to goal, every
transition uses a known mechanism") reads like automated theorem-proving. In
reality the **LLM proposes** the mechanisms and populates the graph; the only
thing enforcing rigor is the validator pipeline + anti-fantasy gating
(provenance / deterministic computation / registered rule / explicit
hypothesis). That is a strong *pragmatic* guard, but the spec should not be
read as formal verification — its ceiling is "no unsupported factual claim
ships," not "the conclusion is proven true."

### R4 — The Output Verifier is the trust keystone; its own nature is unspecified. (MED)
The whole anti-fantasy guarantee rests on an **independent** mechanism
promoting PROPOSED→VERIFIED. If the Output Verifier is itself LLM-based, the
guarantee weakens to "one LLM checks another." The spec should pin down which
verifiers are **deterministic** (schema, citation-coverage, type, replay-hash)
vs **LLM-judge** (semantic), and require at least one deterministic gate on
every factual claim.

### R5 — Adapter "interchangeability" is overstated. (LOW-MED)
"ActiveGraph is just an adapter" understates that the **entire execution
model** (event log, projection, replay, fork, behaviors) *is* ActiveGraph.
Port-ifying it (`EventJournalPort`, `ExperimentWorkspacePort`) is good
hygiene, but swapping ActiveGraph out later would be a **rewrite of the
execution core**, not an adapter swap. Treat it as a strategic dependency,
not a pluggable one.

### R6 — Behavioral discipline is hard to maintain at scale. (LOW-MED)
"Behaviors must be deterministic, no direct I/O, effects as EffectIntent" is a
strict discipline across many packs. Real drift risk (an HTTP call inside a
behavior silently breaks replay). The framework's cache-divergence detection
catches it *at replay time*, not at authoring time — add a dependency/I/O lint
for behaviors, or a "pure behavior" decorator that fails fast on side effects.

### R7 — Cost/latency of the full cognitive pipeline. (LOW)
Task Graph → validate → repair loop → plan → execute → synthesize → verify is
many LLM calls per "complex" request. The Complexity Router (concept.md §17)
mitigates by short-circuiting simple tasks to a direct path — good — but the
router is itself a heuristic; misroutes either overspend or under-process.

## 4. Practical usage scenarios (feasibility walk-through)

### A. Research answer with citations (concept.md MVP target) — ✅ REALISTIC
Task Graph of Claim/Evidence nodes; RAG fills evidence; "reachability" can
start as **provenance coverage** ("every factual claim has an evidence node
with a source") rather than full proof search; Output Verifier checks citation
coverage. ActiveGraph event log gives full audit. **Best first vertical slice.**

### B. Cross-environment skill (browser → API) via ExpressionProfile — ⚠️ ASPIRATIONAL
The flagship differentiator and **the most ambitious** piece. Needs
`ContextSignature` (typed attributed graph pattern) for each environment, slot
binding, grounding via typed-subgraph/CSP/ILP matching (idea.md §10.3). This is
research-grade; **not in a first build.** A thin version (hand-authored
profiles per environment) is feasible earlier; full cross-modal transfer is
M5+.

### C. Approved automated operation ("create a GitHub issue") — ✅ REALISTIC & WELL-SUPPORTED
Direct or short cognitive path; external change → `EffectIntent`; irreversible
op → `PendingApproval` (verified C15) → human approves → sandbox execute.
Grounded in real primitives (C14 effect/approval, ActiveGraph behaviors). **A
strong, concrete scenario** — pair with A as the two first demos.

### D. Skill evolution / self-improvement — ✅ SOUND DESIGN, FAR OUT
Correctly forbids online self-change (concept.md §12 forbidden loop);
evolution is offline (mutation → held-out eval → promotion gate). The design
is sound, but it is P2/research and depends on a mature Experience Store +
evaluation dataset that do not exist yet.

## 5. Recommendation — de-risk the seam first

1. **Prototype R1 (the mapping)** before broad build: define ActiveGraph
   object/relation types for Task-Graph node kinds + the propose/validate/
   evidence behaviors, and run scenario A end-to-end on real ActiveGraph.
   This validates the load-bearing assumption cheaply.
2. **Qualify the language**: restate "determinism/reproducibility" as
   replayable-from-log (R2) and "reachability" as pragmatic provenance-gating
   (R3) — in the spec itself, so downstream implementers don't over-trust.
3. **Pin the verifier taxonomy** (R4): one deterministic gate per factual
   claim minimum.
4. **First vertical slice = scenario A + C** on a thin M0 (TaskSpec + FSM +
   event log via ActiveGraph + router + budgets); defer B/D.

## 6. Fact-check notes (spec ↔ reality)

- All §7.1 source locations re-verified against the live clone `27c2901b` and
  the GitNexus index (see `doc/architecture-coverage.md` + earlier fact-check;
  line ranges are gitnexus-authoritative, source `class` lines are ±1 due to
  decorators).
- ActiveGraph "resumable/forkable/diff-able / cache-replay / byte-deterministic
  fixtures" quoted verbatim from its README (lines 1-70) — the substrate claims
  are real, not inferred.
- No claim in the spec was found to contradict its source; the risks above are
  about **ambition/under-specification**, not factual error.
