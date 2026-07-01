from typing import Protocol
from uuid import UUID

from onboarding.domain.models import ResumeTokenData


class IResumeTokenService(Protocol):
    """Creates and validates time-limited resume tokens."""

    async def create_token(self, application_id: UUID, resumption_data: ResumeTokenData) -> str: ...

    async def validate_token(self, token: str) -> ResumeTokenData | None: ...

    async def mark_used(self, token: str) -> None: ...

    async def revoke_for_application(self, application_id: UUID) -> int: ...

    async def get_active_token(self, application_id: UUID) -> str | None: ...

    async def sync_resumption(
        self, application_id: UUID, resumption_data: ResumeTokenData
    ) -> None: ...

    async def cleanup_expired(self) -> int: ...
