from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from onboarding.audit.redaction import redact_pii
from onboarding.domain.models import FlowEvent
from onboarding.interfaces.events import IEventRouter
from onboarding.persistence.models import (
    DecisionTraceORM,
    FlowTraceORM,
    IntegrationTraceORM,
)


class TraceTableRouter(IEventRouter):
    """Routes flow-stage events to dedicated trace tables.

    Routing rules (CloudWatch-event-rules style):
    - application_started, step_completed, submitted -> flow_trace
    - integration_result -> integration_trace
    - decision -> decision_trace
    """

    _FLOW_EVENT_TYPES = {
        "application_started",
        "application_abandoned",
        "step_completed",
        "submitted",
        "subflow_started",
        "subflow_completed",
        "subflow_failed",
        "progress_updated",
    }
    _INTEGRATION_EVENT_TYPES = {"integration_result", "integration_requested"}
    _DECISION_EVENT_TYPES = {"decision", "decision_requested"}

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def emit(self, event: FlowEvent) -> None:
        safe_metadata = redact_pii(event.metadata)
        created_at = event.created_at or datetime.now(timezone.utc)

        if event.event_type in self._FLOW_EVENT_TYPES:
            orm = FlowTraceORM(
                application_id=event.application_id,
                event_type=event.event_type,
                actor=event.actor,
                metadata_json=safe_metadata,
                created_at=created_at,
            )
        elif event.event_type in self._INTEGRATION_EVENT_TYPES:
            orm = IntegrationTraceORM(
                application_id=event.application_id,
                event_type=event.event_type,
                actor=event.actor,
                metadata_json=safe_metadata,
                created_at=created_at,
            )
        elif event.event_type in self._DECISION_EVENT_TYPES:
            orm = DecisionTraceORM(
                application_id=event.application_id,
                event_type=event.event_type,
                actor=event.actor,
                metadata_json=safe_metadata,
                created_at=created_at,
            )
        else:
            raise ValueError(f"Unknown event type: {event.event_type}")

        self._session.add(orm)
        await self._session.commit()

    async def get_events(self, application_id: UUID) -> list[FlowEvent]:
        events: list[FlowEvent] = []

        for model in (FlowTraceORM, IntegrationTraceORM, DecisionTraceORM):
            stmt = (
                select(model)
                .where(model.application_id == application_id)
                .order_by(model.created_at)
            )
            rows = (await self._session.execute(stmt)).scalars().all()
            events.extend(
                FlowEvent(
                    application_id=r.application_id,
                    event_type=r.event_type,
                    actor=r.actor,
                    metadata=r.metadata_json,
                    created_at=r.created_at,
                )
                for r in rows
            )

        events.sort(key=lambda e: e.created_at or datetime.min.replace(tzinfo=timezone.utc))
        return events

    async def list_all_events(self, limit: int = 100) -> list[FlowEvent]:
        events: list[FlowEvent] = []
        for model in (FlowTraceORM, IntegrationTraceORM, DecisionTraceORM):
            stmt = select(model).order_by(model.created_at.desc()).limit(limit)
            rows = (await self._session.execute(stmt)).scalars().all()
            events.extend(
                FlowEvent(
                    application_id=r.application_id,
                    event_type=r.event_type,
                    actor=r.actor,
                    metadata=r.metadata_json,
                    created_at=r.created_at,
                )
                for r in rows
            )
        events.sort(
            key=lambda e: e.created_at or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        return events[:limit]
