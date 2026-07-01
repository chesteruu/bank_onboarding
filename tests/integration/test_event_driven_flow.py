"""End-to-end tests for the event-driven onboarding pipeline (in-process bus + fakes)."""

import pytest

from onboarding.domain.enums import IntegrationCheckType
from onboarding.domain.events.segment import SegmentStatus

IDENTITY_ANSWERS = {
    "national_id": "199001011234",
    "full_name": "Anna Andersson",
    "date_of_birth": "1990-01-01",
}

CONTACT_ANSWERS = {
    "email": "anna@example.com",
    "phone": "+46701234567",
    "address_line": "Storgatan 1",
    "city": "Stockholm",
    "postal_code": "11122",
}


async def _advance_to_credit(service, app):
    app, _ = await service.submit_step(app.id, "identity", IDENTITY_ANSWERS)
    app, _ = await service.submit_step(app.id, "contact", CONTACT_ANSWERS)
    app, _ = await service.submit_step(
        app.id,
        "consent",
        {
            "consent_terms": True,
            "pep_self_declaration": "not_pep",
            "tax_residency": "SE",
        },
    )
    app, _ = await service.submit_step(
        app.id,
        "financial",
        {"monthly_income": 45000, "monthly_expenses": 20000, "employment_status": "employed"},
    )
    return app


@pytest.mark.asyncio
async def test_identity_submit_creates_segment_and_advances_to_contact(service):
    app = await service.start_application("SE", "private", device_id="integ-1")

    app, _ = await service.submit_step(app.id, "identity", IDENTITY_ANSWERS)

    assert app.current_step_key == "contact"

    segments = await service._segments.list_for_application(app.id)
    identity = next(s for s in segments if s.segment_key == "identity")
    assert identity.orchestrator_id == "identity"
    assert identity.status == SegmentStatus.COMPLETED
    assert identity.percent == 100

    status = await service.get_status(app.id)
    assert status["ready"] is True
    assert status["current_step_key"] == "contact"
    assert status["main_progress"]["percent"] > 0


@pytest.mark.asyncio
async def test_identity_submit_emits_subflow_and_integration_trace_events(service):
    app = await service.start_application("SE", "private", device_id="integ-2")
    await service.submit_step(app.id, "identity", IDENTITY_ANSWERS)

    app_events = await service._events.get_events(app.id)
    event_types = {e.event_type for e in app_events}

    assert "subflow_started" in event_types
    assert "subflow_completed" in event_types
    assert "integration_requested" in event_types
    assert "integration_result" in event_types
    assert "progress_updated" in event_types


@pytest.mark.asyncio
async def test_outbox_publishes_events_on_step_submit(service):
    app = await service.start_application("SE", "private", device_id="integ-3")
    await service.submit_step(app.id, "identity", IDENTITY_ANSWERS)

    assert len(service._outbox.published) >= 1


@pytest.mark.asyncio
async def test_credit_decision_runs_component_integrations(service):
    app = await service.start_application("SE", "private", device_id="integ-4")
    app = await _advance_to_credit(service, app)
    assert app.current_step_key == "credit_decision"

    app, _ = await service.submit_step(app.id, "credit_decision", {})
    assert app.current_step_key == "review"

    integrations = await service._repo.get_integration_results(app.id)
    check_types = {r.check_type for r in integrations}
    assert IntegrationCheckType.IDENTITY in check_types
    assert IntegrationCheckType.CREDIT in check_types
    assert IntegrationCheckType.AFFORDABILITY in check_types

    credit_segment = await service._segments.get(app.id, "credit_decision")
    assert credit_segment is not None
    assert credit_segment.status == SegmentStatus.COMPLETED


@pytest.mark.asyncio
async def test_poll_status_until_ready_after_submit(service):
    """Simulates async UX: status is ready once in-process handlers finish."""
    app = await service.start_application("SE", "private", device_id="integ-5")
    await service.submit_step(app.id, "identity", IDENTITY_ANSWERS)

    for _ in range(5):
        status = await service.get_status(app.id)
        if status["ready"]:
            break
    else:
        pytest.fail("Status never became ready after identity submit")

    assert status["current_step_key"] == "contact"
    assert status["main_progress"]["active_segment"] is None


@pytest.mark.asyncio
async def test_se_private_happy_path_through_decision(service):
    app = await service.start_application("SE", "private", device_id="integ-6")
    app = await _advance_to_credit(service, app)
    app, _ = await service.submit_step(app.id, "credit_decision", {})
    assert app.current_step_key == "review"

    decision = await service.finalize_application(app.id)
    assert decision.outcome.value == "approved"

    detail = await service.get_admin_application_detail(app.id)
    assert len(detail["segments"]) >= 5
    assert detail["application"].final_decision is not None


@pytest.mark.asyncio
async def test_se_business_happy_path(service):
    app = await service.start_application("SE", "business", device_id="integ-7")
    assert app.current_step_key == "company"

    app, _ = await service.submit_step(
        app.id,
        "company",
        {"company_number": "5566778899", "company_name": "Acme AB"},
    )
    app, _ = await service.submit_step(
        app.id,
        "signatory",
        {"signatory_name": "Erik Eriksson", "national_id": "198001011234", "role": "CEO"},
    )
    app, _ = await service.submit_step(
        app.id,
        "ubo",
        {"ubo_count": 1, "ubo_names": "Erik Eriksson"},
    )
    app, _ = await service.submit_step(
        app.id,
        "financial",
        {"annual_revenue": 5000000, "monthly_expenses": 200000, "employee_count": 12},
    )
    app, _ = await service.submit_step(app.id, "kyb_decision", {})
    app, _ = await service.submit_step(app.id, "credit_decision", {})
    assert app.current_step_key == "review"

    decision = await service.finalize_application(app.id)
    assert decision.outcome.value in ("approved", "manual_review")
