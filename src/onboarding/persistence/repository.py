from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from onboarding.domain.enums import (
    AccountType,
    ApplicationStatus,
    CheckOutcome,
    Country,
    DecisionOutcome,
    IntegrationCheckType,
)
from onboarding.domain.models import Application, IntegrationResult, StepSubmission
from onboarding.persistence.models import (
    IntegrationResultORM,
    OnboardingApplicationORM,
    StepSubmissionORM,
)


def _to_application(orm: OnboardingApplicationORM) -> Application:
    return Application(
        id=orm.id,
        request_id=orm.request_id,
        country=Country(orm.country),
        account_type=AccountType(orm.account_type),
        device_id=orm.device_id,
        identifier_hash=orm.identifier_hash,
        status=ApplicationStatus(orm.status),
        current_step_key=orm.current_step_key,
        final_decision=DecisionOutcome(orm.final_decision) if orm.final_decision else None,
        created_at=orm.created_at,
        updated_at=orm.updated_at,
    )


class PostgresApplicationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        request_id: str,
        country: Country,
        account_type: AccountType,
        current_step_key: str,
        device_id: str | None = None,
    ) -> Application:
        orm = OnboardingApplicationORM(
            request_id=request_id,
            country=country.value,
            account_type=account_type.value,
            device_id=device_id,
            current_step_key=current_step_key,
            status=ApplicationStatus.DRAFT.value,
        )
        self._session.add(orm)
        await self._session.commit()
        await self._session.refresh(orm)
        return _to_application(orm)

    async def get(self, application_id: UUID) -> Application | None:
        result = await self._session.get(OnboardingApplicationORM, application_id)
        return _to_application(result) if result else None

    async def list_applications(self) -> list[Application]:
        stmt = select(OnboardingApplicationORM).order_by(OnboardingApplicationORM.created_at.desc())
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_to_application(r) for r in rows]

    async def update_status(
        self,
        application_id: UUID,
        status: ApplicationStatus,
        *,
        final_decision: DecisionOutcome | None = None,
        current_step_key: str | None = None,
    ) -> Application:
        orm = await self._session.get(OnboardingApplicationORM, application_id)
        if orm is None:
            raise ValueError(f"Application {application_id} not found")
        orm.status = status.value
        if final_decision is not None:
            orm.final_decision = final_decision.value
        if current_step_key is not None:
            orm.current_step_key = current_step_key
        orm.updated_at = datetime.now(timezone.utc)
        await self._session.commit()
        await self._session.refresh(orm)
        return _to_application(orm)

    async def save_step_submission(self, submission: StepSubmission) -> StepSubmission:
        orm = StepSubmissionORM(
            application_id=submission.application_id,
            step_key=submission.step_key,
            answers_json=submission.answers,
            completed_at=submission.completed_at,
            input_hash=submission.input_hash,
        )
        self._session.add(orm)
        await self._session.commit()
        return submission

    async def get_step_submissions(self, application_id: UUID) -> list[StepSubmission]:
        stmt = select(StepSubmissionORM).where(StepSubmissionORM.application_id == application_id)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [
            StepSubmission(
                application_id=r.application_id,
                step_key=r.step_key,
                answers=r.answers_json,
                completed_at=r.completed_at,
                input_hash=r.input_hash,
            )
            for r in rows
        ]

    async def get_step_submission(
        self, application_id: UUID, step_key: str
    ) -> StepSubmission | None:
        stmt = select(StepSubmissionORM).where(
            StepSubmissionORM.application_id == application_id,
            StepSubmissionORM.step_key == step_key,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        return StepSubmission(
            application_id=row.application_id,
            step_key=row.step_key,
            answers=row.answers_json,
            completed_at=row.completed_at,
            input_hash=row.input_hash,
        )

    async def save_integration_result(self, result: IntegrationResult) -> IntegrationResult:
        orm = IntegrationResultORM(
            application_id=result.application_id,
            check_type=result.check_type.value,
            provider=result.provider,
            request_payload_hash=result.request_payload_hash,
            response_json=result.response,
            outcome=result.outcome.value,
            ran_at=result.ran_at,
        )
        self._session.add(orm)
        await self._session.commit()
        return result

    async def get_integration_results(self, application_id: UUID) -> list[IntegrationResult]:
        stmt = select(IntegrationResultORM).where(
            IntegrationResultORM.application_id == application_id
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [
            IntegrationResult(
                application_id=r.application_id,
                check_type=IntegrationCheckType(r.check_type),
                provider=r.provider,
                request_payload_hash=r.request_payload_hash,
                response=r.response_json,
                outcome=CheckOutcome(r.outcome),
                ran_at=r.ran_at,
            )
            for r in rows
        ]

    async def get_aggregated_answers(self, application_id: UUID) -> dict[str, Any]:
        submissions = await self.get_step_submissions(application_id)
        aggregated: dict[str, Any] = {}
        for sub in submissions:
            aggregated.update(sub.answers)
        return aggregated

    async def get_latest_by_device(
        self, device_id: str, status: ApplicationStatus | None = None
    ) -> Application | None:
        stmt = (
            select(OnboardingApplicationORM)
            .where(OnboardingApplicationORM.device_id == device_id)
            .order_by(OnboardingApplicationORM.created_at.desc())
        )
        if status is not None:
            stmt = stmt.where(OnboardingApplicationORM.status == status.value)
        row = (await self._session.execute(stmt)).scalars().first()
        return _to_application(row) if row else None

    async def find_by_identifier_hash(
        self, identifier_hash: str, status: ApplicationStatus | None = None
    ) -> Application | None:
        stmt = (
            select(OnboardingApplicationORM)
            .where(OnboardingApplicationORM.identifier_hash == identifier_hash)
            .order_by(OnboardingApplicationORM.created_at.desc())
        )
        if status is not None:
            stmt = stmt.where(OnboardingApplicationORM.status == status.value)
        row = (await self._session.execute(stmt)).scalars().first()
        return _to_application(row) if row else None

    async def update_identifier_hash(
        self, application_id: UUID, identifier_hash: str
    ) -> Application:
        orm = await self._session.get(OnboardingApplicationORM, application_id)
        if orm is None:
            raise ValueError(f"Application {application_id} not found")
        orm.identifier_hash = identifier_hash
        orm.updated_at = datetime.now(timezone.utc)
        await self._session.commit()
        await self._session.refresh(orm)
        return _to_application(orm)

    async def list_by_device(
        self, device_id: str, status: ApplicationStatus | None = None
    ) -> list[Application]:
        stmt = (
            select(OnboardingApplicationORM)
            .where(OnboardingApplicationORM.device_id == device_id)
            .order_by(OnboardingApplicationORM.created_at.desc())
        )
        if status is not None:
            stmt = stmt.where(OnboardingApplicationORM.status == status.value)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_to_application(r) for r in rows]

    async def abandon_drafts_for_device(self, device_id: str) -> list[UUID]:
        stmt = select(OnboardingApplicationORM).where(
            OnboardingApplicationORM.device_id == device_id,
            OnboardingApplicationORM.status == ApplicationStatus.DRAFT.value,
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        now = datetime.now(timezone.utc)
        abandoned: list[UUID] = []
        for orm in rows:
            orm.status = ApplicationStatus.ABANDONED.value
            orm.current_step_key = None
            orm.updated_at = now
            abandoned.append(orm.id)
        if abandoned:
            await self._session.commit()
        return abandoned
