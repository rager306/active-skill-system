# Architecture Coverage & Consistency (M001-pgyf3y / S03)

Traceability + consistency check for `doc/architecture.md` against its sources
(`doc/idea.md`, `doc/concept.md`) and the S01 claim verdicts
(`doc/activegraph-claims.md`, activegraph `27c2901b`).

## Traceability matrix

Legend: `idea §X` = `doc/idea.md` section; `concept F-XX` / `concept §X` =
`doc/concept.md`; `C#` = claim verdict in `doc/activegraph-claims.md`.

### Functional requirements (doc/architecture.md §8.1-§8.2)

| Spec ID | Requirement | Source pointer | Covered |
|---|---|---|---|
| F-01 | accept request/constraints/format/budget | concept F-01 | ✅ |
| F-02 | request → validable TaskSpec | concept F-02 | ✅ |
| F-03 | typed Task Graph (Expression binding target) | concept F-03 + idea §3.2 | ✅ |
| F-04 | version graph changes | concept F-04 | ✅ |
| F-05 | goal reachability | concept F-05 + concept §6 | ✅ |
| F-06 | detect missing evidence/contradiction/constraint violation | concept F-06 | ✅ |
| F-07 | bounded repair loop (measurable-improvement gate) | concept F-07 + concept §7 | ✅ |
| F-08 | plan tool calls only for concrete gaps | concept F-08 | ✅ |
| F-09 | persist provenance of external results | concept F-09 | ✅ |
| F-10 | verify final answer vs goals/constraints | concept F-10 | ✅ |
| F-11 | partial result on budget exhaustion (no fabrication) | concept F-11 | ✅ |
| F-12 | full audit/event log | concept F-12 + **C7/C14** (EventStore) | ✅ |
| F-13 | cancellation + idempotency | concept F-13 | ✅ |
| F-14 | approval for irreversible actions | concept F-14 + **C15** (PendingApproval) | ✅ |
| F-17 | typed Skill Registry (GeneSpec/ExpressionProfile) | idea §3.1-§3.2 + concept F-17 | ✅ |
| F-19 | experience retrieval by task signature | concept F-19 + idea §3.3 | ✅ |
| F-22 | versioning of prompts/policies/ontologies/skills | idea §16.1/§4.3 + concept F-22 + **C9** | ✅ |
| F-23 | offline evolution of skills/repair policies | idea §3.3 + concept §12 + F-23 | ✅ |

> concept.md P0/P1/P2 IDs not surfaced in the spec (e.g. F-15/16/18/20/21/24-28)
> are intentionally out of M001 scope (research/architecture milestone; staged
> development per concept.md §20). Recorded in §"Out of scope" below, not
> silently dropped.

### Architectural rules (doc/architecture.md §8.3)

| Rule | Source pointer | Covered |
|---|---|---|
| 1. packs trusted code; genes/profiles untrusted data | idea §16.1 | ✅ |
| 2. domain knows nothing about ActiveGraph | idea §16.2 + forbidden-deps §5.2 | ✅ |
| 3. behaviors are thin inbound adapters | idea §16.3 + **C5/C6/C12** | ✅ |
| 4. object graph is projection; event log is history | idea §16.4 + **C7/C8/C14** | ✅ |
| 5. no direct I/O in behaviors (replay reproducibility) | idea §16.5 + **C13** | ✅ |
| 6. external change → EffectIntent first | idea §16.6 | ✅ |
| 7. ExpressionProfile = applicability, not authority | idea §16.7 | ✅ |
| 8. BindingInstance local, not published as GeneSpec | idea §16.8 | ✅ |
| 9. new GeneSpec version → new immutable content hash | idea §16.9 | ✅ |
| 10. fork applies to experiments only (governance) | idea §16.10 + **C15** | ✅ |

### Key architectural claims (doc/architecture.md §1/§5/§7)

| Claim | Source pointer | Covered |
|---|---|---|
| Cognitive Runtime = top-level control plane | concept §2 | ✅ |
| Active Skill System = typed skill/expression subsystem | idea §1/§3 | ✅ |
| ActiveGraph = adapter + composition root (role is project rule) | idea "Кратский вывод" + **C1/C4 (partial)** | ✅ |
| Pack bundles object/relation/behaviors/tools/policies/prompts | idea "Кратский вывод" + **C2/C3 (verified)** | ✅ |
| ExperimentWorkspace via fork/diff | idea §4.2/§5.3 + **C10/C16 (verified)** | ✅ |
| Frame is mission context, NOT a reconverging branch | **C11 (REFUTED)** | ✅ |
| Approval/governance grounded on PendingApproval | **C15** | ✅ |

## Contradictions and gaps

Scanned `doc/architecture.md` against idea.md, concept.md, and the S01
verdicts. Findings and resolutions:

### Honored S01 mismatches (no contradiction)

1. **C11 — frames-reconverge dropped.** Spec §7.2 #1 explicitly states Frame is
   mission context and fork is the only branch primitive. No spec section
   relies on reconverging frames. ✅ consistent.
2. **C1/C4 — composition root is a project rule.** Spec §7.2 #2 and §5.2 state
   the role is enforced via dependency tests/review, not a framework guarantee.
   No claim asserts the framework enforces it. ✅ consistent.
3. **C15 — fork-for-experiments governance.** Spec §7.2 #3 and rule 10 wire it
   through PendingApproval rather than asserting it framework-native. ✅ consistent.

### Internal consistency checks

- **Rule 4 (graph = projection) vs any "source of truth" claim:** none. The spec
  consistently treats the event log as history and the graph as a rebuilt
  projection (§5.4, §7.1). ✅ no contradiction.
- **"LLM not an owner of global logic" (§1/§3) vs LLM synthesizer (§6):** the
  LLM synthesizes over a *verified trajectory* and the Output Verifier gates
  it (§6, anti-fantasy §6.2). No self-promotion PROPOSED→VERIFIED. ✅ consistent.
- **F-14 approval vs PendingApproval:** spec grounds F-14 on the new
  PendingApproval primitive (C15) — matches the fresh index. ✅ consistent.

### Gaps found and resolved

- **Gap 1 (minor): concept.md P1/P2 requirements not individually listed.**
  concept.md F-15/16/18/20/21/24-28 (recursive submaps, ontology routing,
  streaming, domain validators, Pareto selection, etc.) are not enumerated in
  §8. **Resolution:** declared out of M001 scope (concept.md §20 staged
  development) — recorded here, not silently dropped. No action for M001.
- **Gap 2 (minor): exact storage stack (PostgreSQL vs graph DB) left open.**
  concept.md §13 says graph DB is added only when load demands it; idea.md says
  no premature stack selection. Spec §2 keeps infra abstract (DB adapter).
  **Resolution:** intentional non-goal of M001 (CONTEXT resolved decision #2 /
  non-goals). ✅ consistent with scope.

### Contradictions found

**None unresolved.** No spec claim contradicts its source, and no S01 verdict
is violated. The two minor gaps are scope decisions, not defects.

## Out of scope (intentional)

concept.md staged-development P1/P2 capabilities not enumerated in
`doc/architecture.md` §8 (recursive submaps F-15, ontology routing F-16,
streaming/visualization F-18, domain validators F-20, Pareto selection F-26,
cross-agent portability F-27, process mining F-28, graph skill composition
F-24, automatic alternative-plan search F-25, cost/latency/risk policies F-21).
Deferred to later milestones per concept.md §20 (M4-M7). Not a coverage gap
for M001.

## Coverage verdict

**PASS** against the S03 success criteria.

- **Coverage: 100%.** Every requirement (F-01..F-14, F-17/19/22/23), all 10
  architectural rules, and every key architectural claim in
  `doc/architecture.md` has at least one source pointer in the traceability
  matrix (idea.md § / concept.md F-XX / S01 claim C-XX).
- **Contradictions: 0 unresolved.** All S01 mismatches are honored; the 2 gaps
  found are intentional M001 scope decisions (deferred P1/P2 capabilities; open
  storage stack), explicitly listed above rather than silently dropped.
- **Inputs intact:** `doc/idea.md` and `doc/concept.md` were not modified.

**Open items:** none.
