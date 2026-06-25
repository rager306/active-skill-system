# Architecture Requirements Synthesis & Roadmap Correction

> Post-D006/D007. Consolidates all requirements from concept.md, architecture.md,
> loop-engineering synthesis, ComPilot analysis, and Synapse determinism patterns
> into a single traceable map. Adjusts the roadmap.

## 1. Requirement consolidation

### P0 — mandatory kernel (concept.md F-01..F-14)

| ID | Requirement | Status | Component | Source |
|---|---|---|---|---|
| F-01 | Accept request + constraints + budget | ✅ | `RunGoal`, `Budget` | M002 |
| F-02 | Request → validable TaskSpec | ✅ | `ParseTaskSpecUseCase` | M007 |
| F-03 | Typed Task Graph | ✅ | `TaskGraph`, `TaskNode`, `TaskEdge` | M003 |
| F-04 | Version graph changes | ✅ | `TaskGraph.commit()` | M003 |
| F-05 | Goal reachability | ✅ | `_goal_supported` | M003 |
| F-06 | Detect gaps/contradictions/constraints | ✅ | `ValidateTaskGraphUseCase` | M003 |
| F-07 | Bounded repair loop | ✅ | `RepairLoopUseCase` | M009 |
| F-08 | Plan tool calls for concrete gaps | ✅ | `ToolPort` + `RepairPolicy` | M009 |
| F-09 | Persist provenance | ✅ | Evidence nodes + DERIVED_FROM | M003 |
| F-10 | Verify final answer | ✅ | `OutputVerifierUseCase` | M013 |
| F-11 | Partial result on budget exhaustion | ✅ | `BudgetController` | M013 |
| F-12 | Full audit/event log | ✅ | `ActivegraphEventSink` + replay | M005 |
| F-13 | Cancellation + idempotency | ❌ | — | PENDING |
| F-14 | Approval for irreversible actions | ⚠️ | `GovernancePolicy` skeleton | PENDING |

**P0: 12/14 closed.** F-13 (cancel/idempotency) + F-14 (approval) remain.

### P1 — development (concept.md F-15..F-22)

| ID | Requirement | Status | Component |
|---|---|---|---|
| F-17 | Typed Skill Registry | 🔲 | GeneSpec domain skeleton (M002) |
| F-19 | Experience retrieval by signature | 🔲 | — |
| F-20 | Deterministic domain validators | ✅ | `ValidateTaskGraphUseCase` |
| F-21 | Cost/latency/risk policies | ⚠️ | `BudgetController` (cost); risk = pending |
| F-22 | Versioning of prompts/policies/skills | ⚠️ | `PromptGenome` (M012); policies/skills = pending |

### Determinism patterns (D007 — Synapse synthesis)

| Pattern | Status | Component | Priority |
|---|---|---|---|
| Verify-after-act (action-level anti-fancy) | ❌ | `ToolPort` extension | HIGH |
| SafetyLevel L1/L2/L3 in GovernancePolicy | ⚠️ | `GovernancePolicy` (M002) | HIGH |
| ToolProfile (normal/break_glass/debug) | ❌ | `ToolRegistry` | MEDIUM |
| EvidenceLedger (per-patch audit) | ❌ | — | MEDIUM |
| Delta-verification (before/after patch) | ❌ | — | LOW |

### Loop engineering (D006 — synthesis)

| Primitive | Status | Component |
|---|---|---|
| Scheduling | ✅ | `RunFSM` |
| Worktrees | ✅ | `ExperimentWorkspace` |
| Skills | ✅ | `PromptGenome` |
| Connectors | ✅ | `ToolPort` |
| Sub-agents (maker/checker) | ✅ | `Validate` + `RepairLoop` |
| State/Memory | ✅ | Event log |

### Evolvable artifacts (D004/D005)

| Artifact | Status | Component |
|---|---|---|
| ModelGenome | ✅ | `ModelGenome` + `ModelSelector` (M011) |
| PromptGenome | ✅ | `PromptGenome` + `PromptRegistry` (M012) |
| Evolvable trait extraction | 🔲 | 2 concrete cases done; 3rd needed |
| SkillGenome | 🔲 | Domain skeleton (M002); registry = concept M4 |
| RepairPolicyGenome | 🔲 | After reasoning loop stabilization |

## 2. Hexagonal/onion layer impact

### What changes per layer:

```
L1 Domain (changes needed):
  - GovernancePolicy: add SafetyLevel enum (L1/L2/L3)
  - ToolCapability: add VERIFY capability (for verify-after-act tools)
  - EvidenceEntry: new frozen dataclass (action_id, expected, actual, verified_by, timestamp)

L2 Application (changes needed):
  - ToolPort: extend with verify(result) -> VerifiedToolResult
  - ToolRegistry: add ToolProfile filtering (normal/break_glass/debug)
  - New use-case: VerifyToolResultUseCase (independent readback)
  - BudgetController: already tracks tool_calls; add verified vs unverified counts

L3 Adapters (changes needed):
  - Existing tools (SimpleSearchTool, SimpleCalcTool): add verify() method
  - New: VerifiedToolResult wrapping ToolResult with independent confirmation
  - MiniMaxProvider: no change (LLM is not a "tool" in verify-after-act sense)

L4 Composition (changes needed):
  - diligence.py: wire ToolProfile filtering + verify-after-act
```

### What does NOT change:
- TaskGraph (M003) — generic reasoning structure, unaffected
- ValidateTaskGraphUseCase (M003) — graph validator, unaffected
- RepairLoopUseCase (M009) — repair loop, only gets verified patches
- GraphPatch (M009) — patch structure, unaffected
- ExperimentWorkspace (M006) — fork/diff, unaffected
- ModelGenome/ModelSelector (M011) — model routing, unaffected
- PromptGenome/PromptRegistry (M012) — prompt versioning, unaffected
- OutputVerifierUseCase (M013) — output gates, unaffected
- BudgetController (M013) — budget tracking, unaffected
- Anti-fancy gate (M003) — Claim/Graph/Output levels, unaffected

**Architectural invariant:** determinism patterns are **additive verification layers**,
not changes to core reasoning structure. They wrap existing components (ToolPort →
VerifiedToolPort) without altering the onion layering.

## 3. ADR impact assessment

| Decision | Impact | Detail |
|---|---|---|
| D001 (claude-code disabled) | None | Provider routing, unrelated |
| D002 (riskratchet) | None | Quality gate, unaffected by verification patterns |
| D003 (RunReasoningUseCase shape) | None | Use-case interface, unaffected |
| D004 (Evolvable trait) | None | Genome/evolution, unaffected |
| D005 (ModelGenome) | None | Model routing, unaffected |
| D006 (Loop Engineering) | **Enhanced** | Safety levels L1-L3 now have concrete domain enum |
| D007 (Determinism patterns) | **New** | This decision — verify-after-act + safety + profiles |

**No existing ADR is invalidated.** D006 is enhanced (safety levels get concrete
implementation). D007 is new (action-level verification layer).

## 4. Corrected roadmap

### Phase 1: P0 closure + determinism hardening

```
M014: P0 closure + Determinism hardening
  S01: F-13 Cancellation + idempotency (RunGoal cancel, idempotency key)
  S02: F-14 Approval workflow (SafetyLevel L1/L2/L3 in GovernancePolicy + approval gate)
  S03: Verify-after-act (VerifiedToolResult, ToolPort.verify(), ToolProfile)
  S04: EvidenceLedger (append-only per-patch audit trail)
```

### Phase 2: Evolvable trait + domain profiles

```
M015: Evolvable trait extraction (D004)
  S01: Evolvable protocol + FitnessSignal + MutationSpace
  S02: ModelGenome + PromptGenome → Evolvable conformance
  S03: EvolutionEngine[E] (offline mutation → eval → promotion gate)

M016: ComPilot domain profile (compiler optimization benchmark)
  S01: Compiler NodeKind/EdgeKind extension (loops, deps, transforms)
  S02: TiramisuCompilerTool (compile → measure → ToolResult)
  S03: End-to-end on PolyBench (compare with vanilla ComPilot)
```

### Phase 3: Concept M4-M6

```
M017: Skill Registry (concept M4)
  - GeneSpec/ExpressionProfile binding
  - Sandbox + risk gate + trust/signatures
  - ToolProfile for skills (D007)

M018: Experience Retrieval (concept M5)
  - Task signature → pattern matching
  - (subgraph, transform) → cached results
  - Sample-efficiency for repair loop

M019: Offline Evolution (concept M6)
  - EvolutionEngine[E: Evolvable] (from M015)
  - Mutation → held-out eval → promotion gate
  - Applied to: prompts, models, repair policies, skills
```

### Phase 4: Concept M7

```
M020: Multi-domain Runtime (concept M7)
  - Domain ontologies
  - Subgraphs
  - Specialized validators per domain
```

## 5. Priority justification

1. **M014 first** — P0 closure (F-13/F-14) is the contract. Determinism patterns
   (verify-after-act, safety levels) are the cheapest high-impact addition
   (wrap existing tools, extend GovernancePolicy). Combined in one milestone
   because F-14 (approval) and SafetyLevel (D006/D007) are the same concept.

2. **M015 next** — Evolvable trait extraction is ready (2 concrete cases). Third
   case (TransformationGenome from ComPilot, M016) validates the generalization.

3. **M016** — ComPilot is the first real-world benchmark. Validates architecture
   on measurable metrics (runnable-rate, speedup, tokens).

4. **M017-M019** — concept M4-M6. Depends on M015 (Evolvable) and M016
   (domain profile validation).

5. **M020** — concept M7. Multi-domain. Furthest out.
