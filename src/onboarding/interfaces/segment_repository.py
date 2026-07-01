from typing import Protocol
from uuid import UUID

from onboarding.domain.events.segment import FlowSegment, SegmentProgress


class ISegmentRepository(Protocol):
    async def upsert(self, segment: FlowSegment) -> FlowSegment: ...

    async def get(self, application_id: UUID, segment_key: str) -> FlowSegment | None: ...

    async def list_for_application(self, application_id: UUID) -> list[FlowSegment]: ...

    async def get_active(self, application_id: UUID) -> FlowSegment | None: ...
