# Спецификация аналога SymFSM для собственного проекта

Официальная концепция сводится к цепочке:

```text
Запрос → когнитивная карта → проверка достижимости → repair → выполнение → синтез → проверка
```

Сайт также заявляет рекурсивные подкарты, накопление успешных траекторий и разделение ролей: LLM понимает и формулирует, а внешний слой контролирует структуру решения. ([principium.pro][1])

Для реализации лучше не копировать SymFSM буквально, а разделить систему на три независимые модели:

1. **Task Graph** — что известно, что требуется и какие существуют зависимости.
2. **Plan Graph** — какие действия необходимо выполнить, чтобы закрыть пробелы.
3. **Run FSM** — в какой фазе обработки находится запрос.

Это устраняет главную неоднозначность публичной концепции: понятие, состояние процесса и действие не должны быть одной сущностью.

---

# 1. Кристаллизованная идея

> **Система превращает запрос пользователя в типизированную модель задачи, проверяет возможность достижения цели, устраняет структурные и информационные пробелы, выполняет только обоснованные действия и генерирует ответ из проверенного состояния.**

Формула системы:

```text
Cognitive Runtime =
    Task IR
  + Semantic Graph
  + Workflow FSM
  + Validators
  + Repair Controller
  + Tool/Skill Runtime
  + Evidence Ledger
  + Output Synthesizer
  + Experience/Evaluation Loop
```

Главное ограничение:

```text
структурно корректно ≠ фактически истинно
```

Поэтому система должна проверять одновременно:

* структуру рассуждения;
* происхождение фактов;
* выполнение ограничений;
* результат инструментов;
* соответствие финального ответа построенной модели.

---

# 2. Архитектурный контекст

```mermaid
flowchart LR
    U[Пользователь или внешняя система]
    API[API Gateway]
    CK[Cognitive Control Plane]
    LLM[LLM Providers]
    TOOLS[Инструменты и агенты]
    RAG[RAG и источники знаний]
    SKILLS[Skill Registry]
    DATA[Данные проекта]
    HUMAN[Human Approval]
    OBS[Наблюдаемость]

    U --> API
    API --> CK

    CK <--> LLM
    CK <--> TOOLS
    CK <--> RAG
    CK <--> SKILLS
    CK <--> DATA
    CK <--> HUMAN

    API --> OBS
    CK --> OBS
    TOOLS --> OBS
```

**Cognitive Control Plane** является управляющим контуром. LLM, RAG, инструменты и агенты — исполнители, а не владельцы глобальной логики.

---

# 3. Логическая архитектура

```mermaid
flowchart TB
    subgraph Interface["Интерфейсный слой"]
        API[REST API]
        UI[Reasoning Studio]
        SDK[SDK / Webhooks / SSE]
    end

    subgraph Control["Управляющий слой"]
        ROUTER[Complexity Router]
        SUP[Run Supervisor FSM]
        POLICY[Policy Engine]
        BUDGET[Budget Controller]
    end

    subgraph Semantic["Семантический слой"]
        PARSER[Task Interpreter]
        ONTO[Ontology Router]
        BUILDER[Task Graph Builder]
        GRAPH[Versioned Task Graph]
    end

    subgraph Reasoning["Проверка и планирование"]
        VALID[Validator Pipeline]
        REACH[Reachability Engine]
        REPAIR[Repair Planner]
        PLANNER[Plan Graph Builder]
    end

    subgraph Execution["Исполнение"]
        SKILL[Skill Resolver]
        TOOL[Tool Runtime]
        SANDBOX[Sandbox]
        SYNTH[Answer Synthesizer]
        OUTVAL[Output Verifier]
    end

    subgraph Knowledge["Память и знания"]
        EVID[Evidence Ledger]
        EXP[Experience Store]
        REG[Skill and Ontology Registry]
        ART[Artifact Store]
    end

    subgraph Infra["Инфраструктура"]
        EVENTS[Event Log]
        TELEMETRY[Metrics and Traces]
        QUEUE[Job Queue]
        SECRETS[Secrets Vault]
    end

    API --> ROUTER
    UI --> API
    SDK --> API

    ROUTER --> SUP
    SUP --> PARSER
    PARSER --> ONTO
    ONTO --> BUILDER
    BUILDER --> GRAPH

    GRAPH --> VALID
    VALID --> REACH
    REACH --> REPAIR
    REPAIR --> GRAPH
    REACH --> PLANNER

    PLANNER --> SKILL
    SKILL --> TOOL
    TOOL --> SANDBOX
    SANDBOX --> EVID
    EVID --> GRAPH

    GRAPH --> SYNTH
    SYNTH --> OUTVAL
    OUTVAL --> SUP

    POLICY --> SUP
    BUDGET --> SUP
    REG --> ONTO
    REG --> SKILL
    EXP --> REPAIR

    SUP --> EVENTS
    SUP --> TELEMETRY
    SUP --> QUEUE
    TOOL --> SECRETS
    TOOL --> ART
```

---

# 4. Разделение моделей

## 4.1. Task Graph

Описывает предметную структуру задачи:

```mermaid
classDiagram
    class Task {
        +taskId
        +domain
        +taskType
        +riskLevel
        +status
    }

    class Goal {
        +goalId
        +description
        +priority
        +status
    }

    class Constraint {
        +constraintId
        +type
        +expression
        +severity
    }

    class Claim {
        +claimId
        +text
        +status
        +confidence
    }

    class Evidence {
        +evidenceId
        +source
        +retrievedAt
        +reliability
        +contentHash
    }

    class Hypothesis {
        +hypothesisId
        +statement
        +testStatus
    }

    class Gap {
        +gapId
        +gapType
        +severity
        +status
    }

    class Mechanism {
        +mechanismId
        +rule
        +validator
    }

    Task "1" --> "*" Goal
    Task "1" --> "*" Constraint
    Task "1" --> "*" Claim
    Task "1" --> "*" Gap

    Evidence "*" --> "*" Claim : supports
    Hypothesis "*" --> "*" Claim : mayExplain
    Mechanism "*" --> "*" Claim : derives
    Constraint "*" --> "*" Goal : restricts
    Gap "*" --> "*" Goal : blocks
```

### Минимальные типы узлов

| Тип          | Назначение                        |
| ------------ | --------------------------------- |
| `Goal`       | Требуемый результат               |
| `Fact`       | Принятое исходное утверждение     |
| `Evidence`   | Проверяемый источник факта        |
| `Constraint` | Жёсткое или мягкое ограничение    |
| `Hypothesis` | Непроверенное предположение       |
| `Mechanism`  | Правило получения нового вывода   |
| `Unknown`    | Недостающая информация            |
| `Decision`   | Выбор между альтернативами        |
| `Action`     | Необходимое внешнее действие      |
| `Result`     | Результат действия или вычисления |

### Основные типы связей

```text
SUPPORTS
REQUIRES
DERIVED_FROM
CAUSES
CONTRADICTS
BLOCKS
SATISFIES
REFINES
DEPENDS_ON
PRODUCES
INVALIDATES
```

---

## 4.2. Plan Graph

Task Graph отвечает на вопрос **«что должно быть доказано или получено?»**.

Plan Graph отвечает на вопрос **«что выполнить для этого?»**.

```mermaid
flowchart LR
    G[Цель]
    SG1[Подцель A]
    SG2[Подцель B]
    GAP1[Недостающий факт]
    GAP2[Неизвестный механизм]
    A1[Поиск источников]
    A2[Вызов инструмента]
    A3[Применение skill]
    V1[Проверка результата]
    DONE[Цель подтверждена]

    G --> SG1
    G --> SG2

    SG1 --> GAP1
    SG2 --> GAP2

    GAP1 --> A1
    GAP2 --> A2
    GAP2 --> A3

    A1 --> V1
    A2 --> V1
    A3 --> V1

    V1 --> DONE
```

---

## 4.3. Run FSM

FSM управляет **жизненным циклом запроса**, но не пытается представить каждое понятие отдельным состоянием.

```mermaid
stateDiagram-v2
    [*] --> RECEIVED

    RECEIVED --> CLASSIFYING
    CLASSIFYING --> DIRECT_PATH: простая задача
    CLASSIFYING --> MODELING: сложная задача

    DIRECT_PATH --> SYNTHESIZING

    MODELING --> VALIDATING_MODEL
    VALIDATING_MODEL --> PLANNING: модель достаточна
    VALIDATING_MODEL --> REPAIRING: обнаружены gaps
    VALIDATING_MODEL --> PARTIAL: исчерпан бюджет

    REPAIRING --> VALIDATING_MODEL: graph patch
    REPAIRING --> WAITING_INPUT: нужно обязательное уточнение
    REPAIRING --> WAITING_APPROVAL: опасное действие

    WAITING_INPUT --> MODELING
    WAITING_APPROVAL --> PLANNING: разрешено
    WAITING_APPROVAL --> PARTIAL: отклонено

    PLANNING --> EXECUTING
    EXECUTING --> VALIDATING_MODEL: получены новые данные
    EXECUTING --> REPAIRING: ошибка действия
    EXECUTING --> SYNTHESIZING: план завершён

    SYNTHESIZING --> VALIDATING_OUTPUT
    VALIDATING_OUTPUT --> COMPLETED: проверки пройдены
    VALIDATING_OUTPUT --> REPAIRING: исправимая ошибка
    VALIDATING_OUTPUT --> PARTIAL: неполный результат
    VALIDATING_OUTPUT --> FAILED: критическая ошибка

    RECEIVED --> CANCELLED
    CLASSIFYING --> CANCELLED
    MODELING --> CANCELLED
    EXECUTING --> CANCELLED

    COMPLETED --> [*]
    PARTIAL --> [*]
    FAILED --> [*]
    CANCELLED --> [*]
```

---

# 5. Основной workflow

```mermaid
sequenceDiagram
    autonumber

    actor User
    participant API
    participant Router
    participant Supervisor
    participant Interpreter
    participant Graph
    participant Validators
    participant Repair
    participant Tools
    participant LLM
    participant OutputVerifier
    participant Memory

    User->>API: Запрос + ограничения
    API->>Supervisor: Создать Run
    Supervisor->>Router: Оценить сложность и риск

    alt Простая задача
        Router-->>Supervisor: Direct path
        Supervisor->>LLM: Сформировать ответ
    else Сложная задача
        Router-->>Supervisor: Cognitive path
        Supervisor->>Interpreter: Создать TaskSpec
        Interpreter->>Graph: Построить Task Graph

        loop До достижения цели или бюджета
            Supervisor->>Validators: Проверить граф
            Validators->>Graph: Reachability, constraints, provenance

            alt Есть разрывы
                Validators-->>Supervisor: GapSet
                Supervisor->>Repair: Выбрать стратегию
                Repair->>Tools: Поиск, вычисление или skill
                Tools-->>Repair: Результат + evidence
                Repair->>Graph: Применить versioned patch
            else Граф достаточен
                Validators-->>Supervisor: Valid trajectory
            end
        end

        Supervisor->>LLM: Синтез по проверенной траектории
    end

    LLM-->>Supervisor: Draft answer
    Supervisor->>OutputVerifier: Проверка ответа

    alt Ответ корректен
        OutputVerifier-->>Supervisor: Pass
        Supervisor->>Memory: Сохранить шаблон и метрики
        Supervisor-->>API: Completed
        API-->>User: Ответ + уровень уверенности
    else Ответ нарушает модель
        OutputVerifier-->>Supervisor: Violations
        Supervisor->>Repair: Output repair
    end
```

---

# 6. Логика достижимости

Цель считается достижимой только при выполнении всех условий:

```text
1. Существует путь от принятых фактов или evidence к цели.
2. Каждый переход использует известный механизм или правило.
3. Все обязательные входы механизма доступны.
4. Жёсткие ограничения не нарушены.
5. На пути нет нерешённого критического противоречия.
6. Фактические утверждения имеют provenance.
7. Непроверенные предположения явно маркированы.
```

Упрощённо:

```text
reachable(goal) =
    exists valid_path(start_nodes, goal)
    and all_guards_satisfied(path)
    and all_hard_constraints_satisfied(path)
    and no_critical_gap(path)
```

```mermaid
flowchart TD
    G[Проверяемая цель]
    P{Есть путь от известных данных?}
    M{Все переходы имеют механизм?}
    C{Жёсткие ограничения выполнены?}
    E{Факты имеют evidence?}
    X{Есть критические противоречия?}
    OK[Цель достижима]
    GAP[Создать Gap]
    REJECT[Ветка недопустима]

    G --> P

    P -- Нет --> GAP
    P -- Да --> M

    M -- Нет --> GAP
    M -- Да --> C

    C -- Нет --> REJECT
    C -- Да --> E

    E -- Нет --> GAP
    E -- Да --> X

    X -- Да --> REJECT
    X -- Нет --> OK
```

---

# 7. Repair-механика

Repair не должен «додумывать недостающее». Он должен определить класс проблемы и выбрать ограниченное действие.

```mermaid
flowchart TD
    GAP[Обнаружен Gap]
    CLASSIFY{Тип Gap}

    CLASSIFY -->|Missing evidence| RETRIEVE[Найти источник]
    CLASSIFY -->|Ambiguity| BRANCH[Создать альтернативные ветви]
    CLASSIFY -->|Missing mechanism| DECOMP[Декомпозировать или найти skill]
    CLASSIFY -->|Contradiction| RESOLVE[Определить конфликтующие основания]
    CLASSIFY -->|Constraint violation| REPLAN[Перестроить Plan Graph]
    CLASSIFY -->|Tool failure| SUBSTITUTE[Повторить или заменить инструмент]
    CLASSIFY -->|Undefined concept| DEFINE[Связать с онтологией или определить]
    CLASSIFY -->|Unsafe action| APPROVAL[Запросить разрешение]

    RETRIEVE --> PATCH[Сформировать GraphPatch]
    BRANCH --> SUBMAP[Создать SubGraph]
    DECOMP --> PATCH
    RESOLVE --> PATCH
    REPLAN --> PATCH
    SUBSTITUTE --> PATCH
    DEFINE --> PATCH
    APPROVAL --> PATCH

    SUBMAP --> VERIFY[Повторная проверка]
    PATCH --> VERIFY

    VERIFY -->|Успех| ACCEPT[Зафиксировать новую версию]
    VERIFY -->|Нет улучшения| ROLLBACK[Откатить patch]
    VERIFY -->|Бюджет исчерпан| PARTIAL[Вернуть частичный результат]
    ROLLBACK --> CLASSIFY
```

## Классы repair-операций

| Gap                                           | Действие                         |
| --------------------------------------------- | -------------------------------- |
| Не хватает факта                              | RAG, поиск, база данных, API     |
| Не хватает механизма                          | Skill retrieval или декомпозиция |
| Неоднозначность                               | Создание нескольких ветвей       |
| Противоречие                                  | Сравнение provenance и доверия   |
| Недостаточная детализация                     | Подкарта для локального узла     |
| Нарушение ограничения                         | Перепланирование                 |
| Ошибка инструмента                            | Retry, fallback, substitute      |
| Нет обязательного пользовательского параметра | Clarification                    |
| Ответ не соответствует графу                  | Локальная регенерация            |

## Обязательные ограничители

```yaml
repair_policy:
  max_cycles: 5
  max_subgraph_depth: 3
  max_parallel_branches: 4
  max_tool_calls: 20
  max_total_tokens: configurable
  max_wall_clock: configurable
  loop_detection: true
  minimum_graph_improvement: required
```

Repair должен приниматься только при измеримом улучшении:

```text
новая версия графа принимается, если:

critical_gaps уменьшились
или reachability выросла
или число подтверждённых целей увеличилось

при этом:
hard_constraint_violations не выросли
risk_score не ухудшился
```

---

# 8. Жизненный цикл утверждения

```mermaid
stateDiagram-v2
    [*] --> PROPOSED

    PROPOSED --> HYPOTHESIS: нет доказательств
    PROPOSED --> GROUNDED: найден evidence
    PROPOSED --> REJECTED: нарушена схема

    HYPOTHESIS --> GROUNDED: гипотеза подтверждена
    HYPOTHESIS --> REJECTED: опровергнута
    HYPOTHESIS --> UNRESOLVED: недостаточно данных

    GROUNDED --> VERIFIED: валидатор пройден
    GROUNDED --> CONFLICTED: найдено противоречие

    CONFLICTED --> VERIFIED: конфликт разрешён
    CONFLICTED --> REJECTED: источник проиграл

    VERIFIED --> INVALIDATED: новые данные
    INVALIDATED --> PROPOSED: повторная оценка

    VERIFIED --> [*]
    REJECTED --> [*]
    UNRESOLVED --> [*]
```

Критическое правило:

> LLM не может самостоятельно перевести своё утверждение из `PROPOSED` в `VERIFIED`.

Для этого требуется хотя бы один независимый механизм:

* детерминированный валидатор;
* внешний источник;
* вычисление;
* инструмент;
* доменное правило;
* human approval.

---

# 9. Anti-Fantasy как формальная политика

Узел разрешается включить в финальный ответ, если выполнено хотя бы одно условие:

```text
1. Узел подтверждён evidence.
2. Узел получен детерминированным вычислением.
3. Узел выведен через зарегистрированное правило.
4. Узел явно маркирован как предположение.
5. Узел является формулировкой, а не фактическим утверждением.
```

```mermaid
flowchart LR
    N[Новый узел]
    T{Тип определён?}
    P{Есть provenance?}
    H{Это hypothesis?}
    R{Есть правило вывода?}
    A[Принять]
    Q[Принять как непроверенный]
    X[Отклонить]

    N --> T
    T -- Нет --> X
    T -- Да --> P

    P -- Да --> A
    P -- Нет --> H

    H -- Да --> Q
    H -- Нет --> R

    R -- Да --> A
    R -- Нет --> X
```

---

# 10. Интеграция агентов, инструментов и skills

Агенты и инструменты должны подключаться через типизированный контракт, а не через свободный текст.

```mermaid
flowchart LR
    GAP[Gap или Action]
    QUERY[Capability Query]
    REG[Capability Registry]
    MATCH[Typed Matching]
    POLICY[Risk and Trust Gate]
    BIND[Local Binding]
    RUN[Sandbox Execution]
    CHECK[Result Validation]
    GRAPH[Task Graph Update]

    GAP --> QUERY
    QUERY --> REG
    REG --> MATCH
    MATCH --> POLICY
    POLICY -->|Разрешено| BIND
    POLICY -->|Нужен человек| APPROVAL[Approval]
    POLICY -->|Запрещено| BLOCK[Blocked]

    APPROVAL --> BIND
    BIND --> RUN
    RUN --> CHECK
    CHECK --> GRAPH
```

Для проектного развития разумно синтезировать это со SkillGenome-подходом:

* передавать декларативную спецификацию навыка, а не произвольный код;
* типизировать вход и выход;
* разделять переносимую спецификацию и локальную привязку;
* подписывать внешние skills;
* выполнять локальную оценку и risk gate;
* запускать действия в sandbox. 

## Минимальный SkillSpec

```yaml
skill:
  id: research.compare_sources
  version: 1.0.0

  input_schema:
    type: object
    required: [question, sources]

  output_schema:
    type: object
    required: [findings, conflicts, citations]

  capabilities:
    - http.read
    - document.parse

  side_effects:
    external_calls: true
    writes: false
    irreversible: false

  risk:
    level: low

  execution:
    runtime: local
    sandbox: required

  verification:
    validators:
      - schema
      - citation_coverage
      - source_consistency
```

---

# 11. Накопление опыта без хранения скрытых рассуждений

Сохранять следует не внутренний поток размышлений модели, а структурированные операционные объекты:

```text
Task signature
Graph pattern
Gap classes
Repair actions
Tool results
Accepted trajectory
Rejected branches
Constraint violations
Output verification result
Cost and latency
User feedback
```

```mermaid
flowchart TB
    RUN[Завершённый Run]
    EXTRACT[Experience Extractor]
    PATTERN[Graph Pattern]
    REPAIR[Repair Pattern]
    SKILL[Skill Candidate]
    METRIC[Evaluation Record]
    STORE[Experience Store]

    RUN --> EXTRACT
    EXTRACT --> PATTERN
    EXTRACT --> REPAIR
    EXTRACT --> SKILL
    EXTRACT --> METRIC

    PATTERN --> STORE
    REPAIR --> STORE
    SKILL --> STORE
    METRIC --> STORE

    STORE --> RETRIEVE[Retrieve for new task]
    RETRIEVE --> SUP[Run Supervisor]
```

---

# 12. Контур эволюции системы

Эволюция должна происходить **офлайн**, через benchmark и promotion gate, а не посредством неконтролируемого самоизменения production-системы.

SkillNet и EvoSkill хорошо дополняют такой подход: registry предоставляет поиск, граф зависимостей и quality gates, а эволюционный контур анализирует ошибки, создаёт варианты и проверяет их на held-out задачах. 

Более точная модель оптимизации — не «обучение нейросети», а validation-gated local search:

```text
failure analysis
→ mutation
→ evaluation
→ selection
→ promotion
```

То есть изменения принимаются только после независимой проверки, а не потому, что LLM считает их улучшением. 

```mermaid
flowchart LR
    LOGS[Production Failures]
    DATASET[Evaluation Dataset]
    PROPOSE[Mutation Proposer]
    CAND[Candidate Policy / Skill]
    SANDBOX[Sandbox Evaluation]
    SCORE[Quality, Cost, Risk]
    GATE{Лучше baseline?}
    REG[Candidate Registry]
    PROMOTE[Controlled Promotion]
    REJECT[Reject and Archive]

    LOGS --> PROPOSE
    DATASET --> SANDBOX
    PROPOSE --> CAND
    CAND --> SANDBOX
    SANDBOX --> SCORE
    SCORE --> GATE

    GATE -- Да --> REG
    REG --> PROMOTE
    GATE -- Нет --> REJECT
```

### Запрещённый контур

```mermaid
flowchart LR
    PROD[Production Run]
    LLM[LLM предлагает изменение]
    CORE[Немедленно меняет production policy]

    PROD --> LLM --> CORE
```

Такой механизм создаёт дрейф поведения, benchmark overfitting и нерегулируемое изменение security policy.

---

# 13. Потоки данных и хранилища

```mermaid
flowchart TB
    API[API]
    ORCH[Run Orchestrator]
    EVENTS[(Event Log)]
    META[(Run Metadata)]
    GRAPH[(Graph Versions)]
    EVID[(Evidence Store)]
    ART[(Artifact Store)]
    VECTOR[(Retrieval Index)]
    EXP[(Experience Store)]
    METRICS[(Telemetry)]

    API --> ORCH

    ORCH --> EVENTS
    ORCH --> META
    ORCH --> GRAPH
    ORCH --> EVID
    ORCH --> ART
    ORCH --> VECTOR
    ORCH --> EXP
    ORCH --> METRICS

    EVENTS --> REPLAY[Deterministic Replay]
    GRAPH --> REPLAY
    EVID --> REPLAY
```

## Практическая стратегия хранения

Для MVP не требуется отдельная graph database.

Достаточно:

```text
PostgreSQL
├── runs
├── run_events
├── graph_nodes
├── graph_edges
├── graph_versions
├── evidence
├── tool_calls
├── validations
├── approvals
└── skill_specs

Object Storage
├── документы
├── tool artifacts
├── отчёты
└── большие snapshots

Vector Index
├── evidence retrieval
├── pattern retrieval
└── skill retrieval
```

Graph database следует добавлять, когда основная нагрузка действительно смещается к:

* поиску путей;
* графовой композиции skills;
* анализу lineage;
* dependency resolution;
* большим многосвязным картам.

---

# 14. API-контракт

Публичный пример SymFSM ограничивается асинхронными `POST /submit` и `GET /result`, со статусами `queued`, `running`, `done`, `error`. Сам репозиторий обозначен как исследовательский прототип. ([GitHub][2])

Для собственной системы нужен более полный контракт.

```text
POST   /v1/runs
GET    /v1/runs/{run_id}
POST   /v1/runs/{run_id}/cancel

GET    /v1/runs/{run_id}/events
GET    /v1/runs/{run_id}/graph
GET    /v1/runs/{run_id}/plan
GET    /v1/runs/{run_id}/artifacts

POST   /v1/runs/{run_id}/input
POST   /v1/runs/{run_id}/approvals
POST   /v1/runs/{run_id}/feedback

GET    /v1/skills
POST   /v1/skills
POST   /v1/skills/{skill_id}/evaluate

GET    /v1/policies
GET    /v1/ontologies
```

## Статусы Run

```text
received
classifying
modeling
validating_model
repairing
waiting_input
waiting_approval
planning
executing
synthesizing
validating_output
completed
partial
failed
cancelled
```

## Событийный поток

```mermaid
sequenceDiagram
    participant Client
    participant API
    participant Stream as SSE Event Stream
    participant Runtime

    Client->>API: POST /v1/runs
    API-->>Client: run_id

    Client->>Stream: GET /runs/{id}/events
    Runtime-->>Stream: task.interpreted
    Runtime-->>Stream: graph.version.created
    Runtime-->>Stream: validation.failed
    Runtime-->>Stream: repair.started
    Runtime-->>Stream: tool.completed
    Runtime-->>Stream: validation.passed
    Runtime-->>Stream: output.completed
    Stream-->>Client: Последовательность событий
```

---

# 15. Функциональные требования

## P0 — обязательное ядро

| ID   | Требование                                                          |
| ---- | ------------------------------------------------------------------- |
| F-01 | Принимать запрос, ограничения, формат результата и бюджет           |
| F-02 | Преобразовывать запрос в валидируемый `TaskSpec`                    |
| F-03 | Строить типизированный Task Graph                                   |
| F-04 | Версионировать изменения графа                                      |
| F-05 | Проверять достижимость целей                                        |
| F-06 | Обнаруживать missing evidence, contradiction и constraint violation |
| F-07 | Запускать ограниченный repair-loop                                  |
| F-08 | Планировать вызовы инструментов только для конкретных gaps          |
| F-09 | Сохранять provenance каждого внешнего результата                    |
| F-10 | Проверять финальный ответ относительно целей и ограничений          |
| F-11 | Поддерживать partial result при исчерпании бюджета                  |
| F-12 | Записывать полный audit/event log                                   |
| F-13 | Поддерживать отмену и идемпотентность запросов                      |
| F-14 | Требовать approval для необратимых действий                         |

## P1 — развитие

| ID   | Требование                                             |
| ---- | ------------------------------------------------------ |
| F-15 | Рекурсивные подкарты                                   |
| F-16 | Доменный ontology routing                              |
| F-17 | Типизированный Skill Registry                          |
| F-18 | Streaming событий и визуализация графа                 |
| F-19 | Experience retrieval по сигнатуре задачи               |
| F-20 | Детерминированные domain validators                    |
| F-21 | Политики стоимости, latency и риска                    |
| F-22 | Версионирование prompts, policies, ontologies и skills |

## P2 — исследовательский контур

| ID   | Требование                                      |
| ---- | ----------------------------------------------- |
| F-23 | Offline evolution skills и repair policies      |
| F-24 | Graph-based skill composition                   |
| F-25 | Автоматический поиск альтернативных планов      |
| F-26 | Pareto selection по качеству, стоимости и риску |
| F-27 | Cross-agent skill portability                   |
| F-28 | Process mining успешных траекторий              |

---

# 16. Нефункциональные требования

## Надёжность

* Все операции изменения графа транзакционные.
* Каждый GraphPatch может быть отменён.
* Повторный запрос с тем же idempotency key не создаёт второй Run.
* Ошибка одного инструмента не уничтожает состояние задачи.
* Run можно восстановить из event log и graph snapshots.

## Безопасность

* Секреты не попадают в prompts, graph или event payload.
* Инструменты получают краткоживущие credentials.
* Сетевой доступ sandbox ограничивается allowlist.
* Необратимые операции требуют policy gate и approval.
* Загруженные skills проходят подпись, schema validation и локальный eval.
* Tenant data логически и физически изолированы согласно модели развёртывания.

## Наблюдаемость

Для каждого Run фиксируются:

```text
state transitions
graph versions
gaps
repair cycles
tool calls
provider calls
token usage
latency
cost
constraint violations
output validation
approvals
errors
```

## Воспроизводимость

Полный replay должен включать:

```text
model identifier
prompt version
policy version
ontology version
skill version
tool version
input hashes
evidence hashes
random seed, если применим
```

## Производительность

Нужны отдельные бюджеты для:

```text
simple path
cognitive path
tool execution
repair
output verification
```

Система не должна запускать полный когнитивный pipeline для каждого приветствия или простого фактологического запроса.

---

# 17. Complexity Router

```mermaid
flowchart TD
    Q[Новый запрос]
    RISK{Высокий риск?}
    TOOL{Нужны инструменты?}
    MULTI{Есть несколько целей или этапов?}
    CONS{Есть ограничения?}
    AMB{Высокая неоднозначность?}
    DIRECT[Direct LLM Path]
    FULL[Cognitive Runtime]

    Q --> RISK
    RISK -- Да --> FULL
    RISK -- Нет --> TOOL
    TOOL -- Да --> FULL
    TOOL -- Нет --> MULTI
    MULTI -- Да --> FULL
    MULTI -- Нет --> CONS
    CONS -- Да --> FULL
    CONS -- Нет --> AMB
    AMB -- Да --> FULL
    AMB -- Нет --> DIRECT
```

Практические признаки сложной задачи:

* несколько взаимозависимых целей;
* более одного жёсткого ограничения;
* необходимость внешних источников;
* выполнение действий;
* высокая цена ошибки;
* несколько конкурирующих решений;
* необходимость объяснимости;
* противоречивые исходные данные.

---

# 18. Эталонная логика Supervisor

```python
def execute_run(request):
    run = create_run(request)
    route = classify_complexity(request)

    if route == "direct":
        draft = generate_direct(request)
        return verify_and_finalize(run, draft)

    task_spec = interpret_request(request)
    graph = build_initial_graph(task_spec)

    while run.budget.available:
        validation = validate_graph(graph)

        if validation.is_ready:
            break

        gap = select_highest_priority_gap(validation.gaps)
        repair_action = choose_repair(gap, graph, run.policy)

        if repair_action.requires_approval:
            decision = request_approval(repair_action)
            if not decision.approved:
                mark_unresolved(gap)
                continue

        result = execute_repair(repair_action)
        patch = create_graph_patch(result)

        candidate_graph = apply_patch(graph, patch)
        candidate_validation = validate_graph(candidate_graph)

        if improves(candidate_validation, validation):
            graph = commit(candidate_graph)
        else:
            rollback(patch)

        if loop_detected(graph):
            break

    trajectory = select_valid_trajectory(graph)
    draft = synthesize_answer(task_spec, graph, trajectory)

    output_validation = validate_output(draft, graph, task_spec)

    if output_validation.passed:
        persist_experience(run, graph, trajectory)
        return complete(run, draft)

    if run.budget.available:
        return repair_output(run, draft, output_validation)

    return partial(run, draft, output_validation)
```

---

# 19. MVP-архитектура

Для первого рабочего вертикального сценария следует ограничить систему одним доменом, например:

```text
архитектурный анализ
или
исследовательский ответ с источниками
```

```mermaid
flowchart LR
    API[Fast API Layer]
    SUP[Run Supervisor]
    PARSER[LLM Task Parser]
    GRAPH[Task Graph]
    VAL[Deterministic Validators]
    REPAIR[Repair Policy]
    SEARCH[Search / RAG]
    TOOL[2-3 Tools]
    GEN[LLM Synthesizer]
    OUT[Output Validator]
    DB[(PostgreSQL)]
    OBJ[(Artifact Store)]

    API --> SUP
    SUP --> PARSER
    PARSER --> GRAPH
    GRAPH --> VAL
    VAL --> REPAIR
    REPAIR --> SEARCH
    REPAIR --> TOOL
    SEARCH --> GRAPH
    TOOL --> GRAPH
    GRAPH --> GEN
    GEN --> OUT

    SUP --> DB
    GRAPH --> DB
    SEARCH --> OBJ
    TOOL --> OBJ
```

## Не включать в первый MVP

* универсальную онтологию всех доменов;
* многоагентную колонию;
* сложную 30-мерную модель состояния;
* автоматическую онлайн-эволюцию;
* произвольный исполняемый код из marketplace;
* глубокую рекурсивность;
* собственный язык логического доказательства;
* отдельную graph database без подтверждённой необходимости.

---

# 20. Этапы развития

```mermaid
flowchart LR
    M0["M0: TaskSpec + FSM"]
    M1["M1: Task Graph + Validators"]
    M2["M2: Repair + Tools"]
    M3["M3: Evidence + Output Verification"]
    M4["M4: Skill Registry"]
    M5["M5: Experience Retrieval"]
    M6["M6: Offline Evolution"]
    M7["M7: Multi-domain Runtime"]

    M0 --> M1 --> M2 --> M3 --> M4 --> M5 --> M6 --> M7
```

### M0

* асинхронный Run;
* FSM;
* event log;
* бюджеты;
* direct/full routing.

### M1

* схемы узлов и связей;
* versioned graph;
* reachability;
* constraint validation.

### M2

* классификация gaps;
* repair policies;
* tool adapters;
* retry/fallback;
* approval.

### M3

* provenance;
* evidence ledger;
* claim coverage;
* final output verifier.

### M4

* типизированные SkillSpec;
* local bindings;
* sandbox;
* risk gate;
* trust/signatures.

### M5

* поиск похожих graph patterns;
* reuse успешных repair;
* process metrics.

### M6

* mutation proposals;
* held-out evaluation;
* Pareto selection;
* controlled promotion.

### M7

* доменные онтологии;
* subgraphs;
* специализированные validators;
* масштабируемая графовая инфраструктура.

---

# 21. Критерии готовности

Система считается работоспособной, когда выполняются следующие инварианты:

```text
1. Каждый Run имеет воспроизводимую последовательность событий.
2. Каждая версия графа неизменяема после фиксации.
3. Каждый фактический вывод имеет provenance или статус hypothesis.
4. Каждый tool call связан с конкретным Gap или Action.
5. Ни одно необратимое действие не выполняется без policy gate.
6. Repair не может выполняться бесконечно.
7. Финальный ответ покрывает заявленные цели.
8. Нарушенные ограничения явно отражаются в результате.
9. При недостатке данных возвращается partial, а не выдуманное завершение.
10. Изменения skills и policies не попадают в production без eval.
```

## Метрики качества

| Метрика                 | Что измеряет                              |
| ----------------------- | ----------------------------------------- |
| Goal coverage           | Доля закрытых целей                       |
| Constraint compliance   | Соблюдение ограничений                    |
| Evidence coverage       | Подтверждённость фактических утверждений  |
| Repair success rate     | Доля успешно устранённых gaps             |
| Unsupported claim rate  | Неподтверждённые утверждения              |
| Tool efficiency         | Полезные вызовы относительно всех вызовов |
| Cost per successful run | Стоимость успешного решения               |
| Latency per run class   | Задержка по типам задач                   |
| Regression rate         | Деградация после изменений                |
| Human intervention rate | Частота запросов approval/clarification   |

---

# Итоговая конструкция

```mermaid
flowchart TB
    REQUEST[Запрос]
    SPEC[TaskSpec]
    TG[Task Graph]
    CHECK[Structural and Evidence Validation]
    GAP{Есть критические gaps?}
    PG[Plan Graph]
    EXEC[Typed Skill and Tool Runtime]
    UPDATE[Graph Update]
    PATH[Verified Trajectory]
    SYNTH[LLM Synthesis]
    OUT[Output Verification]
    RESULT[Answer / Partial / Failure]
    EXP[Experience and Offline Evaluation]

    REQUEST --> SPEC
    SPEC --> TG
    TG --> CHECK
    CHECK --> GAP

    GAP -- Да --> PG
    PG --> EXEC
    EXEC --> UPDATE
    UPDATE --> CHECK

    GAP -- Нет --> PATH
    PATH --> SYNTH
    SYNTH --> OUT
    OUT -->|Pass| RESULT
    OUT -->|Repairable| PG
    OUT -->|Budget exhausted| RESULT

    RESULT --> EXP
    EXP -. validated patterns .-> SPEC
    EXP -. promoted skills .-> EXEC
```

**Целевая архитектурная формула проекта:**

> **FSM управляет процессом, Task Graph моделирует проблему, Plan Graph моделирует действия, validators определяют допустимость, repair закрывает gaps, skills и инструменты исполняют план, LLM интерпретирует и формулирует, а offline evaluation улучшает систему без неконтролируемого самоизменения.**

[1]: https://principium.pro/ru/symfsm-2/ "Скачать SymFSM приложение для Windows. Официальная страница"
[2]: https://github.com/likeslines-maker/SymFSMExamples "GitHub - likeslines-maker/SymFSMExamples: From Text Generation to Computable Reasoning · GitHub"
