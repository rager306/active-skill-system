# AGENTS.md — Canonical Agent Harness Rules

This file is the authoritative reference for AI agents working in the
active-skill monorepo. Every section maps to a deterministic, testable
contract. **When in doubt, run the ratchet** (see §4).

## 1. Agent Protocol

- All agent invocations are recorded in `ratchet/ledger.jsonl` (append-only).
- Every action that changes a file MUST be followed by a verification command
  and the result must be summarized in the response.
- Never claim a file was created/modified without running `ls -la <path>` first.

## 2. Framework Integration

The active-skill-system is a layered architecture (R001):

```
L0 domain        (pure stdlib, no infra)
L1 ports         (Protocol contracts)
L2 application   (use_cases + Evolvable + RepairPolicy)
L3 adapters      (L3 implements L1; may import infra)
L4 composition   (L4 wires L2 + L3 via lazy imports)
```

Rules:
- **R002**: L0 + L1 + L2 never import activegraph / anthropic / openai.
- **R007**: enforce via `uv run lint-imports` (import-linter contract).
- **R008**: composition modules are side-effect free on import.
- **R009**: heavy infra imports live inside `_build_*()` helpers / `main()`.

Test command: `uv run pytest -q -p no:cacheprovider` (must remain green at every step).

## 3. Evidence Requirements

Every promotion of a new Evolvable / policy / tool must include:
- A test in `tests/` that fails without the change and passes with it.
- A `Verification Evidence` row in the task summary (command, exit code, duration).
- A UAT runtime check via `gsd_uat_exec` for end-to-end work.

## 4. Ratchet Obligation

Every agent error MUST be:
1. Logged in `ratchet/ledger.jsonl` via `RatchetLedger.append()`.
2. Linked to a test that prevents regression.
3. Reflected in the relevant `AGENTS.md` section.

The ratchet is append-only: existing entries cannot be modified, only superseded
by a new entry with a higher `id`.

## 5. Skill References

Fat skills live in `.agents/skills/<name>/SKILL.md` (see Impeccable for the
template). Each skill:
- Has a `name`, `description`, and `version` front-matter.
- Documents a deterministic process over the framework.
- References the relevant composition helper (e.g. `composition/compiler_evolution.py`).
- Logs each invocation to the ratchet ledger.

Currently registered skills: see `.agents/skills/` (M034 will populate this).

## 6. Composition Helper Catalog

The following `composition/<name>_evolution.py` entry points are available:

| Domain | Entry point | Primary metric |
|--------|-------------|----------------|
| compiler | `python -m active_skill_system.composition.compiler_evolution` | cycles |
| SQL | `python -m active_skill_system.composition.sql_evolution` | rows_examined |
| IaC | `python -m active_skill_system.composition.iac_evolution` | resource_count |
| security | `python -m active_skill_system.composition.security_evolution` | threat_count |
| ML | `python -m active_skill_system.composition.ml_evolution` | loss |
| network | `python -m active_skill_system.composition.network_evolution` | latency_ms |
| storage | `python -m active_skill_system.composition.storage_evolution` | storage_bytes |
| log | `python -m active_skill_system.composition.log_evolution` | error_rate |

All support `--use-polyhedral-model` (compiler) and `--stage <name>` flags
where applicable.

## 7. Memory Discipline

Project memory lives in `.gsd/memory/` (via GSD's `capture_thought` tool).
Each memory entry should:
- Have a clear category (architecture / pattern / gotcha / environment).
- Be confidence-rated (0.6 tentative, 0.8 solid, 0.95 well-confirmed).
- Be tagged for future searchability.

Ratchet rule: when a memory entry becomes outdated, supersede it with a
new entry that references the old one (never delete).
