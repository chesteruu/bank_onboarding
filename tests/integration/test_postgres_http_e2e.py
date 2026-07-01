"""HTTP end-to-end tests against real Postgres (requires Docker Compose)."""

import re
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from integration.postgres_helpers import count_applications_sync, list_segments_sync

pytestmark = pytest.mark.postgres

IDENTITY = {
    "national_id": "199001011234",
    "full_name": "Anna Andersson",
    "date_of_birth": "1990-01-01",
}


def _extract_application_id(location: str) -> UUID:
    match = re.search(r"/onboarding/([0-9a-f-]{36})/", location)
    assert match, f"No application id in Location: {location}"
    return UUID(match.group(1))


def test_http_postgres_start_persists_application(pg_http_client: TestClient, postgres_ready: str):
    response = pg_http_client.post(
        "/onboarding/start",
        data={"country": "SE", "account_type": "private"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    app_id = _extract_application_id(response.headers["location"])
    assert count_applications_sync(postgres_ready, app_id) == 1


def test_http_postgres_identity_flow_persists_segments(pg_http_client: TestClient):
    start = pg_http_client.post(
        "/onboarding/start",
        data={"country": "SE", "account_type": "private"},
        follow_redirects=False,
    )
    app_id = _extract_application_id(start.headers["location"])

    submit = pg_http_client.post(
        f"/onboarding/{app_id}/step/identity",
        data=IDENTITY,
        follow_redirects=False,
    )
    assert submit.status_code == 303
    assert f"/onboarding/{app_id}/step/contact" in submit.headers["location"]

    status = pg_http_client.get(f"/onboarding/{app_id}/status").json()
    assert status["ready"] is True
    assert status["current_step_key"] == "contact"


def test_http_postgres_segments_in_database(pg_http_client: TestClient, postgres_ready: str):
    start = pg_http_client.post(
        "/onboarding/start",
        data={"country": "SE", "account_type": "private"},
        follow_redirects=False,
    )
    app_id = _extract_application_id(start.headers["location"])
    pg_http_client.post(
        f"/onboarding/{app_id}/step/identity", data=IDENTITY, follow_redirects=False
    )

    segments = list_segments_sync(postgres_ready, app_id)
    assert len(segments) >= 1
    assert any(s["segment_key"] == "identity" and s["status"] == "completed" for s in segments)
