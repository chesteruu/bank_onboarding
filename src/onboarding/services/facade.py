from __future__ import annotations

from typing import Any
from uuid import UUID

from onboarding.domain.models import Application, DecisionResult, IntegrationResult
from onboarding.services.command_service import OnboardingCommandService
from onboarding.services.onboarding import OnboardingService
from onboarding.services.query_service import OnboardingQueryService


class OnboardingFacade:
    """Unified API: event-driven command/query or legacy sync orchestrator."""

    def __init__(
        self,
        command: OnboardingCommandService,
        query: OnboardingQueryService,
        legacy: OnboardingService | None = None,
        *,
        event_driven: bool = True,
    ) -> None:
        self._command = command
        self._query = query
        self._legacy = legacy
        self._event_driven = event_driven

    def allowed_countries(self, account_type: str) -> list[str]:
        return self._command.allowed_countries(account_type)

    async def start_application(
        self, country: str, account_type: str, device_id: str | None = None
    ) -> Application:
        if self._event_driven:
            return await self._command.start_application(country, account_type, device_id)
        assert self._legacy is not None
        return await self._legacy.start_application(country, account_type, device_id)

    async def get_application(self, application_id: UUID) -> Application | None:
        return await self._query.get_application(application_id)

    async def resume_by_device(self, device_id: str) -> Application | None:
        return await self._query.resume_by_device(device_id)

    async def resume_by_token(self, token: str) -> Application | None:
        return await self._query.resume_by_token(token)

    async def get_resume_link(self, application_id: UUID, base_url: str) -> str | None:
        return await self._query.get_resume_link(application_id, base_url)

    async def start_over(self, device_id: str) -> None:
        if self._event_driven:
            await self._command.start_over(device_id)
        elif self._legacy:
            await self._legacy.start_over(device_id)

    async def get_status(self, application_id: UUID) -> dict[str, Any]:
        return await self._query.get_status(application_id)

    async def get_step_view(
        self, application_id: UUID, step_key: str, *, base_url: str | None = None
    ) -> dict[str, Any]:
        return await self._query.get_step_view(application_id, step_key, base_url=base_url)

    async def submit_step(
        self,
        application_id: UUID,
        step_key: str,
        answers: dict[str, Any],
        *,
        allow_duplicate: bool = False,
    ) -> tuple[Application, list[IntegrationResult]]:
        if self._event_driven:
            app = await self._command.submit_step(
                application_id, step_key, answers, allow_duplicate=allow_duplicate
            )
            return app, []
        assert self._legacy is not None
        return await self._legacy.submit_step(
            application_id, step_key, answers, allow_duplicate=allow_duplicate
        )

    async def finalize_application(self, application_id: UUID) -> DecisionResult:
        if self._event_driven:
            await self._command.finalize_application(application_id)
            app = await self._query.get_application(application_id)
            assert app is not None and app.final_decision is not None
            return DecisionResult(outcome=app.final_decision, reasons=[])
        assert self._legacy is not None
        return await self._legacy.finalize_application(application_id)

    async def get_review_data(self, application_id: UUID) -> dict[str, Any]:
        return await self._query.get_review_data(application_id)

    async def list_applications(self) -> list[Application]:
        return await self._query.list_applications()

    async def get_admin_application_detail(self, application_id: UUID) -> dict[str, Any]:
        return await self._query.get_review_data(application_id)

    async def list_trace_events(self, limit: int = 100):
        return await self._query.list_trace_events(limit=limit)

    @property
    def event_driven(self) -> bool:
        return self._event_driven
