from uuid import UUID


class StubResumeTokenService:
    """No-op implementation used when resume tokens are not enabled."""

    async def create_token(self, application_id: UUID) -> str:
        raise NotImplementedError("Resume tokens are disabled in this configuration")

    async def validate_token(self, token: str) -> UUID | None:
        raise NotImplementedError("Resume tokens are disabled in this configuration")
