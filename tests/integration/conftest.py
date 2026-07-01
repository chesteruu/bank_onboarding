import os

import pytest
from fakes import build_event_facade

from onboarding.config import get_settings
from integration.postgres_helpers import (
    admin_database_url,
    create_session_factory,
    ensure_test_database,
    get_test_database_url,
    postgres_is_reachable,
    run_migrations,
    truncate_all_tables_sync,
)


@pytest.fixture
def service():
    """In-memory event-driven facade (no Postgres)."""
    return build_event_facade()


@pytest.fixture(scope="session")
def test_database_url() -> str:
    return get_test_database_url()


@pytest.fixture(scope="session")
def postgres_ready(test_database_url: str) -> str:
    """Ensure Postgres is up, test DB exists, and migrations are applied."""
    import asyncio

    admin_async = admin_database_url(test_database_url).replace(
        "postgresql://", "postgresql+asyncpg://"
    )
    if not asyncio.run(postgres_is_reachable(admin_async)):
        pytest.skip(
            "Postgres is not running. Start it with: docker compose up -d postgres"
        )

    asyncio.run(ensure_test_database(test_database_url))
    run_migrations(test_database_url)
    get_settings.cache_clear()
    os.environ.setdefault("DATABASE_URL", test_database_url)
    return test_database_url


@pytest.fixture
async def pg_session(postgres_ready: str):
    """Fresh async session per test; tables truncated before each test."""
    truncate_all_tables_sync(postgres_ready)
    engine, factory = create_session_factory(postgres_ready)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture
async def pg_service(pg_session):
    """Event-driven facade backed by real Postgres."""
    from integration.postgres_helpers import build_postgres_facade

    return await build_postgres_facade(pg_session)


@pytest.fixture
def pg_http_client(postgres_ready: str):
    """TestClient with Postgres-backed deps; truncates before each test."""
    import asyncio

    from fastapi.testclient import TestClient

    from main import create_app
    from onboarding.persistence.database import get_db_session
    from integration.postgres_helpers import db_session_override

    truncate_all_tables_sync(postgres_ready)
    engine, factory = create_session_factory(postgres_ready)

    async def override_get_db_session():
        async for session in db_session_override(factory):
            yield session

    app = create_app()
    app.dependency_overrides[get_db_session] = override_get_db_session

    with TestClient(app) as client:
        client.test_database_url = postgres_ready  # type: ignore[attr-defined]
        yield client

    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())
