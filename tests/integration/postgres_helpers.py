"""Helpers for Postgres-backed integration tests."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import AsyncGenerator
from urllib.parse import urlparse, urlunparse

from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from onboarding.config import PROJECT_ROOT, get_settings
from onboarding.decision.engine import RulesDecisionEngine
from onboarding.events.bootstrap import build_orchestrator_registry, wire_event_system
from onboarding.events.bus.in_process import InProcessEventBus
from onboarding.events.handlers.coordinator import FlowCoordinatorHandler
from onboarding.events.handlers.decision import DecisionHandler
from onboarding.events.handlers.integration import IntegrationHandler
from onboarding.events.handlers.trace import TraceProjectionHandler
from onboarding.events.outbox.publisher import OutboxPublisher
from onboarding.events.outbox.repository import PostgresOutboxRepository
from onboarding.events.router import TraceTableRouter
from onboarding.flow.engine import FlowEngine
from onboarding.flow.provider import YamlFlowDefinitionProvider
from onboarding.integrations.gateway import MockIntegrationGateway
from onboarding.persistence.repository import PostgresApplicationRepository
from onboarding.persistence.segment_repository import PostgresSegmentRepository
from onboarding.services.command_service import OnboardingCommandService
from onboarding.services.facade import OnboardingFacade
from onboarding.services.query_service import OnboardingQueryService
from onboarding.services.resume_service import PostgresResumeTokenService

DEFAULT_TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/onboarding_test"

TRUNCATE_TABLES = (
    "event_outbox",
    "flow_segments",
    "decision_trace",
    "integration_trace",
    "flow_trace",
    "resume_tokens",
    "audit_events",
    "integration_results",
    "step_submissions",
    "onboarding_applications",
)


def get_test_database_url() -> str:
    return os.getenv("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)


def admin_database_url(database_url: str) -> str:
    """Connect to the maintenance DB to create the test database if needed."""
    parsed = urlparse(database_url.replace("+asyncpg", ""))
    maintenance = parsed._replace(path="/postgres")
    return urlunparse(maintenance)


def test_db_name(database_url: str) -> str:
    return urlparse(database_url.replace("+asyncpg", "")).path.lstrip("/") or "onboarding_test"


async def postgres_is_reachable(database_url: str) -> bool:
    try:
        engine = create_async_engine(database_url, pool_pre_ping=True)
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        await engine.dispose()
        return True
    except Exception:
        return False


async def ensure_test_database(database_url: str) -> None:
    db_name = test_db_name(database_url)
    admin_url = admin_database_url(database_url)
    engine = create_async_engine(admin_url.replace("postgresql://", "postgresql+asyncpg://"))
    async with engine.connect() as conn:
        exists = await conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": db_name},
        )
        if exists.scalar() is None:
            await conn.execute(text("COMMIT"))
            await conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    await engine.dispose()


def run_migrations(database_url: str) -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=PROJECT_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


async def truncate_all_tables(session: AsyncSession) -> None:
    tables = ", ".join(TRUNCATE_TABLES)
    await session.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    await session.commit()


def truncate_all_tables_sync(database_url: str) -> None:
    sync_url = database_url.replace("+asyncpg", "")
    engine = create_engine(sync_url, pool_pre_ping=True)
    with engine.begin() as conn:
        tables = ", ".join(TRUNCATE_TABLES)
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    engine.dispose()


def count_applications_sync(database_url: str, application_id) -> int:
    sync_url = database_url.replace("+asyncpg", "")
    engine = create_engine(sync_url, pool_pre_ping=True)
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT COUNT(*) FROM onboarding_applications WHERE id = :id"),
            {"id": str(application_id)},
        )
        count = result.scalar_one()
    engine.dispose()
    return count


def list_segments_sync(database_url: str, application_id) -> list[dict]:
    sync_url = database_url.replace("+asyncpg", "")
    engine = create_engine(sync_url, pool_pre_ping=True)
    with engine.connect() as conn:
        rows = (
            conn.execute(
                text("SELECT segment_key, status FROM flow_segments WHERE application_id = :id"),
                {"id": str(application_id)},
            )
            .mappings()
            .all()
        )
    engine.dispose()
    return [dict(row) for row in rows]


def create_session_factory(database_url: str):
    engine = create_async_engine(database_url, pool_pre_ping=True, pool_size=5, max_overflow=5)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, factory


async def build_postgres_facade(
    session: AsyncSession,
    *,
    orchestrator_registry=None,
) -> OnboardingFacade:
    """Wire OnboardingFacade the same way as web/deps.py (real Postgres repos)."""
    settings = get_settings()
    provider = YamlFlowDefinitionProvider(settings.flows_dir)
    flow_engine = FlowEngine(provider)
    gateway = MockIntegrationGateway()
    rules_dir = PROJECT_ROOT / "src" / "onboarding" / "decision" / "rules"
    decision_engine = RulesDecisionEngine(rules_dir)

    repo = PostgresApplicationRepository(session)
    segments = PostgresSegmentRepository(session)
    event_router = TraceTableRouter(session)
    resume_tokens = PostgresResumeTokenService(session)

    outbox = PostgresOutboxRepository(session)
    bus = InProcessEventBus()
    publisher = OutboxPublisher(outbox, bus, session=session)
    orchestrators = orchestrator_registry or build_orchestrator_registry(settings.flows_dir)

    async def abandon(device_id: str) -> None:
        abandoned = await repo.abandon_drafts_for_device(device_id)
        for app_id in abandoned:
            await resume_tokens.revoke_for_application(app_id)

    coordinator = FlowCoordinatorHandler(
        repo, segments, flow_engine, orchestrators, publisher, resume_tokens
    )
    integration = IntegrationHandler(repo, gateway, publisher)
    trace = TraceProjectionHandler(event_router)
    decision = DecisionHandler(repo, decision_engine, publisher, resume_tokens)
    wire_event_system(
        bus,
        {
            "coordinator": coordinator,
            "integration": integration,
            "trace": trace,
            "decision": decision,
        },
    )

    command = OnboardingCommandService(
        repo,
        flow_engine,
        publisher,
        resume_tokens,
        settings.available_flows,
        legacy_abandon=abandon,
    )
    query = OnboardingQueryService(repo, segments, flow_engine, event_router, resume_tokens)
    facade = OnboardingFacade(command, query, event_driven=True)
    facade._session = session  # type: ignore[attr-defined]
    return facade


async def db_session_override(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    async with factory() as session:
        yield session
