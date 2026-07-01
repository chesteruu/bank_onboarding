from typing import Protocol
from uuid import UUID

from onboarding.domain.models import FlowEvent


class IEventRouter(Protocol):
    """Routes flow-stage events to the appropriate trace destination."""

    async def emit(self, event: FlowEvent) -> None: ...

    async def get_events(self, application_id: UUID) -> list[FlowEvent]: ...

    async def list_all_events(self, limit: int = 100) -> list[FlowEvent]: ...
