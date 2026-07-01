from __future__ import annotations

from datetime import datetime, timezone

from onboarding.audit.redaction import hash_payload
from onboarding.domain.events.catalog import EventType, routing_key_for
from onboarding.domain.events.envelope import DomainEvent, EventEnvelope
from onboarding.domain.models import FlowStep
from onboarding.events.outbox.publisher import OutboxPublisher
from onboarding.integrations.gateway import INTEGRATION_MAP
from onboarding.interfaces.integrations import IIntegrationGateway
from onboarding.interfaces.persistence import IApplicationRepository


class IntegrationHandler:
    def __init__(
        self,
        repo: IApplicationRepository,
        gateway: IIntegrationGateway,
        publisher: OutboxPublisher,
    ) -> None:
        self._repo = repo
        self._gateway = gateway
        self._publisher = publisher

    async def handle(self, event: DomainEvent) -> None:
        if event.event_type != EventType.INTEGRATION_REQUESTED:
            return
        app = await self._repo.get(event.application_id)
        if app is None:
            return

        integration_key = event.payload["integration_key"]
        segment_key = event.payload["segment_key"]
        aggregated = await self._repo.get_aggregated_answers(app.id)

        pseudo_step = FlowStep(
            key=segment_key,
            title=segment_key,
            integrations=[integration_key],
        )
        results = await self._gateway.run_checks(app, pseudo_step, aggregated)
        for result in results:
            await self._repo.save_integration_result(result)
            envelope = EventEnvelope(
                event_type=EventType.INTEGRATION_COMPLETED,
                application_id=app.id,
                flow_id=event.envelope.flow_id,
                correlation_id=event.envelope.correlation_id,
                routing_key=routing_key_for(
                    EventType.INTEGRATION_COMPLETED, event.envelope.flow_id
                ),
                segment_key=segment_key,
                orchestrator_id=event.envelope.orchestrator_id,
                payload={
                    "segment_key": segment_key,
                    "integration_key": integration_key,
                    "check_type": result.check_type.value,
                    "outcome": result.outcome.value,
                    "provider": result.provider,
                    "request_payload_hash": result.request_payload_hash,
                    "response": result.response,
                    "pending_count": 0,
                },
            )
            await self._publisher.enqueue_and_flush(envelope)
