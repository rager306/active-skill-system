# ActiveGraph Claim Verification (M001-pgyf3y / S01)

> **Re-verified 2026-06-23 against the fresh index** — repo re-cloned to
> `github.com/yoheinakajima/activegraph` **lastCommit `27c2901b`** (2026-06-10;
> was `f3ed033`, 2026-05-19) and re-indexed via GitNexus (4936 nodes / 9544
> edges / 300 flows). All structural verdicts (C2,C3,C5,C6,C7,C8,C9,C10,C12,
> C13,C14,C16) hold unchanged; `Runtime.fork` line range shifted
> 2169-2285 → **2338-2472** (Runtime grew ~187 lines). The only material
> change is **C15**: a new `PendingApproval` symbol now provides framework
> grounding for the "approval/governance" rule (see below). C11 stays REFUTED.

Working research file. Each claim is a **falsifiable statement about the real
ActiveGraph implementation** (`/root/vendor-source/activegraph`,
github.com/yoheinakajima/activegraph), inherited from `doc/idea.md` and
`doc/concept.md`. Verdicts (T02-T04) cite concrete activegraph source
locations (file:line or symbol) gathered via GitNexus.

## Claim catalog

> Source pointer format: `doc` `section` / `[ref]`. `idea.md` carries the
> ActiveGraph-specific claims; `concept.md` describes the *to-be-built*
> Cognitive Runtime and contributes little ActiveGraph-specific claims.

### pack / adapter / composition-root

- **C1** — ActiveGraph **pack is an external composition root and transport
  adapter**, not the place where SkillGenome business logic lives.
  *(idea.md, "Краткий вывод": "ActiveGraph pack должен быть внешним
  composition root и транспортным адаптером...")*
- **C2** — An ActiveGraph **pack is a Python package** that includes
  object/relation types, behaviors, tools, prompts, and policies.
  *(idea.md, "Кратский вывод" [1]; §16 rule 1)*
- **C3** — A pack is a **deployable capability**, not an onion-architecture
  layer; packs are split by bounded context / trust boundary / deployment
  profile / optional capability / owner.
  *(idea.md, §2 "Pack не является архитектурным слоем")*
- **C4** — ActiveGraph packs sit in the **"driving adapters and composition
  roots" layer (L4)** of the hexagonal layout.
  *(idea.md, §1 diagram L4)*

### event

- **C5** — **Behaviors subscribe to events** and create new events or graph
  changes.
  *(idea.md, "Краткий вывод"; §4.1)*
- **C6** — Event-driven inbound flow: ActiveGraph event → behavior →
  application use case → domain events → behavior emits an integration event
  back onto the graph.
  *(idea.md, §4.1 sequence diagram)*
- **C7** — The **event log is the durable execution history** of the system.
  *(idea.md, §4.3 rule list; §16 rule 4)*

### read-model

- **C8** — The ActiveGraph graph is best treated as a **projection / read
  model / reactive workspace**, not the single representation of domain
  aggregates.
  *(idea.md, §4.3)*
- **C9** — An ActiveGraph object's **Pydantic schema validates data shape**
  (boundary validation / read models) but must not replace the domain model
  and its invariants; pack version, prompts and settings participate in the
  replay contract.
  *(idea.md, §4.3 [5])*

### workspace

- **C10** — ActiveGraph realizes **ExperimentWorkspacePort** through a
  fork/diff API.
  *(idea.md, §4.2; §"Итоговая рекомендация"; §5.3 adapter table)*
- **C11** — ActiveGraph offers **"frames" for short-lived branches that
  reconverge** and **"forks" for persistent, independently compared
  variants**.
  *(idea.md, §4.2 [4])*

### behavior

- **C12** — **Behaviors are thin inbound adapters**: deserialize → call use
  case → serialize; they must contain no skill search, promotion decisions,
  type checking, grounding logic, direct HTTP, or evolution heuristics.
  *(idea.md, §4.1; §16 rule 3, 5)*

### replay

- **C13** — ActiveGraph **requires deterministic behavior bodies**; external
  I/O must go through controlled runtime primitives, otherwise replay and fork
  stop being reproducible.
  *(idea.md, §4.1 [3])*
- **C14** — ActiveGraph is explicitly built as an **append-only event log with
  a graph projection and fork/diff on top of it**.
  *(idea.md, §16 rule 4 [7])*

### fork

- **C15** — **Fork applies to experiments**, not to core business logic.
  *(idea.md, §16 rule 10)*
- **C16** — A fork's **common prefix is reconstructed from the saved event log
  and cache**, with independent execution starting after the branch point.
  *(idea.md, §4.2)*

<!-- Verdict sections (T02-T04) and the verdict matrix (T05) are appended below. -->

## Verdicts: pack / adapter / composition-root

Grounded via GitNexus against `activegraph` (github.com/yoheinakajima/activegraph;
re-verified at lastCommit `27c2901b`; first pass was on `f3ed033`). GitNexus
`query`/`context` as the primary instrument; direct source reads only to pin
exact lines for the decisive symbols.

- **C2 — verified (exact).** A pack is a real, schema-validated bundle. Class
  `Pack` (`activegraph/packs/__init__.py:530-621`) is a `@dataclass(frozen=True)`
  with exactly the fields idea.md claims: `name, version, description,
  object_types, relation_types, behaviors, tools, policies, prompts,
  settings_schema`. `__post_init__` enforces within-pack uniqueness and type
  checks (behaviors must be `Behavior`/`RelationBehavior`, tools must be `Tool`).
  A concrete pack exists: `activegraph/packs/diligence/` ships
  `object_types.py`, `behaviors.py`, `tools.py`, `__init__.py`.
- **C3 — verified.** A pack is a deployable capability, not an architecture
  layer. Packs are loaded at runtime (`activegraph/packs/loader.py`:
  `PackRuntimeState` L311-336, `_build_pack_loaded_payload` L688-700,
  `load_pack`); loading is idempotent on `(name, version)` and emits a
  `pack.loaded` event. The `diligence` pack demonstrates capability-based
  separation (its own object/relation types, behaviors, tools).
- **C1 — partial (design-load-bearing, not framework-intrinsic).** The code
  confirms a pack *bundles* behaviors/tools/types (so it can host an inbound/
  outbound adapter surface), but "pack must be an external composition root /
  transport adapter and NOT the home for SkillGenome business logic" is a
  project-level design constraint, not a property the framework enforces. The
  framework permits arbitrary logic inside a behavior body; the discipline
  ("thin behaviors, domain lives elsewhere") is the skill-system's choice.
  → S02 must state C1 as an imposed rule, not as an activegraph guarantee.
- **C4 — partial (same reason as C1).** activegraph packs can occupy a
  "driving adapter / composition root" role (behaviors receive events and
  emit graph changes; see `@behavior(on=[...])` in
  `activegraph/behaviors/decorators.py:145-190`, signature `(event, graph, ctx)
  -> None` per CONTRACT #6), but the framework does not name or enforce an
  "L4 composition-root layer". That layering is the skill-system's hexagonal
  decision projected onto activegraph.

**Cluster summary:** the *structural* pack claims (C2, C3) are fully verified
in code; the *role* claims (C1, C4) are design intentions the framework
enables but does not enforce — S02 must record them as project rules.

## Verdicts: event / read-model / workspace

- **C5 — verified.** Behaviors subscribe to events and create new events or
  graph changes. `@behavior(on=[...], creates=[...])` in
  `activegraph/behaviors/decorators.py:145-190`; `creates=` lists the event/
  object types a behavior may emit/create.
- **C6 — verified.** Event-driven inbound flow with the exact idea.md
  signature. `CONTRACT #6` (decorators.py docstring): regular behavior
  signature is `(event, graph, ctx) -> None`; `@llm_behavior` is
  `(event, graph, ctx, llm_output) -> None`.
- **C7 — verified (exact).** The event log is the durable execution history.
  `activegraph/store/base.py`: `EventStore` is documented as an "Append-only
  per-run event log. CONTRACT v0.5 #2" (append / iter_events / count /
  truncate_after). `RunRecord` is the canonical runs-table row.
- **C8 — verified.** The graph is a projection/read model rebuilt from the
  event log. `store/base.py:replay_into` "Apply a stream of events to a Graph
  without firing listeners ... used by `Runtime.load` and `Runtime.fork`" —
  i.e. the graph is a materialized projection of the append-only log, not the
  source of truth. Behaviors react to events (reactive workspace).
- **C9 — verified.** Pydantic validates pack/object shape, and pack version /
  prompts / settings participate in the replay contract. `Pack.settings_schema`
  must be a Pydantic `BaseModel` subclass (`packs/__init__.py:__post_init__`);
  `Pack.prompt_manifest()` returns per-prompt `{version, hash}` ("CONTRACT
  v0.9 #10"); `runtime/errors.py:ReplayDivergenceError` +
  `_prompt_hash_message` enforce prompt/version divergence on replay.
- **C10 — verified (primitives exist).** activegraph exposes a fork/diff API
  the skill-system can adapt into `ExperimentWorkspacePort`: `Runtime.fork`,
  `activegraph/runtime/diff.py:Diff` (L60-76), `cli/main.py:cmd_diff`, and
  `RunRecord(parent_run_id, forked_at_event_id)`. The port *interface* itself
  is a skill-system abstraction; activegraph supplies fork/diff primitives.
- **C11 — REFUTED (important mismatch).** idea.md [4] claims activegraph offers
  *"frames for short-lived branches that reconverge"* and *"forks for
  persistent variants"*. In code, `fork` is the branching mechanism
  (parent_run_id + forked_at_event_id), but `activegraph/frame.py:class Frame`
  is **"Mission context for a run"** (goal, id, constraints, success_criteria,
  permissions) — a task-context object, NOT a reconverging execution branch.
  The "frames reconverge" capability does not exist in activegraph.
  → S02 must NOT rely on activegraph "frames" for branch reconvergence; treat
  `fork` as the only branching primitive and `Frame` as run mission context.

**Cluster summary:** event (C5-C7) and read-model/projection (C8-C9) claims
are fully verified; fork/diff primitives exist (C10); the frames-vs-forks
reconvergence claim (C11) is refuted — a real doc/code mismatch S02 must honor.

## Verdicts: behavior / replay / fork

- **C12 — verified.** Behaviors are thin inbound adapters. `@behavior`/
  `@relation_behavior`/`@llm_behavior` (`activegraph/behaviors/decorators.py`)
  bind a function to events with signature `(event, graph, ctx) -> None`
  (CONTRACT #6) / `(event, graph, ctx, llm_output) -> None` for LLM behaviors.
  The decorator only wires `on=/where=/creates=`; the handler body is the
  user's code, so "thin" is a convention the framework encourages (and the
  pack validation requires `@behavior` to come from `activegraph.packs`).
- **C13 — verified (exact).** activegraph demands determinism and makes
  external I/O replay-able through controlled caches. `Runtime.fork` and
  `Runtime.load` rebuild state via `Graph._replay_event`;
  `activegraph/llm/cache.py:LLMCache.from_events` and
  `activegraph/tools/cache.py:ToolCache.from_events` serve LLM/tool results
  from the event log on replay; `runtime/errors.py:ReplayDivergenceError`
  (extends `errors.py:ReplayError`) with `_prompt_hash_message`/
  `_type_message`/`_length_message` aborts replay on divergence.
  `core/ids.py:IDGen.reseed_from_events` makes IDs deterministic.
  Tests: `test_tool_replay.py` (deterministic vs non-deterministic cache),
  `test_fork_with_cache_falls_through_on_prompt_divergence`.
- **C14 — verified (exact).** Append-only event log + graph projection +
  fork/diff on top. `store/base.py:EventStore` = "Append-only per-run event
  log"; `replay_into`/`_replay_event` rebuild the graph from the log; fork
  and diff operate over runs (`runtime/diff.py:Diff/compute_diff`,
  `store/sqlite.py:SQLiteEventStore.fork_run`, `store/postgres.py:fork_run`).
- **C15 — partial, now with framework grounding (re-verified `27c2901`).**
  activegraph provides fork and the examples use it for alternative hypotheses
  (`examples/diligence_real_run.py:step_3_fork_alt_thesis`,
  `resume_and_fork.py:step_3_fork`), consistent with "fork for experiments".
  `test_parent_is_untouched_by_fork` shows forks are isolated from their
  parent. NEW: a `PendingApproval` class now exists
  (`activegraph/packs/__init__.py:957-971`; fields id/kind/object_type/data/
  reason/pack; imported by runtime, loader, the diligence pack) — an approval
  primitive the runtime surfaces. This means the "approval/governance" intent
  behind C15 is no longer purely a project invention; activegraph now supplies
  a hook for it. The narrower claim "fork must be restricted to experiments
  and never core business logic" is still a project governance rule (the
  framework does not forbid forking any run), so C15 stays partial — but S02
  can ground the rule on `PendingApproval` rather than asserting it from
  nothing.
- **C16 — verified (exact).** A fork reconstructs the shared prefix from the
  saved event log and caches, then diverges. `Runtime.fork`
  (`runtime/runtime.py:2338-2472` on `27c2901`; was 2169-2285 on `f3ed033`)
  calls `SQLiteEventStore.fork_run` +
  `iter_events` (copy parent prefix), `Graph._replay_event`/`attach_store`
  (rebuild projection), `LLMCache.from_events` + `ToolCache.from_events`
  (restore caches from the log), then `_requeue_unfired` (independent
  execution after the branch point). `RunRecord(parent_run_id,
  forked_at_event_id)` records the branch point. Tests:
  `test_fork_creates_new_run_with_copied_events`,
  `test_fork_preserves_id_counters_then_diverges`,
  `test_fork_runs_independently_and_is_persisted`,
  `test_diff_partition_of_events_after_divergence`.

**Cluster summary:** behavior (C12), replay determinism (C13), event-log+
projection (C14), and fork prefix-reconstruction (C16) are all verified in
code; "fork is for experiments only" (C15) is a design rule the framework
permits but does not enforce.

## Verdict matrix

| Claim | Category | Verdict | Key activegraph source |
|-------|----------|---------|------------------------|
| C1 | pack/adapter/composition-root | partial (design rule) | Pack bundles behaviors/tools/types (packs/__init__.py:530-621); role not enforced |
| C2 | pack/adapter/composition-root | verified | `Pack` class fields (packs/__init__.py:530-621); diligence pack |
| C3 | pack/adapter/composition-root | verified | runtime loading (packs/loader.py:PackRuntimeState/load_pack); diligence pack |
| C4 | pack/adapter/composition-root | partial (design role) | `@behavior(on=)` enables adapter role (behaviors/decorators.py:145-190); L4 layering is the project's |
| C5 | event | verified | `@behavior(on=,creates=)` (behaviors/decorators.py:145-190) |
| C6 | event | verified | CONTRACT #6 signature `(event,graph,ctx)` (behaviors/decorators.py) |
| C7 | event | verified | `EventStore` = append-only per-run log (store/base.py) |
| C8 | read-model | verified | `replay_into` rebuilds graph from log (store/base.py); used by load/fork |
| C9 | read-model | verified | `settings_schema` BaseModel; `prompt_manifest` hashes; ReplayDivergenceError |
| C10 | workspace | verified (primitives) | `Runtime.fork`, `runtime/diff.py:Diff`, RunRecord(parent,forked_at) |
| C11 | workspace | REFUTED | `Frame` (frame.py) = mission context, NOT a reconverging branch |
| C12 | behavior | verified | `@behavior` thin inbound adapter, signature `(event,graph,ctx)` |
| C13 | replay | verified | LLMCache/ToolCache `from_events`; ReplayDivergenceError; IDGen.reseed_from_events |
| C14 | replay | verified | `EventStore` append-only + `_replay_event` projection + fork/diff |
| C15 | fork | partial (now framework-grounded) | fork isolated (test_parent_is_untouched_by_fork); NEW `PendingApproval` (packs/__init__.py:957-971) provides an approval primitive; still not restricted to experiments |
| C16 | fork | verified | `Runtime.fork` (runtime.py:2338-2472 on 27c2901): fork_run+iter_events, _replay_event, caches.from_events, _requeue_unfired |

## Unverified claims

Items the S02 synthesis MUST flag — not silently carried as assumptions:

1. **C1 / C4 — composition-root role is a project rule, not an activegraph guarantee.**
   The framework bundles behaviors/tools/object-types in a pack and lets a
   behavior act as an event-driven inbound adapter, but it does not enforce
   "pack = external composition root; no business logic in behaviors".
   S02 must state this as an imposed architectural rule.
2. **C11 — REFUTED: activegraph `Frame` is not a reconverging branch.**
   `activegraph/frame.py:Frame` is mission context (goal/constraints/
   success_criteria/permissions). There is NO "frame reconverge" mechanism.
   `fork` is the only branching primitive. S02 must drop the
   frames-vs-forks reconvergence claim and treat fork as the sole branch
   mechanism (with diff for comparison).
3. **C15 — "fork for experiments only" is a governance rule (now partly grounded).**
   activegraph isolates forks from their parent but does not prevent forking
   core runs. As of `27c2901`, a `PendingApproval` primitive exists
   (`packs/__init__.py:957-971`), so the approval/governance intent has a
   framework hook to attach to. S02 should still encode "fork for
   experiments only" as a Governance/Evolution constraint, but can wire it
   through `PendingApproval` rather than asserting it from nothing.

Everything else (C2, C3, C5-C10, C12-C14, C16) is verified against the real
activegraph source (github.com/yoheinakajima/activegraph, re-verified at
lastCommit `27c2901b` 2026-06-10; was `f3ed033` 2026-05-19) and can be used
as firm inputs to the synthesis.
