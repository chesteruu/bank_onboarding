from __future__ import annotations

from onboarding.domain.events.envelope import DomainEvent, EventEnvelope
from onboarding.events.bus.in_process import InProcessEventBus
from onboarding.interfaces.outbox import IOutboxRepository


class OutboxPublisher:
    """Drains outbox into the event bus (piggybacked on poll/command paths)."""

    def __init__(
        self,
        outbox: IOutboxRepository,
        bus: InProcessEventBus,
        session=None,
    ) -> None:
        self._outbox = outbox
        self._bus = bus
        self._session = session

    async def _commit(self) -> None:
        if self._session is not None:
            await self._session.commit()

    async def enqueue_and_flush(self, envelope: EventEnvelope) -> None:
        outbox_id = await self._outbox.enqueue(envelope)
        await self._outbox.mark_published(outbox_id)
        await self._bus.publish(DomainEvent(envelope=envelope))
        await self._commit()

    async def flush_pending(self, limit: int = 50) -> int:
        pending = await self._outbox.fetch_pending(limit=limit)
        for outbox_id, envelope in pending:
            await self._bus.publish(DomainEvent(envelope=envelope))
            await self._outbox.mark_published(outbox_id)
        if pending:
            await self._commit()
        return len(pending)
