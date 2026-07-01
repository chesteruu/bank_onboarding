from __future__ import annotations

from onboarding.domain.enums import ApplicationStatus, DecisionOutcome
from onboarding.domain.events.catalog import EventType, routing_key_for
from onboarding.domain.events.envelope import DomainEvent, EventEnvelope
from onboarding.events.outbox.publisher import OutboxPublisher
from onboarding.interfaces.decision import IDecisionEngine
from onboarding.interfaces.persistence import IApplicationRepository
from onboarding.interfaces.resume import IResumeTokenService


class DecisionHandler:
    def __init__(
        self,
        repo: IApplicationRepository,
        decision_engine: IDecisionEngine,
        publisher: OutboxPublisher,
        resume_tokens: IResumeTokenService | None = None,
    ) -> None:
        self._repo = repo
        self._decision = decision_engine
        self._publisher = publisher
        self._resume_tokens = resume_tokens

    async def handle(self, event: DomainEvent) -> None:
        if event.event_type != EventType.DECISION_REQUESTED:
            return
        app = await self._repo.get(event.application_id)
        if app is None:
            return
        integrations = await self._repo.get_integration_results(app.id)
        answers = await self._repo.get_aggregated_answers(app.id)
        decision = self._decision.evaluate(app, integrations, aggregated_answers=answers)

        status_map = {
            DecisionOutcome.APPROVED: ApplicationStatus.APPROVED,
            DecisionOutcome.MANUAL_REVIEW: ApplicationStatus.MANUAL_REVIEW,
            DecisionOutcome.REJECTED: ApplicationStatus.REJECTED,
        }
        await self._repo.update_status(app.id, ApplicationStatus.SUBMITTED, final_decision=decision.outcome)
        await self._repo.update_status(
            app.id, status_map[decision.outcome], final_decision=decision.outcome
        )
        if self._resume_tokens:
            await self._resume_tokens.revoke_for_application(app.id)

        await self._publisher.enqueue_and_flush(
            EventEnvelope(
                event_type=EventType.APPLICATION_SUBMITTED,
                application_id=app.id,
                flow_id=event.envelope.flow_id,
                correlation_id=event.envelope.correlation_id,
                routing_key=routing_key_for(EventType.APPLICATION_SUBMITTED, event.envelope.flow_id),
                payload={},
            )
        )
        await self._publisher.enqueue_and_flush(
            EventEnvelope(
                event_type=EventType.DECISION_COMPLETED,
                application_id=app.id,
                flow_id=event.envelope.flow_id,
                correlation_id=event.envelope.correlation_id,
                routing_key=routing_key_for(EventType.DECISION_COMPLETED, event.envelope.flow_id),
                payload={
                    "outcome": decision.outcome.value,
                    "reasons": decision.reasons,
                },
            )
        )
