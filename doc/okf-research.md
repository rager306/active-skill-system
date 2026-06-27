# Open Knowledge Format (OKF) — research

> Status: **research / format evaluation**. OKF is evaluated as a candidate
> interchange/serialization format for this project's knowledge artefacts. It is
> NOT adopted as a binding decision — v0.1 is a draft and the project has no
> immediate need that forces a format choice. Companion to the RGLA docs.
>
> Source: https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md
> (v0.1 Draft, read 2026-06). Announced 2026-06-12.

## 1. What OKF is (from SPEC v0.1)

An open, human- and agent-friendly format for representing *knowledge* — the
metadata, context, and curated insight around data and systems. A **Knowledge
Bundle** is a directory tree of markdown files; each file is a **Concept** with
YAML frontmatter (only `type` required) + a markdown body. Concepts link via
ordinary markdown links → a lightweight knowledge graph.

Goals (from SPEC §1): readable by humans without tooling, parseable by agents
without bespoke SDKs, diffable in version control, portable across
tools/organisations/time.

**Explicit non-goals (SPEC §1):** OKF does *not* define a concept taxonomy, does
*not* prescribe storage/serving/query infrastructure, and does *not* subsume
domain schemas (Avro/Protobuf/OpenAPI) — it *references* them.

## 2. How it relates to this project (honest, non-overlapping)

OKF is orthogonal to the load-bearing decisions already made. It occupies a
**different layer** than RLM (reasoning mechanism) or LadybugDB (provenance
storage):

| Layer in this project | What lives there | OKF's relationship |
|-----------------------|------------------|--------------------|
| RGLA Loop runtime (D009) | Loop entity, event-sourced lifecycle | Orthogonal — OKF is not a runtime |
| LoopGraph provenance (D009/D010) | Typed edges on LadybugDB (Cypher) | **Complementary export target** (§4.2) |
| RLM reasoning (D011) | model-picked decomposition | Orthogonal — OKF is not a reasoner |
| **Fat Skills** (M034) | `.agents/skills/<name>/SKILL.md` + frontmatter | **Already near-OKF** — format candidate (§4.1) |
| Domain types / genomes | frozen dataclasses in `domain/` | Orthogonal — code, not prose |
| Project docs (`doc/`) | markdown specs | Already OKF-shaped informally |

Key point: OKF does **not** duplicate or threaten R002 layering, D009 Loop,
D010 LadybugDB, or D011 RLM. It is a representation/interchange concern only.

## 3. Where it could be genuinely valuable (specific, narrow)

### 3.1 Fat-skills format formalization (M034)
The project's `.agents/skills/<name>/SKILL.md` files already use frontmatter +
markdown — structurally close to OKF concepts. Adopting the OKF `type`-required
convention + bundle layout would give fat skills a **vendor-neutral interchange
standard** and interop with the emerging OKF tooling (linters, visualisers,
Claude skills). Cost is low; the files already nearly conform.

### 3.2 LoopGraph provenance export (Loop Transfer)
The RGLA vision (D009) lists "Loop Transfer — перенос проверенных циклов между
проектами" as a deferred capability. LoopGraph provenance (typed edges on
LadybugDB) is the runtime source of truth; OKF is a candidate **serialization
format for exporting/sharing** a Loop subgraph as a portable, human-readable,
git-versioned bundle. LadybugDB stays the runtime store; OKF is the *view*.

### 3.3 Knowledge fragmentation reduction
Today knowledge is spread across `doc/`, `.agents/skills/`, `.gsd/`, and
fat-skills with no shared format. OKF could be the common envelope for curated,
shareable knowledge (not for all of these — `.gsd/` is system-managed state).

## 4. Honest caveats and push-back

1. **v0.1 Draft — not stable.** The SPEC explicitly says "Draft"; type taxonomy
   is unregistered. Binding the project to v0.1 now risks churn. Treat as a
   *format to track*, not commit to, until it stabilises or a concrete need
   forces a choice.
2. **Markdown-links ≠ typed provenance edges.** HN critique is correct: OKF's
   plain markdown links cannot carry `VERIFIED_BY` / `LEARNS_FROM` edge
   *payloads* (confidence, timestamp, schema). This is exactly why LoopGraph uses
   LadybugDB typed edges (D010). **OKF is a view/interchange, never the
   provenance source of truth.**
3. **Wiki ≠ provenance.** OKF is curated knowledge (a wiki), not execution
   provenance. Confusing the two would re-create the RuVector mistake (a name
   with no recorded contract). They serve different readers.
4. **No runtime/query value.** OKF gives no Cypher, no fast traversal. It cannot
   replace LadybugDB for runtime provenance queries.
5. **Vendor coupling risk.** Despite "vendor-neutral", the ecosystem
   (Knowledge Catalog, GA4 samples) is Google-centric so far. The format is open;
   the gravity is not yet.

## 5. Net effect on project decisions

| Decision | Effect |
|----------|--------|
| D009 (RGLA Loop + LoopGraph) | None — OKF is not a runtime/provenance store |
| D010 (LadybugDB) | None — OKF cannot replace typed-edge graph queries |
| D011 (RLM) | None — OKF is not a reasoning mechanism |
| **Fat skills format (M034)** | **Candidate** — near-OKF already; low-cost to formalise later |
| **Loop Transfer (deferred)** | **Candidate** — OKF as export/serialization format for Loop subgraphs |
| **Binding adoption** | **Declined for now** — v0.1 draft; track, do not commit |

No new binding decision (D012) is warranted yet. OKF is recorded as a **tracked
format candidate** for two narrow future uses (§3.1, §3.2), to be revisited when
either (a) OKF stabilises past draft, or (b) a concrete Loop-Transfer or
fat-skill-interop need forces a format choice.

## 6. Open follow-ups (not started)

1. If fat-skills interop with external OKF tooling becomes desired: audit
   `.agents/skills/*/SKILL.md` against the OKF concept spec and add the
   `type`-required convention.
2. If Loop Transfer is built: design a `LoopSubgraph → OKF bundle` exporter as an
   L4 composition utility (LadybugDB remains the source of truth).
3. Track OKF SPEC revisions; revisit this note if it moves past v0.1 draft.
