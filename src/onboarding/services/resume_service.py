from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from onboarding.domain.models import ResumeTokenData
from onboarding.interfaces.resume import IResumeTokenService
from onboarding.persistence.models import ResumeTokenORM
from onboarding.services.resume_tokens_crypto import hash_token, mint_token, new_salt


class PostgresResumeTokenService(IResumeTokenService):
    """Resume tokens hashed at rest with a configurable TTL.

    The raw token is an HMAC over ``application_id:salt`` keyed by a server
    secret. Only the token hash and salt are persisted, so the raw token never
    lives in the database; it can still be recomputed for link display because
    it is deterministic given ``(secret, application_id, salt)``.
    """

    def __init__(self, session: AsyncSession, *, secret: str, ttl_hours: int = 24) -> None:
        self._session = session
        self._secret = secret
        self._ttl_hours = ttl_hours

    async def create_token(self, application_id: UUID, resumption_data: ResumeTokenData) -> str:
        await self.cleanup_expired()
        salt = new_salt()
        token = mint_token(self._secret, application_id, salt)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=self._ttl_hours)
        orm = ResumeTokenORM(
            application_id=application_id,
            token_hash=hash_token(token),
            token_salt=salt,
            resumption_data_json=resumption_data.model_dump(mode="json"),
            expires_at=expires_at,
        )
        self._session.add(orm)
        await self._session.commit()
        return token

    async def validate_token(self, token: str) -> ResumeTokenData | None:
        stmt = (
            select(ResumeTokenORM)
            .where(ResumeTokenORM.token_hash == hash_token(token))
            .where(ResumeTokenORM.used_at.is_(None))
            .where(ResumeTokenORM.expires_at > datetime.now(timezone.utc))
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        return ResumeTokenData(**row.resumption_data_json)

    async def mark_used(self, token: str) -> None:
        stmt = select(ResumeTokenORM).where(ResumeTokenORM.token_hash == hash_token(token))
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
            select(ResumeTokenORM)
            .where(ResumeTokenORM.application_id == application_id)
            .where(ResumeTokenORM.used_at.is_(None))
            .where(ResumeTokenORM.expires_at > datetime.now(timezone.utc))
            .limit(1)
        )
        row = (await self._session.execute(stmt)).scalars().first()
        if row is None or row.token_salt is None:
            return None
        return mint_token(self._secret, application_id, row.token_salt)

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
