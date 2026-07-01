# Banko Onboarding App

Event-driven, interface-first FastAPI onboarding for **3 countries × 2 account types** (SE / ES / PL × private / business). Each market is composed from a thin **shell flow** plus reusable **component sub-flows** (identity, credit, KYB, …). Commands publish domain events through a Postgres outbox; a coordinator and component orchestrators advance progress and persist segment state.

## Documentation

| Document | Contents |
|----------|----------|
| [Architecture](docs/ARCHITECTURE.md) | Event bus, coordinator model, **swimlane diagrams**, persistence |
| [AWS migration](docs/AWS_MIGRATION.md) | **AWS-native target**, outbox relay, **on-demand scaling** |
| [Flows guide](docs/FLOWS_GUIDE.md) | **How to add a country, shell flow, or component sub-flow** |
| [Agent skill](.cursor/skills/onboarding-flows/SKILL.md) | LLM rulebook — safe patterns for YAML / flow changes |

## Stack

- **FastAPI** + **Jinja2** (server-rendered steps)
- **SQLAlchemy 2 async** + **Alembic** + **PostgreSQL**
- **Event-driven core** — transactional outbox, in-process bus (Kafka/EventBridge-ready)
- **Pydantic v2** forms · **YAML** shell + component flows
- **pytest** + **httpx** + optional **Postgres e2e**

## Features

- **Two-level flows** — shell YAML defines step order; component YAML owns integrations and internal progress
- **Segment progress** — `flow_segments` table + `/status` + SSE for async UX
- **Account-type-first landing** with configurable country allow-list via `i18n/markets.yaml`
- **Config-based i18n** — per-country locale and translation bundles under `i18n/bundles/`
- **Device cookie + resume tokens** (24h TTL, single-use)
- **Duplicate-draft detection** on identity identifiers
- **Trace tables** — flow, integration, and decision audit projections
- **Admin dashboard** with segment breakdown per application

## Quick start

### Prerequisites

- Python 3.10+
- Docker (recommended) or PostgreSQL

### Setup

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

python -m pip install --upgrade pip
pip install -e ".[dev]"

cp .env.example .env
```

### Git hooks (lint + mypy)

Every commit runs **ruff** (lint + format) and **mypy** via [pre-commit](https://pre-commit.com/):

```bash
# Windows
.\scripts\install-hooks.ps1

# macOS / Linux
./scripts/install-hooks.sh
```

Or manually: `pre-commit install`

Run checks without committing:

```bash
pre-commit run --all-files
```

### Database (Docker — recommended)

```bash
docker compose up -d postgres
alembic upgrade head
```

- App DB: `onboarding` (see `DATABASE_URL` in `.env.example`)
- Test DB: `onboarding_test` (created automatically on first container init)

### Run the app

```bash
uvicorn main:app --reload --port 8001
```

Open http://127.0.0.1:8001

### Run tests

```bash
pytest -m "not postgres"    # unit + in-memory integration (no DB)
pytest -m postgres            # Postgres e2e (requires Docker)
pytest                        # all tests (74+)
```

Postgres tests skip automatically when the database is unreachable.

## Environment variables

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | Async Postgres URL, e.g. `postgresql+asyncpg://postgres:postgres@localhost:5432/onboarding` |
| `TEST_DATABASE_URL` | Test DB for `pytest -m postgres` (default: `.../onboarding_test`) |
| `DEBUG` | SQL echo when `true` |

Other settings live in `src/onboarding/config.py` (`Settings`):

| Setting | Default | Purpose |
|---------|---------|---------|
| `event_driven_enabled` | `true` | Event bus + outbox path (recommended) |
| `available_flows` | from `i18n/markets.yaml` | Enabled countries per account type |
| `device_cookie_name` | `onboarding_device_id` | Resume cookie |
| `device_cookie_max_age_days` | `90` | Cookie TTL |

## Shell flows (current)

| Flow | Shell steps |
|------|-------------|
| **SE private** | identity → contact → consent → financial → credit_decision → review → decision |
| **ES / PL private** | Same pattern as SE private |
| **SE business** | company → signatory → ubo → financial → kyb_decision → credit_decision → review → decision |
| **ES business** | company → representative → ubo → financial → kyb_decision → credit_decision → bank_verification → review → decision |
| **PL business** | company → board → ubo → financial → kyb_decision → credit_decision → bank_verification → review → decision |

Shell files: [`flows/`](flows/). Component internals: [`flows/components/`](flows/components/).

## API routes

| Route | Purpose |
|-------|---------|
| `GET /` | Landing or resume prompt |
| `POST /onboarding/start` | Create application |
| `GET /onboarding/{id}/step/{key}` | Render step or review |
| `POST /onboarding/{id}/step/{key}` | Submit step (may redirect to `/processing`) |
| `GET /onboarding/{id}/status` | JSON progress + segments |
| `GET /onboarding/{id}/events` | SSE progress stream |
| `GET /onboarding/{id}/processing` | Polling page while segment work runs |
| `GET /onboarding/resume/{token}` | Resume via token link |
| `POST /onboarding/start-over` | Abandon drafts, rotate device id |
| `/admin/*` | Admin dashboard |

## Demo magic identifiers

| Pattern | Outcome |
|---------|---------|
| ID / PESEL / company no. ending `0000` | Manual review |
| Ending `9999` | Rejection |
| Ending `8888` | Expired ID / unreachable provider |
| Name contains `pep` | Possible sanctions hit |
| Name contains `sanction` | Confirmed sanctions hit |
| Expenses ≥ income | Credit / affordability fail |

Happy-path SE private: `199001011234`, `Anna Andersson`.

## Deploy to Vercel

1. Provision Neon Postgres (Vercel Marketplace).
2. Set `DATABASE_URL` (pooled, `+asyncpg` prefix).
3. Run `alembic upgrade head` against Neon before deploy.
4. Deploy — `vercel.json` routes to `main.py`.

Migrations run outside cold starts. Outbox events flush on HTTP poll/SSE (no background worker on Vercel).

## Adding a new market

See **[docs/FLOWS_GUIDE.md](docs/FLOWS_GUIDE.md)** for the full checklist. Summary:

1. Add `Country` enum value (if new country code)
2. Create shell YAML `flows/{cc}_{type}.yaml`
3. Add or reuse component YAML under `flows/components/{orchestrator}/`
4. Register form schema + template (if new fields)
5. Add decision rules `src/onboarding/decision/rules/{flow_id}.yaml`
6. Enable country in `i18n/markets.yaml` and add `i18n/bundles/{CC}.yaml`
7. Add tests

When using an LLM, point it at **[.cursor/skills/onboarding-flows/SKILL.md](.cursor/skills/onboarding-flows/SKILL.md)** first.

## Assumptions (demo scope)

- No real external APIs; mock integrations only
- No authentication or rate limiting
- PII redacted in traces; answers stored as JSON (no field-level encryption)
