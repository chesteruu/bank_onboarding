# Architecture

Event-driven onboarding with a **bus-agnostic core**, **transactional outbox**, and a **two-level flow model** (shell + components). The web layer never orchestrates directly — it publishes commands and reads projections.

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

Production: replace `InProcessEventBus` with a broker consumer; handlers stay the same.

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
