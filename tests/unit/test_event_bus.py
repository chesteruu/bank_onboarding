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


@pytest.mark.asyncio
async def test_event_bus_dedupes_redelivered_event():
    """At-least-once redelivery of the same envelope must be handled once."""
    bus = InProcessEventBus()
    calls: list[str] = []

    async def handler(event: DomainEvent) -> None:
        calls.append(str(event.envelope.event_id))

    bus.subscribe("*", handler)
    envelope = EventEnvelope(
        event_type=EventType.INTEGRATION_COMPLETED,
        application_id=uuid4(),
        flow_id="se_private",
        correlation_id="req_test",
        routing_key="onboarding.se_private.onboarding.integration.completed",
    )
    event = DomainEvent(envelope=envelope)

    await bus.publish(event)
    await bus.publish(event)  # redelivery, same event_id
    await bus.publish(event)

    assert len(calls) == 1


@pytest.mark.asyncio
async def test_event_bus_processes_distinct_events():
    bus = InProcessEventBus()
    calls: list[str] = []

    async def handler(event: DomainEvent) -> None:
        calls.append(str(event.envelope.event_id))

    bus.subscribe("*", handler)
    for _ in range(3):
        await bus.publish(
            DomainEvent(
                envelope=EventEnvelope(
                    event_type=EventType.INTEGRATION_COMPLETED,
                    application_id=uuid4(),
                    flow_id="se_private",
                    correlation_id="req_test",
                    routing_key="onboarding.se_private.onboarding.integration.completed",
                )
            )
        )
    assert len(calls) == 3
