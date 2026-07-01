from __future__ import annotations

from onboarding.domain.events.catalog import EventType
from onboarding.domain.events.envelope import DomainEvent
from onboarding.domain.models import FlowEvent
from onboarding.interfaces.events import IEventRouter


class TraceProjectionHandler:
    """Projects domain events onto existing trace tables."""

    _FLOW = {
        EventType.APPLICATION_STARTED,
        EventType.STEP_SUBMITTED,
        EventType.STEP_ADVANCED,
        EventType.APPLICATION_SUBMITTED,
        EventType.APPLICATION_ABANDONED,
        EventType.SUB_FLOW_STARTED,
        EventType.SUB_FLOW_COMPLETED,
        EventType.SUB_FLOW_FAILED,
        EventType.MAIN_PROGRESS_UPDATED,
    }
    _INTEGRATION = {
        EventType.INTEGRATION_REQUESTED,
        EventType.INTEGRATION_COMPLETED,
        EventType.INTEGRATION_FAILED,
    }
    _DECISION = {EventType.DECISION_REQUESTED, EventType.DECISION_COMPLETED}

    def __init__(self, trace_router: IEventRouter) -> None:
        self._trace = trace_router

    async def handle(self, event: DomainEvent) -> None:
        et = event.event_type
        metadata = {**event.payload, "flow_id": event.envelope.flow_id}
        if event.envelope.segment_key:
            metadata["segment_key"] = event.envelope.segment_key

        if et in self._FLOW:
            mapped = self._map_flow_type(et)
        elif et in self._INTEGRATION:
            mapped = (
                "integration_result"
                if et != EventType.INTEGRATION_REQUESTED
                else "integration_requested"
            )
        elif et in self._DECISION:
            mapped = "decision" if et == EventType.DECISION_COMPLETED else "decision_requested"
        else:
            return

        await self._trace.emit(
            FlowEvent(
                application_id=event.application_id,
                event_type=mapped,
                actor="system",
                metadata=metadata,
            )
        )

    @staticmethod
    def _map_flow_type(et: EventType) -> str:
        mapping = {
            EventType.APPLICATION_STARTED: "application_started",
            EventType.STEP_SUBMITTED: "step_completed",
            EventType.STEP_ADVANCED: "step_completed",
            EventType.APPLICATION_SUBMITTED: "submitted",
            EventType.APPLICATION_ABANDONED: "application_abandoned",
            EventType.SUB_FLOW_STARTED: "subflow_started",
            EventType.SUB_FLOW_COMPLETED: "subflow_completed",
            EventType.SUB_FLOW_FAILED: "subflow_failed",
            EventType.MAIN_PROGRESS_UPDATED: "progress_updated",
        }
        return mapping.get(et, et.value)
