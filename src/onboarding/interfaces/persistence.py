from typing import Any, Protocol
from uuid import UUID

from onboarding.domain.enums import AccountType, ApplicationStatus, Country, DecisionOutcome
from onboarding.domain.models import Application, IntegrationResult, StepSubmission


class IApplicationRepository(Protocol):
    async def create(
        self,
        *,
        request_id: str,
        country: Country,
        account_type: AccountType,
        current_step_key: str,
        device_id: str | None = None,
    ) -> Application: ...

    async def get(self, application_id: UUID) -> Application | None: ...

    async def list_applications(self) -> list[Application]: ...

    async def update_status(
        self,
        application_id: UUID,
        status: ApplicationStatus,
        *,
        final_decision: DecisionOutcome | None = None,
        current_step_key: str | None = None,
    ) -> Application: ...

    async def save_step_submission(self, submission: StepSubmission) -> StepSubmission: ...

    async def get_step_submissions(self, application_id: UUID) -> list[StepSubmission]: ...

    async def get_step_submission(
        self, application_id: UUID, step_key: str
    ) -> StepSubmission | None: ...

    async def save_integration_result(self, result: IntegrationResult) -> IntegrationResult: ...

    async def get_integration_results(self, application_id: UUID) -> list[IntegrationResult]: ...

    async def get_aggregated_answers(self, application_id: UUID) -> dict[str, Any]: ...

    async def get_latest_by_device(
        self, device_id: str, status: ApplicationStatus | None = None
    ) -> Application | None: ...

    async def find_by_identifier_hash(
        self, identifier_hash: str, status: ApplicationStatus | None = None
    ) -> Application | None: ...

    async def update_identifier_hash(
        self, application_id: UUID, identifier_hash: str
    ) -> Application: ...

    async def list_by_device(
        self, device_id: str, status: ApplicationStatus | None = None
    ) -> list[Application]: ...

    async def abandon_drafts_for_device(self, device_id: str) -> list[UUID]: ...
