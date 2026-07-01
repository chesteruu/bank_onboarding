from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from onboarding.domain.events.segment import FlowSegment, SegmentStatus
from onboarding.persistence.models import FlowSegmentORM


def _to_segment(orm: FlowSegmentORM) -> FlowSegment:
    return FlowSegment(
        id=orm.id,
        application_id=orm.application_id,
        segment_key=orm.segment_key,
        orchestrator_id=orm.orchestrator_id,
        component_flow_id=orm.component_flow_id,
        status=SegmentStatus(orm.status),
        internal_step_key=orm.internal_step_key,
        internal_total_steps=orm.internal_total_steps,
        percent=orm.percent,
        sequence=orm.sequence,
        updated_at=orm.updated_at,
    )


class PostgresSegmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, segment: FlowSegment) -> FlowSegment:
        stmt = select(FlowSegmentORM).where(
            FlowSegmentORM.application_id == segment.application_id,
            FlowSegmentORM.segment_key == segment.segment_key,
        )
        orm = (await self._session.execute(stmt)).scalar_one_or_none()
        now = datetime.now(timezone.utc)
        if orm is None:
            orm = FlowSegmentORM(
                id=segment.id or uuid4(),
                application_id=segment.application_id,
                segment_key=segment.segment_key,
                orchestrator_id=segment.orchestrator_id,
                component_flow_id=segment.component_flow_id,
                status=segment.status.value,
                internal_step_key=segment.internal_step_key,
                internal_total_steps=segment.internal_total_steps,
                percent=segment.percent,
                sequence=segment.sequence,
                updated_at=now,
            )
            self._session.add(orm)
        else:
            orm.orchestrator_id = segment.orchestrator_id
            orm.component_flow_id = segment.component_flow_id
            orm.status = segment.status.value
            orm.internal_step_key = segment.internal_step_key
            orm.internal_total_steps = segment.internal_total_steps
            orm.percent = segment.percent
            if segment.sequence >= orm.sequence:
                orm.sequence = segment.sequence
            orm.updated_at = now
        await self._session.flush()
        await self._session.refresh(orm)
        return _to_segment(orm)

    async def get(self, application_id: UUID, segment_key: str) -> FlowSegment | None:
        stmt = select(FlowSegmentORM).where(
            FlowSegmentORM.application_id == application_id,
            FlowSegmentORM.segment_key == segment_key,
        )
        orm = (await self._session.execute(stmt)).scalar_one_or_none()
        return _to_segment(orm) if orm else None

    async def list_for_application(self, application_id: UUID) -> list[FlowSegment]:
        stmt = select(FlowSegmentORM).where(FlowSegmentORM.application_id == application_id)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_to_segment(r) for r in rows]

    async def get_active(self, application_id: UUID) -> FlowSegment | None:
        stmt = select(FlowSegmentORM).where(
            FlowSegmentORM.application_id == application_id,
            FlowSegmentORM.status.in_(["active", "processing"]),
        )
        orm = (await self._session.execute(stmt)).scalars().first()
        return _to_segment(orm) if orm else None
