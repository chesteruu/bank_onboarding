from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from onboarding.domain.events.envelope import EventEnvelope
from onboarding.persistence.models import EventOutboxORM


class PostgresOutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def enqueue(self, envelope: EventEnvelope) -> UUID:
        outbox_id = uuid4()
        orm = EventOutboxORM(
            id=outbox_id,
            event_type=envelope.event_type.value,
            routing_key=envelope.routing_key,
            payload_json=envelope.model_dump(mode="json"),
        )
        self._session.add(orm)
        await self._session.flush()
        return outbox_id

    async def fetch_pending(self, limit: int = 50) -> list[tuple[UUID, EventEnvelope]]:
        stmt = (
            select(EventOutboxORM)
            .where(EventOutboxORM.published_at.is_(None))
            .order_by(EventOutboxORM.created_at)
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        result: list[tuple[UUID, EventEnvelope]] = []
        for row in rows:
            result.append((row.id, EventEnvelope.model_validate(row.payload_json)))
        return result

    async def mark_published(self, outbox_id: UUID) -> None:
        orm = await self._session.get(EventOutboxORM, outbox_id)
        if orm is not None:
            orm.published_at = datetime.now(timezone.utc)
            await self._session.flush()

    async def increment_attempts(self, outbox_id: UUID) -> None:
        orm = await self._session.get(EventOutboxORM, outbox_id)
        if orm is not None:
            orm.attempts += 1
            await self._session.flush()
