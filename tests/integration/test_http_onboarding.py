"""HTTP-level integration tests with dependency overrides (no Postgres required)."""

import re
from uuid import UUID

import pytest
from fakes import build_event_facade
from fastapi.testclient import TestClient

from main import create_app
from onboarding.web.deps import get_onboarding_service

IDENTITY = {
    "national_id": "199001011234",
    "full_name": "Anna Andersson",
    "date_of_birth": "1990-01-01",
}
CONTACT = {
    "email": "anna@example.com",
    "phone": "+46701234567",
    "address_line": "Storgatan 1",
    "city": "Stockholm",
    "postal_code": "11122",
}
CONSENT = {
    "consent_terms": "on",
    "pep_self_declaration": "not_pep",
    "tax_residency": "SE",
}
FINANCIAL = {
    "monthly_income": "45000",
    "monthly_expenses": "20000",
    "employment_status": "employed",
}


@pytest.fixture
def client():
    app = create_app()
    facade = build_event_facade()

    async def override_service():
        return facade

    app.dependency_overrides[get_onboarding_service] = override_service
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _extract_application_id(location: str) -> UUID:
    match = re.search(r"/onboarding/([0-9a-f-]{36})/", location)
    assert match, f"No application id in Location: {location}"
    return UUID(match.group(1))


def _start_se_private(client: TestClient) -> UUID:
    start = client.post(
        "/onboarding/start",
        data={"country": "SE", "account_type": "private"},
        follow_redirects=False,
    )
    assert start.status_code == 303
    return _extract_application_id(start.headers["location"])


def test_http_start_and_identity_step_advances(client: TestClient):
    app_id = _start_se_private(client)

    submit = client.post(
        f"/onboarding/{app_id}/step/identity",
        data=IDENTITY,
        follow_redirects=False,
    )
    assert submit.status_code == 303
    assert f"/onboarding/{app_id}/step/contact" in submit.headers["location"]


def test_http_status_endpoint_returns_segment_progress(client: TestClient):
    app_id = _start_se_private(client)
    client.post(f"/onboarding/{app_id}/step/identity", data=IDENTITY, follow_redirects=True)

    status = client.get(f"/onboarding/{app_id}/status")
    assert status.status_code == 200
    body = status.json()
    assert body["ready"] is True
    assert body["current_step_key"] == "contact"
    assert body["main_progress"]["percent"] > 0
    assert any(s["segment_key"] == "identity" for s in body["segments"])


def test_http_credit_step_advances_to_review_via_status(client: TestClient):
    app_id = _start_se_private(client)
    client.post(f"/onboarding/{app_id}/step/identity", data=IDENTITY, follow_redirects=False)
    client.post(f"/onboarding/{app_id}/step/contact", data=CONTACT, follow_redirects=False)
    client.post(f"/onboarding/{app_id}/step/consent", data=CONSENT, follow_redirects=False)
    client.post(f"/onboarding/{app_id}/step/financial", data=FINANCIAL, follow_redirects=False)

    submit = client.post(
        f"/onboarding/{app_id}/step/credit_decision",
        data={},
        follow_redirects=False,
    )
    assert submit.status_code == 303
    assert f"/onboarding/{app_id}/step/review" in submit.headers["location"]

    status = client.get(f"/onboarding/{app_id}/status").json()
    assert status["ready"] is True
    assert status["current_step_key"] == "review"
    assert status["integration_count"] >= 3
