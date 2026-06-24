# Architecture requirements

Capability-contract for the Active Skill System architecture. Source-of-truth
lives in `.gsd/REQUIREMENTS.md` (GSD-managed symlink to
`/root/.gsd/projects/4030b84aba41/REQUIREMENTS.md`); this file is a git-tracked
shadow that mirrors the GSD document so requirements have a stable, reviewable
git history.

Last reconciled: 2026-06-23, post-M001 hex/onion audit.

---

## R001 — Hexagonal / Onion layering (composition → adapters → application → domain)

- **Class**: quality-attribute
- **Status**: active

Проект строится по канонической гексагональной/луковичной архитектуре с
четырьмя слоями. Зависимости только inward: composition может импортировать
adapters/application/domain; adapters — application/domain; application —
domain; domain — ничего, кроме stdlib. Обратное направление запрещено.

**Why it matters.** Изоляция бизнес-логики от инфраструктуры, заменяемость
адаптеров, тестируемость use-cases без поднятия runtime. Без этой структуры
каждый provider (LLM, DB, MCP) протекает в домен и любое изменение infra
ломает тесты логики.

**Validation.** `pyproject.toml` contracts:

- `Onion/hexagonal layers (inward dependencies only)` (layers)
- `Domain + application are infra-free` (forbidden)

`uv run lint-imports` reports `Contracts: 2 kept, 0 broken`.
`tests/test_layering.py::test_layering_contracts_kept` passes.

**Owner**: composition/diligence.py + all four layers.

---

## R002 — Domain + application are infra-free (no direct activegraph / anthropic / openai)

- **Class**: constraint
- **Status**: active

Слои `domain` и `application` не должны импортировать инфраструктуру напрямую:
ни `activegraph`, ни `anthropic`, ни `openai`, ни MCP SDK. Любой доступ к
инфраструктуре — только через `ports` (Protocol), которые реализуются в слое
adapters.

**Why it matters.** Если domain или application начнут импортировать
activegraph/anthropic/openai напрямую, они перестают быть переносимыми —
тесты use-cases требуют поднятия runtime, LLM-вызовы не мокаются, изменения
vendor'а ломают сразу несколько слоёв.

**Validation.** `pyproject.toml` forbidden-modules contract
`Domain + application are infra-free`:
`forbidden_modules = ["activegraph", "anthropic", "openai"]`.

`uv run lint-imports` reports `Domain + application are infra-free KEPT`.

**Owner**: domain/, application/, application/ports/.

---

## R003 — Domain holds entities + invariants (Genome / Expression / Evolution / Governance)

- **Class**: core-capability
- **Status**: active

Domain содержит сущности и инварианты Active Skill System
(Genome / Expression / Evolution / Governance и связанные с ними типы).
Никакого I/O, никакого импорта инфраструктуры — только типы, инварианты,
бизнес-правила. Зависит только от stdlib + typing.

**Why it matters.** Без заполненного domain «бизнес-логика» растворяется в
activegraph runtime и composition root — проект становится тонкой обёрткой
над чужой системой вместо самостоятельной системы. Domain — место, где
фиксируются инварианты проекта (что такое «геном навыка», что значит
«expression», когда считается «evolution»).

**Validation.** `domain/__init__.py` и `domain/*.py` содержат ≥3 базовых типа;
import-linter `Domain + application are infra-free` остаётся kept;
unit-тесты на инварианты работают без поднятия runtime.

**Owner**: domain/.

---

## R004 — Application holds use-cases (RunReasoning, ForkAndDiff, ReplayRun, …)

- **Class**: core-capability
- **Status**: active

Application содержит use-cases (сценарии оркестрации), которые вызываются
composition roots. Например: `RunReasoningUseCase`, `ForkAndDiffUseCase`,
`ReplayRunUseCase`. Use-case зависит только от domain и ports — не от
adapters и не от конкретного runtime. Composition root склеивает
use-case + adapters + runtime и выполняет сценарий.

**Why it matters.** Без use-cases в application composition root напрямую
дёргает `Runtime.run_goal` / `load_pack` — это смешивает «что делать»
(use-case) с «как запускать» (composition). Use-cases делают логику
переиспользуемой, тестируемой и независимой от конкретного
provider/runtime.

**Validation.** `application/*` содержит ≥1 use-case класс; use-case зависит
только от ports (Protocol) и domain; unit-тест use-case работает с
fake-адаптером (без activegraph).

**Owner**: application/ + composition roots.

---

## R005 — Inbound port to runtime (`application/ports/runtime.py`)

- **Class**: quality-attribute
- **Status**: active

Доступ application к activegraph runtime (и любой другой инфраструктуре)
идёт через ports. Минимум: `application/ports/runtime.py` Protocol
(запустить, форкнуть, replay, diff, экспортировать trace). Adapters
реализуют этот порт над activegraph; use-cases в application дёргают
только порт.

**Why it matters.** Если use-case импортирует `activegraph.Runtime`
напрямую, application перестаёт быть инфра-свободным — нарушается R002, и
тесты use-case требуют поднятия runtime. Через порт use-case становится
тестируемым с fake RuntimePort, а activegraph становится одной из
реализаций порта (в composition её легко заменить).

**Validation.** `application/ports/runtime.py` существует, определяет
Protocol с методами `run` / `fork` / `replay` / `diff` / `export`;
import-linter `Domain + application are infra-free` остаётся kept после
добавления use-case.

**Owner**: application/ports/runtime.py.

---

## R006 — Adapter granularity (≤200 LOC or split)

- **Class**: quality-attribute
- **Status**: active

Адаптеры не должны разрастаться: каждый адаптер ≤200 LOC, либо
разбивается на под-модули в своей подпапке
(например `adapters/llm/minimax/{_provider,_thinking,_tokens,_env}.py` +
`__init__.py` re-export). Решение — на авторе адаптера: можно оставить
один файл, если ≤200 LOC.

**Why it matters.** `minimax.py` уже 254 LOC и смешивает 4 ответственности
(provider lifecycle, thinking cache, count_tokens fallback, env loading).
Это повышает cognitive load и затрудняет unit-тестирование. Split по
ответственностям делает каждый кусок читаемым, тестируемым отдельно и
изменяемым без риска.

**Validation.** `wc -l src/active_skill_system/adapters/**/*.py` ≤ 200;
при >200 LOC — адаптер разбит на под-модули, каждый из которых ≤200 LOC
и имеет собственные unit-тесты.

**Owner**: все адаптеры (llm, db, mcp, sandbox). Backlog: разбить
`minimax.py` на 4 модуля.

---

## R007 — CI enforcement of layering contracts

- **Class**: operability
- **Status**: active

Контракты импорт-слоёв проверяются автоматически в CI:
`pyproject.toml [tool.importlinter]` объявляет контракты;
`tests/test_layering.py::test_layering_contracts_kept` запускает
`lint-imports` через subprocess и валидирует exit code + `0 broken` в
выводе. Любое нарушение контракта ломает дефолтный `uv run pytest` (без
`--runllm`).

**Why it matters.** Без автоматической проверки архитектурные правила
размываются: добавление импорта в обратном направлении проходит
code-review незамеченным и постепенно превращает onion в
big-ball-of-mud. Тест в CI заставляет каждое нарушение быть явным
решением (обновить контракт + обосновать), а не случайностью.

**Validation.** `uv run pytest -q -k layering` проходит;
`uv run lint-imports` выводит `Contracts: 2 kept, 0 broken`; контракты
добавлены в pre-commit hook или CI pipeline.

**Owner**: tests/test_layering.py + pyproject.toml [tool.importlinter].

---

## R008 — Side-effects in composition roots only inside `main()`

- **Class**: operability
- **Status**: active

В composition roots side-effects (`configure_logging`, env load, runtime
construction, file IO) выполняются внутри `main()` / entry-функции, а не
на module-import. Импорт модуля composition не должен иметь видимых
side-effects.

**Why it matters.** Если composition имеет side-effects на import, то
тесты, которые импортируют `application/ports` (для проверки протокола),
непреднамеренно поднимают logging, env, runtime. Это нарушает изоляцию
и делает невозможным headless-использование адаптеров из тестов.

**Validation.** `grep -rn "configure_logging|Runtime(|Graph("
src/active_skill_system/composition` — все вхождения внутри `def main` /
`def run_*`, не на module-уровне. Тест:
`uv run python -c "import active_skill_system.composition.diligence"`
не печатает в stderr.

**Owner**: composition/. Backlog: убрать `configure_logging(...)` на
module-level в `composition/diligence.py:24`, перенести в начало
`main()`.

---

## R009 — Lazy infra imports in composition roots

- **Class**: operability
- **Status**: active

Composition roots используют lazy import для тяжёлой инфраструктуры
(`activegraph.packs.*`, `anthropic`, `openai`). Конкретно:
`from activegraph.packs.diligence import ...` — внутри `def main(...)`, а
не на module-уровне. Это позволяет импортировать composition module для
type-check'а или CLI help без поднятия runtime.

**Why it matters.** Composition — единственный слой, который может
импортировать инфраструктуру. Lazy import держит эту зависимость
локальной: пока composition не запущен (например, `--help`), тяжёлые
пакеты не загружаются. Это ускоряет запуск и делает CLI-help безопасным.

**Validation.** `grep -rn "^from activegraph\.packs|^from anthropic|^from
openai" src/active_skill_system/composition` — все вхождения имеют
preceding line `def main` или `def run_*` (не module-level). Тест:
`uv run python -c "import active_skill_system.composition.diligence;
print('ok')"` работает без сети и без activegraph Runtime.

**Owner**: composition/.

---

## Summary table

| ID | Class | Summary |
|----|-------|---------|
| R001 | quality-attribute | Hex/Onion layering (inward-only) |
| R002 | constraint | domain + application infra-free |
| R003 | core-capability | Domain entities + invariants |
| R004 | core-capability | Application use-cases |
| R005 | quality-attribute | Inbound runtime port |
| R006 | quality-attribute | Adapter granularity ≤200 LOC |
| R007 | operability | CI enforcement of layering |
| R008 | operability | Side-effects only in `main()` |
| R009 | operability | Lazy infra imports in composition |