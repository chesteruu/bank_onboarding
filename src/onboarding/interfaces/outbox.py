from typing import Protocol
from uuid import UUID

from onboarding.domain.events.envelope import EventEnvelope


class IOutboxRepository(Protocol):
    async def enqueue(self, envelope: EventEnvelope) -> UUID: ...

    async def fetch_pending(self, limit: int = 50) -> list[tuple[UUID, EventEnvelope]]: ...

    async def mark_published(self, outbox_id: UUID) -> None: ...

    async def increment_attempts(self, outbox_id: UUID) -> None: ...
