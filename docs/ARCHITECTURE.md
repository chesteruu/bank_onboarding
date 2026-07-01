# Architecture

Event-driven onboarding with a **bus-agnostic core**, **transactional outbox**, and a **two-level flow model** (shell + components). The web layer never orchestrates directly — it publishes commands and reads projections.

## Swimlane diagrams

These diagrams show **who does what** across lanes. They complement the component map below and match the current in-process bus + Postgres outbox implementation (handlers are unchanged when the bus becomes AWS-native — see [AWS migration](AWS_MIGRATION.md)).

### 1. Start application (landing → first step)

```mermaid
sequenceDiagram
    box Applicant
        participant Browser
    end
    box Web
        participant Routes
        participant Facade
    end
    box Commands
        participant Cmd as CommandService
    end
    box Persistence
        participant DB as Postgres
        participant Resume as ResumeTokens
    end

    Browser->>Routes: GET /
    Routes->>Facade: resume_by_device(cookie)
    Facade->>DB: latest draft by device_id
    alt Draft exists
        DB-->>Routes: application
        Routes-->>Browser: resume_prompt.html
    else No draft
        Routes-->>Browser: landing.html
        Browser->>Routes: POST select-type
        Routes-->>Browser: select_country.html
        Browser->>Routes: POST /onboarding/start
        Routes->>Facade: start_application(country, type, device_id)
        Facade->>Cmd: start_application
        Cmd->>DB: abandon prior device drafts
        Cmd->>DB: create application + first step
        Cmd->>Resume: create_token(resumption_data)
        Cmd->>DB: outbox APPLICATION_STARTED
        Routes-->>Browser: 303 → step/identity
    end
```

### 2. Step submit → integration → shell advance (core loop)

Only **FlowCoordinatorHandler** writes `current_step_key`. Component orchestrators update **flow_segments** only.

```mermaid
sequenceDiagram
    box Applicant
        participant Browser
    end
    box Web
        participant Routes
        participant Facade
    end
    box Commands
        participant Cmd as CommandService
    end
    box Outbox
        participant Outbox
        participant Bus as InProcessEventBus
    end
    box Coordinator
        participant Coord as FlowCoordinator
        participant Orch as YamlComponentOrchestrator
    end
    box Workers
        participant IntH as IntegrationHandler
        participant Trace as TraceProjection
    end
    box Persistence
        participant DB as Postgres
    end
    box External
        participant GW as IntegrationGateway
    end

    Browser->>Routes: POST step/{key}
    Routes->>Facade: submit_step
    Facade->>Cmd: submit_step
    Cmd->>DB: save step_submission
    Cmd->>Outbox: enqueue STEP_SUBMITTED
    Outbox->>Bus: flush
    Bus->>Coord: handle
    Bus->>Trace: handle
    Coord->>Orch: on_step_submitted / on_subflow_started
    Orch->>DB: upsert flow_segment
    Orch-->>Coord: pending_integrations
    Coord->>Outbox: INTEGRATION_REQUESTED
    Outbox->>Bus: flush
    Bus->>IntH: handle
    IntH->>GW: run_checks
    GW-->>IntH: IntegrationResult
    IntH->>DB: save integration_result
    IntH->>Outbox: INTEGRATION_COMPLETED
    Outbox->>Bus: flush
    Bus->>Coord: handle
    Coord->>Orch: on_integration_completed
    Orch-->>Coord: subflow completed
    Coord->>Outbox: SUB_FLOW_COMPLETED
    Outbox->>Bus: flush
    Bus->>Coord: advance shell
    Coord->>DB: update current_step_key
    Coord->>DB: sync resume token
    Routes-->>Browser: 303 → next step or /processing
```

### 3. Async UX while segment work runs

Today the in-process bus usually finishes before redirect. With a real broker (or slow integrations), the applicant waits on `/processing` while projections catch up.

```mermaid
sequenceDiagram
    box Applicant
        participant Browser
    end
    box Web
        participant Routes
        participant Facade
    end
    box Query
        participant Qry as QueryService
    end
    box Persistence
        participant DB as Postgres
    end

    Browser->>Routes: GET /processing
    Routes->>Facade: get_status
    Facade->>Qry: get_status
    Qry->>DB: application + flow_segments
    Qry-->>Browser: processing.html + progress JSON

    loop SSE or poll
        Browser->>Routes: GET /events (SSE) or /status
        Routes->>Facade: get_status
        Facade->>Qry: get_status
        Qry->>DB: read segments + ready flag
        Qry-->>Browser: main_progress, active_segment
    end

    Note over Browser,DB: ready=true → redirect to current_step_key
```

### 4. Review, decision, and resume token lifecycle

```mermaid
sequenceDiagram
    box Applicant
        participant Browser
    end
    box Web
        participant Routes
        participant Facade
    end
    box Commands
        participant Cmd as CommandService
    end
    box Outbox
        participant Outbox
        participant Bus as InProcessEventBus
    end
    box Workers
        participant DecH as DecisionHandler
        participant Trace as TraceProjection
    end
    box Persistence
        participant DB as Postgres
        participant Resume as ResumeTokens
    end

    Browser->>Routes: POST review (confirm)
    Routes->>Facade: finalize_application
    Facade->>Cmd: finalize_application
    Cmd->>Outbox: DECISION_REQUESTED
    Outbox->>Bus: flush
    Bus->>DecH: handle
    DecH->>DB: load integrations + answers
    DecH->>DecH: RulesDecisionEngine.evaluate
    DecH->>DB: update status + final_decision
    DecH->>Resume: revoke_for_application
    DecH->>Outbox: DECISION_COMPLETED
    Outbox->>Bus: flush
    Bus->>Trace: handle
    Routes-->>Browser: result.html
```

### 5. Go back one step (resume sync)

```mermaid
sequenceDiagram
    box Applicant
        participant Browser
    end
    box Web
        participant Routes
        participant Facade
    end
    box Commands
        participant Cmd as CommandService
    end
    box Persistence
        participant DB as Postgres
        participant Resume as ResumeTokens
    end

    Browser->>Routes: POST step/{key}/back
    Routes->>Facade: go_back
    Facade->>Cmd: go_back
    alt First shell step
        Cmd-->>Routes: redirect /select-country
    else Previous step exists
        Cmd->>DB: update current_step_key
        Cmd->>Resume: sync_resumption(new step)
        Cmd-->>Routes: redirect previous step
    end
    Routes-->>Browser: 303
```

### Swimlane responsibility matrix

| Lane | Owns | Must not |
|------|------|----------|
| **Applicant / Browser** | Form input, cookies | Advance steps directly |
| **Web / Routes** | HTTP, templates, i18n | Call integrations or change `current_step_key` |
| **CommandService** | Submissions, outbox enqueue, go_back pointer | Render UI |
| **QueryService** | Read models, status, review data | Mutate aggregate |
| **Outbox + Bus** | Durable delivery, handler dispatch | Business rules |
| **FlowCoordinator** | Shell pointer, segment start, integration requests | Shell-level integration calls |
| **Component orchestrator** | Internal step logic inside a segment | Update shell pointer |
| **IntegrationHandler** | External checks, `integration_results` | Advance shell |
| **DecisionHandler** | Final outcome, revoke resume tokens | Change flow YAML |
| **TraceProjection** | Audit tables | Application state |

## High-level view

```mermaid
flowchart TB
    subgraph api [API layer]
        Web[Routes and templates]
        Facade[OnboardingFacade]
        Cmd[OnboardingCommandService]
        Qry[OnboardingQueryService]
    end

    subgraph bus [Event bus]
        Outbox[(event_outbox)]
        EventBus[IEventBus]
    end

    subgraph handlers [Handlers]
        Coord[FlowCoordinatorHandler]
        IntH[IntegrationHandler]
        DecH[DecisionHandler]
        TraceH[TraceProjectionHandler]
    end

    subgraph orch [Component orchestrators]
        IdOrch[YamlComponentOrchestrator]
        CredOrch[YamlComponentOrchestrator]
        KybOrch[YamlComponentOrchestrator]
        OtherOrch[Other orchestrators]
    end

    subgraph state [Read models]
        App[(onboarding_applications)]
        Seg[(flow_segments)]
        IntRes[(integration_results)]
        Traces[(flow / integration / decision trace)]
    end

    Web --> Facade
    Facade --> Cmd
    Facade --> Qry
    Cmd --> Outbox
    Cmd --> App
    Outbox --> EventBus
    EventBus --> Coord
    EventBus --> IntH
    EventBus --> DecH
    EventBus --> TraceH
    Coord --> IdOrch
    Coord --> CredOrch
    Coord --> KybOrch
    Coord --> OtherOrch
    IdOrch --> Seg
    CredOrch --> Seg
    Coord --> App
    IntH --> IntRes
    Qry --> App
    Qry --> Seg
    TraceH --> Traces
```

## Request lifecycle (step submit)

```mermaid
sequenceDiagram
    participant Web
    participant Cmd as CommandService
    participant Outbox
    participant Bus as InProcessEventBus
    participant Coord as FlowCoordinator
    participant Orch as ComponentOrchestrator
    participant IntH as IntegrationHandler
    participant DB as Postgres

    Web->>Cmd: submit_step
    Cmd->>DB: save step_submission
    Cmd->>Outbox: STEP_SUBMITTED
    Outbox->>Bus: flush
    Bus->>Coord: handle
    Coord->>Orch: on_step_submitted / on_subflow_started
    Orch-->>Coord: pending_integrations
    Coord->>Outbox: INTEGRATION_REQUESTED
    Outbox->>Bus: flush
    Bus->>IntH: handle
    IntH->>DB: save integration_result
    IntH->>Outbox: INTEGRATION_COMPLETED
    Outbox->>Bus: flush
    Bus->>Coord: handle
    Coord->>Orch: on_integration_completed
    Orch-->>Coord: completed
    Coord->>Outbox: SUB_FLOW_COMPLETED
    Outbox->>Bus: flush
    Bus->>Coord: advance shell step
    Coord->>DB: update current_step_key
```

**Important:** `FlowCoordinatorHandler` is the **only** writer of `onboarding_applications.current_step_key`. Component orchestrators update `flow_segments` only.

## Two-level flow model

### Shell flow (`flows/{country}_{type}.yaml`)

Defines **which components run, in what order**, plus UI metadata:

| Field | Required | Purpose |
|-------|----------|---------|
| `key` | yes | Shell step id (e.g. `credit_decision`) |
| `title` | yes | UI heading |
| `orchestrator` | yes* | Registry id (`identity`, `credit`, …) |
| `component_flow` | yes* | Path under `flows/` (e.g. `components/credit/se_private.yaml`) |
| `form_schema` | if form step | Pydantic schema name in `web/forms.py` |
| `on_complete` | yes | Next shell step key |
| `is_review` | review only | Renders review template |
| `triggers_decision` | decision only | Runs decision rules on finalize |

\*Review/decision steps use shared component YAML; form steps need `form_schema`.

### Component flow (`flows/components/{orchestrator}/…`)

Defines **internal steps and integrations** for one capability:

| Field | Purpose |
|-------|---------|
| `component_id` | Stable id (e.g. `se_private_credit`) |
| `orchestrator` | Must match shell `orchestrator` and registry id |
| `internal_steps[]` | Ordered internal work units |
| `internal_steps[].integrations` | Keys routed by `MockIntegrationGateway` |
| `internal_steps[].optional` | Skip internal step without shell change |

All components use `YamlComponentOrchestrator` — **no new Python class** unless behaviour cannot be expressed in YAML.

## Event model

Envelope: `EventEnvelope` (`domain/events/envelope.py`). Types: `EventType` (`domain/events/catalog.py`).

| Event | Publisher | Consumer |
|-------|-----------|----------|
| `STEP_SUBMITTED` | CommandService | FlowCoordinator |
| `SUB_FLOW_STARTED` | Coordinator | Trace |
| `INTEGRATION_REQUESTED` | Coordinator | IntegrationHandler, Trace |
| `INTEGRATION_COMPLETED` | IntegrationHandler | Coordinator, Trace |
| `SUB_FLOW_COMPLETED` | Coordinator | Coordinator (advance), Trace |
| `MAIN_PROGRESS_UPDATED` | Coordinator | Trace, UI projection |
| `DECISION_REQUESTED` | CommandService | DecisionHandler |

Routing keys: `onboarding.{flow_id}.{event}` or `onboarding.component.{orchestrator_id}.{flow_id}.{event}`.

### Transactional outbox

| Piece | Role |
|-------|------|
| `event_outbox` table | Durable event queue |
| `OutboxPublisher` | Enqueue + flush to bus on submit, `/status`, SSE |
| `InProcessEventBus` | Dev/test adapter; pattern subscriptions |

Production: replace `InProcessEventBus` with a broker consumer; handlers stay the same. See [AWS migration guide](AWS_MIGRATION.md) for EventBridge + SQS layout and on-demand scaling.

## Progress model

```mermaid
flowchart LR
    subgraph main [Main progress]
        Done[Completed shell steps]
        Active[Active segment percent]
    end

    Done --> Formula["main_percent = done/total * 100 + active/total"]
    Active --> Formula
```

| Store | Purpose |
|-------|---------|
| `onboarding_applications.current_step_key` | Shell pointer (coordinator only) |
| `flow_segments` | Per-step orchestrator state, internal step, percent, status |

Aggregate formula:

```
main_percent = (completed_shell_steps / total_shell_steps) * 100
             + (active_segment.percent / total_shell_steps)
```

## Module map

| Package | Responsibility |
|---------|----------------|
| `domain/` | Models, enums, `domain/events/` |
| `interfaces/` | Protocols: repo, bus, orchestrator, outbox, segments |
| `flow/` | Shell provider, component provider, engine, orchestrators, progress |
| `events/` | Bus, outbox, handlers, bootstrap |
| `integrations/` | Gateway + mock clients |
| `decision/` | Rules engine + YAML rules |
| `persistence/` | ORM, repos, segments, outbox |
| `services/` | Command, query, facade (+ legacy `OnboardingService`) |
| `web/` | Routes, forms, templates, DI |

## Persistence

| Table | Purpose |
|-------|---------|
| `onboarding_applications` | Application aggregate |
| `step_submissions` | Form answers per shell step |
| `integration_results` | Check outcomes |
| `flow_segments` | Component progress projection |
| `event_outbox` | Transactional outbox |
| `flow_trace`, `integration_trace`, `decision_trace` | Audit projections |
| `resume_tokens` | Token-based resume |

Migrations: `alembic/versions/` (001–007).

## Async applicant UX

| Endpoint | Returns |
|----------|---------|
| `GET /onboarding/{id}/status` | `ready`, `main_progress`, `active_segment`, `segments[]` |
| `GET /onboarding/{id}/events` | SSE stream |
| `GET /onboarding/{id}/processing` | Polling page |

In-process bus completes synchronously on submit; `/processing` mainly matters when a real async broker is introduced.

## Dependency injection

`web/deps.py` wires per-request Postgres session, builds event bus + handlers, returns `OnboardingFacade`.

`main.py` lifespan registers `OrchestratorRegistry` on `app.state`.

Tests: `build_event_facade()` (in-memory) or `build_postgres_facade()` (Postgres e2e).

## Feature flag

`Settings.event_driven_enabled` (default `true`):

- **true** — Command/query facade, outbox, coordinator (recommended)
- **false** — Legacy sync `OnboardingService` (deprecated; shell YAML is component-oriented)

## Tradeoffs

| Choice | Rationale |
|--------|-----------|
| Shell + component YAML | Add/remove capabilities without monolithic flow edits |
| In-process bus + outbox | No background worker on Vercel; flush on request |
| Postgres read models | Simpler than full event sourcing |
| Monorepo handlers | Extract to Lambdas / consumer groups later |
| Generic YamlComponentOrchestrator | One implementation; YAML drives behaviour |

## Security (demo)

- No auth, no rate limits
- Resume tokens: UUID + TTL (production: HMAC / hash at rest)
- Device cookie: HttpOnly, SameSite=Lax
- PII redacted in trace metadata
