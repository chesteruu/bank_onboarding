from uuid import uuid4

import pytest

from onboarding.domain.events.catalog import EventType
from onboarding.domain.events.envelope import DomainEvent, EventEnvelope
from onboarding.events.bus.in_process import InProcessEventBus


@pytest.mark.asyncio
async def test_event_bus_dispatches_by_pattern():
    bus = InProcessEventBus()
    received: list[str] = []

    async def handler(event: DomainEvent) -> None:
        received.append(event.envelope.event_type.value)

    bus.subscribe("*step.submitted*", handler)
    envelope = EventEnvelope(
        event_type=EventType.STEP_SUBMITTED,
        application_id=uuid4(),
        flow_id="se_private",
        correlation_id="req_test",
        routing_key="onboarding.se_private.onboarding.step.submitted",
    )
    await bus.publish(DomainEvent(envelope=envelope))
    assert received == ["onboarding.step.submitted"]
