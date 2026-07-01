from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from onboarding.audit.redaction import redact_pii
from onboarding.domain.models import AuditEvent
from onboarding.persistence.models import AuditEventORM


class PostgresAuditLogger:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def log_event(
        self,
        application_id: UUID,
        event_type: str,
        *,
        actor: str = "system",
        metadata: dict | None = None,
    ) -> AuditEvent:
        safe_metadata = redact_pii(metadata or {})
        orm = AuditEventORM(
            application_id=application_id,
            event_type=event_type,
            actor=actor,
            metadata_json=safe_metadata,
        )
        self._session.add(orm)
        await self._session.commit()
        await self._session.refresh(orm)
        return AuditEvent(
            id=orm.id,
            application_id=orm.application_id,
            event_type=orm.event_type,
            actor=orm.actor,
            metadata=orm.metadata_json,
            created_at=orm.created_at,
        )

    async def log_step_completed(
        self, application_id: UUID, step_key: str, *, actor: str = "applicant"
    ) -> AuditEvent:
        return await self.log_event(
            application_id,
            "step_completed",
            actor=actor,
            metadata={"step_key": step_key},
        )

    async def log_integration_result(
        self,
        application_id: UUID,
        check_type: str,
        outcome: str,
        *,
        provider: str,
    ) -> AuditEvent:
        return await self.log_event(
            application_id,
            "integration_result",
            metadata={"check_type": check_type, "outcome": outcome, "provider": provider},
        )

    async def log_decision(
        self, application_id: UUID, outcome: str, reasons: list[str]
    ) -> AuditEvent:
        return await self.log_event(
            application_id,
            "decision",
            metadata={"outcome": outcome, "reasons": reasons},
        )

    async def log_submitted(self, application_id: UUID) -> AuditEvent:
        return await self.log_event(application_id, "submitted", actor="applicant")

    async def get_events(self, application_id: UUID) -> list[AuditEvent]:
        from sqlalchemy import select

        stmt = (
            select(AuditEventORM)
            .where(AuditEventORM.application_id == application_id)
            .order_by(AuditEventORM.created_at)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [
            AuditEvent(
                id=r.id,
                application_id=r.application_id,
                event_type=r.event_type,
                actor=r.actor,
                metadata=r.metadata_json,
                created_at=r.created_at,
            )
            for r in rows
        ]
