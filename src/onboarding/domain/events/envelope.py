from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from onboarding.domain.events.catalog import EventType


class EventEnvelope(BaseModel):
    event_id: UUID = Field(default_factory=uuid4)
    event_type: EventType
    event_version: int = 1
    application_id: UUID
    flow_id: str
    correlation_id: str
    routing_key: str
    segment_key: str | None = None
    orchestrator_id: str | None = None
    sequence: int = 0
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict[str, Any] = Field(default_factory=dict)


class DomainEvent(BaseModel):
    """Lightweight alias used by handlers."""

    envelope: EventEnvelope

    @property
    def event_type(self) -> EventType:
        return self.envelope.event_type

    @property
    def application_id(self) -> UUID:
        return self.envelope.application_id

    @property
    def payload(self) -> dict[str, Any]:
        return self.envelope.payload
