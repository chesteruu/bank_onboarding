from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from onboarding.domain.models import ResumeTokenData
from onboarding.interfaces.resume import IResumeTokenService
from onboarding.persistence.models import ResumeTokenORM


class PostgresResumeTokenService(IResumeTokenService):
    """Resume tokens with a 24-hour TTL.

    Tokens stay valid until revoked, expired, or the application is submitted.
    Link-based resume reuses the same token; ``revoke_for_application`` retires it.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_token(self, application_id: UUID, resumption_data: ResumeTokenData) -> str:
        await self.cleanup_expired()
        token_value = uuid4().hex
        expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
        orm = ResumeTokenORM(
            application_id=application_id,
            token_hash=token_value,
            resumption_data_json=resumption_data.model_dump(mode="json"),
            expires_at=expires_at,
        )
        self._session.add(orm)
        await self._session.commit()
        return token_value

    async def validate_token(self, token: str) -> ResumeTokenData | None:
        stmt = (
            select(ResumeTokenORM)
            .where(ResumeTokenORM.token_hash == token)
            .where(ResumeTokenORM.used_at.is_(None))
            .where(ResumeTokenORM.expires_at > datetime.now(timezone.utc))
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        return ResumeTokenData(**row.resumption_data_json)

    async def mark_used(self, token: str) -> None:
        stmt = select(ResumeTokenORM).where(ResumeTokenORM.token_hash == token)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is not None:
            row.used_at = datetime.now(timezone.utc)
            await self._session.commit()

    async def revoke_for_application(self, application_id: UUID) -> int:
        now = datetime.now(timezone.utc)
        stmt = select(ResumeTokenORM).where(
            ResumeTokenORM.application_id == application_id,
            ResumeTokenORM.used_at.is_(None),
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        for row in rows:
            row.used_at = now
        if rows:
            await self._session.commit()
        return len(rows)

    async def get_active_token(self, application_id: UUID) -> str | None:
        stmt = (
            select(ResumeTokenORM.token_hash)
            .where(ResumeTokenORM.application_id == application_id)
            .where(ResumeTokenORM.used_at.is_(None))
            .where(ResumeTokenORM.expires_at > datetime.now(timezone.utc))
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalars().first()

    async def sync_resumption(self, application_id: UUID, resumption_data: ResumeTokenData) -> None:
        stmt = (
            select(ResumeTokenORM)
            .where(ResumeTokenORM.application_id == application_id)
            .where(ResumeTokenORM.used_at.is_(None))
            .where(ResumeTokenORM.expires_at > datetime.now(timezone.utc))
            .limit(1)
        )
        row = (await self._session.execute(stmt)).scalars().first()
        payload = resumption_data.model_dump(mode="json")
        if row is not None:
            row.resumption_data_json = payload
            await self._session.commit()
            return
        await self.create_token(application_id, resumption_data)

    async def cleanup_expired(self) -> int:
        stmt = delete(ResumeTokenORM).where(ResumeTokenORM.expires_at < datetime.now(timezone.utc))
        result = await self._session.execute(stmt)
        await self._session.commit()
        return int(getattr(result, "rowcount", 0) or 0)
