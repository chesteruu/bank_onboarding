from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from onboarding.domain.models import FlowEvent
from onboarding.events.router import TraceTableRouter
from onboarding.persistence.models import DecisionTraceORM, FlowTraceORM, IntegrationTraceORM


def _make_session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.mark.asyncio
async def test_application_started_routes_to_flow_trace():
    session = _make_session()
    router = TraceTableRouter(session)
    app_id = uuid4()

    await router.emit(
        FlowEvent(
            application_id=app_id,
            event_type="application_started",
            metadata={"flow_id": "se_private"},
        )
    )

    orm = session.add.call_args[0][0]
    assert isinstance(orm, FlowTraceORM)
    assert orm.event_type == "application_started"
    assert orm.metadata_json == {"flow_id": "se_private"}
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_step_completed_routes_to_flow_trace():
    session = _make_session()
    router = TraceTableRouter(session)
    app_id = uuid4()

    await router.emit(
        FlowEvent(
            application_id=app_id,
            event_type="step_completed",
            actor="applicant",
            metadata={"step_key": "identity"},
        )
    )

    orm = session.add.call_args[0][0]
    assert isinstance(orm, FlowTraceORM)
    assert orm.actor == "applicant"


@pytest.mark.asyncio
async def test_submitted_routes_to_flow_trace():
    session = _make_session()
    router = TraceTableRouter(session)

    await router.emit(
        FlowEvent(application_id=uuid4(), event_type="submitted", actor="applicant")
    )

    assert isinstance(session.add.call_args[0][0], FlowTraceORM)


@pytest.mark.asyncio
async def test_integration_result_routes_to_integration_trace():
    session = _make_session()
    router = TraceTableRouter(session)

    await router.emit(
        FlowEvent(
            application_id=uuid4(),
            event_type="integration_result",
            metadata={"check_type": "identity", "outcome": "passed", "provider": "mock"},
        )
    )

    assert isinstance(session.add.call_args[0][0], IntegrationTraceORM)


@pytest.mark.asyncio
async def test_decision_routes_to_decision_trace():
    session = _make_session()
    router = TraceTableRouter(session)

    await router.emit(
        FlowEvent(
            application_id=uuid4(),
            event_type="decision",
            metadata={"outcome": "approved", "reasons": ["income_ok"]},
        )
    )

    assert isinstance(session.add.call_args[0][0], DecisionTraceORM)


@pytest.mark.asyncio
async def test_application_abandoned_routes_to_flow_trace():
    session = _make_session()
    router = TraceTableRouter(session)

    await router.emit(
        FlowEvent(
            application_id=uuid4(),
            event_type="application_abandoned",
            actor="applicant",
            metadata={"reason": "start_over", "device_id": "abc123"},
        )
    )

    orm = session.add.call_args[0][0]
    assert isinstance(orm, FlowTraceORM)
    assert orm.event_type == "application_abandoned"


@pytest.mark.asyncio
async def test_unknown_event_type_raises():
    session = _make_session()
    router = TraceTableRouter(session)

    with pytest.raises(ValueError, match="Unknown event type"):
        await router.emit(FlowEvent(application_id=uuid4(), event_type="unknown_event"))


@pytest.mark.asyncio
async def test_redaction_is_applied_to_metadata():
    session = _make_session()
    router = TraceTableRouter(session)

    await router.emit(
        FlowEvent(
            application_id=uuid4(),
            event_type="step_completed",
            metadata={"national_id": "199001011234", "city": "Stockholm"},
        )
    )

    orm = session.add.call_args[0][0]
    assert orm.metadata_json["city"] == "Stockholm"
    assert orm.metadata_json["national_id"] != "199001011234"


@pytest.mark.asyncio
async def test_created_at_defaults_to_now():
    session = _make_session()
    router = TraceTableRouter(session)
    before = datetime.now(timezone.utc)

    await router.emit(FlowEvent(application_id=uuid4(), event_type="submitted"))

    orm = session.add.call_args[0][0]
    assert orm.created_at is not None
    assert orm.created_at >= before
