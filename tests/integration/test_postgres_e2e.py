"""Postgres-backed end-to-end tests (requires Docker Compose Postgres)."""

import pytest
from sqlalchemy import func, select

from onboarding.domain.enums import IntegrationCheckType
from onboarding.persistence.models import (
    EventOutboxORM,
    FlowSegmentORM,
    FlowTraceORM,
    IntegrationResultORM,
    IntegrationTraceORM,
)

pytestmark = pytest.mark.postgres

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


@pytest.mark.asyncio
async def test_postgres_identity_persists_segments_and_outbox(pg_service, pg_session):
    app = await pg_service.start_application("SE", "private", device_id="pg-e2e-1")
    app, _ = await pg_service.submit_step(app.id, "identity", IDENTITY)

    assert app.current_step_key == "contact"

    segment_count = await pg_session.scalar(
        select(func.count())
        .select_from(FlowSegmentORM)
        .where(FlowSegmentORM.application_id == app.id)
    )
    assert segment_count >= 1

    segment = (
        await pg_session.execute(
            select(FlowSegmentORM).where(
                FlowSegmentORM.application_id == app.id,
                FlowSegmentORM.segment_key == "identity",
            )
        )
    ).scalar_one()
    assert segment.status == "completed"
    assert segment.percent == 100

    outbox_count = await pg_session.scalar(select(func.count()).select_from(EventOutboxORM))
    assert outbox_count >= 1

    integration_count = await pg_session.scalar(
        select(func.count())
        .select_from(IntegrationResultORM)
        .where(IntegrationResultORM.application_id == app.id)
    )
    assert integration_count >= 1

    flow_traces = (
        (
            await pg_session.execute(
                select(FlowTraceORM).where(FlowTraceORM.application_id == app.id)
            )
        )
        .scalars()
        .all()
    )
    trace_types = {row.event_type for row in flow_traces}
    assert "subflow_started" in trace_types
    assert "subflow_completed" in trace_types

    integration_traces = (
        (
            await pg_session.execute(
                select(IntegrationTraceORM).where(IntegrationTraceORM.application_id == app.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(integration_traces) >= 1


@pytest.mark.asyncio
async def test_postgres_status_reflects_persisted_state(pg_service):
    app = await pg_service.start_application("SE", "private", device_id="pg-e2e-2")
    await pg_service.submit_step(app.id, "identity", IDENTITY)

    status = await pg_service.get_status(app.id)
    assert status["ready"] is True
    assert status["current_step_key"] == "contact"
    assert any(s["segment_key"] == "identity" for s in status["segments"])


@pytest.mark.asyncio
async def test_postgres_se_private_full_flow_to_approval(pg_service, pg_session):
    app = await pg_service.start_application("SE", "private", device_id="pg-e2e-3")

    app, _ = await pg_service.submit_step(app.id, "identity", IDENTITY)
    app, _ = await pg_service.submit_step(app.id, "contact", CONTACT)
    app, _ = await pg_service.submit_step(
        app.id,
        "consent",
        {
            "consent_terms": True,
            "pep_self_declaration": "not_pep",
            "tax_residency": "SE",
        },
    )
    app, _ = await pg_service.submit_step(
        app.id,
        "financial",
        {"monthly_income": 45000, "monthly_expenses": 20000, "employment_status": "employed"},
    )
    app, _ = await pg_service.submit_step(app.id, "credit_decision", {})
    assert app.current_step_key == "review"

    integration_types = (
        (
            await pg_session.execute(
                select(IntegrationResultORM.check_type).where(
                    IntegrationResultORM.application_id == app.id
                )
            )
        )
        .scalars()
        .all()
    )
    assert IntegrationCheckType.IDENTITY.value in integration_types
    assert IntegrationCheckType.CREDIT.value in integration_types
    assert IntegrationCheckType.AFFORDABILITY.value in integration_types

    decision = await pg_service.finalize_application(app.id)
    assert decision.outcome.value == "approved"

    refreshed = await pg_service.get_application(app.id)
    assert refreshed is not None
    assert refreshed.final_decision is not None
    assert refreshed.status.value in ("approved", "submitted")
