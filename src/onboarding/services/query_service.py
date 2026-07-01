from __future__ import annotations

from typing import Any
from uuid import UUID

from onboarding.audit.redaction import hash_identifier
from onboarding.domain.enums import ApplicationStatus
from onboarding.domain.models import Application, StepSubmission
from onboarding.flow.progress import compute_aggregate_progress
from onboarding.interfaces.events import IEventRouter
from onboarding.interfaces.flow import IFlowEngine
from onboarding.interfaces.persistence import IApplicationRepository
from onboarding.interfaces.resume import IResumeTokenService
from onboarding.interfaces.segment_repository import ISegmentRepository


class OnboardingQueryService:
    def __init__(
        self,
        repo: IApplicationRepository,
        segments: ISegmentRepository,
        flow_engine: IFlowEngine,
        event_router: IEventRouter,
        resume_tokens: IResumeTokenService | None = None,
    ) -> None:
        self._repo = repo
        self._segments = segments
        self._flow = flow_engine
        self._events = event_router
        self._resume_tokens = resume_tokens

    async def get_application(self, application_id: UUID) -> Application | None:
        return await self._repo.get(application_id)

    async def resume_by_device(self, device_id: str) -> Application | None:
        return await self._repo.get_latest_by_device(device_id, status=ApplicationStatus.DRAFT)

    async def resume_by_token(self, token: str) -> Application | None:
        if self._resume_tokens is None:
            return None
        data = await self._resume_tokens.validate_token(token)
        if data is None:
            return None
        app = await self._repo.get(data.application_id)
        if app is None or app.status != ApplicationStatus.DRAFT or not app.current_step_key:
            return None
        return app

    async def get_resume_link(self, application_id: UUID, base_url: str) -> str | None:
        if self._resume_tokens is None:
            return None
        token = await self._resume_tokens.get_active_token(application_id)
        if token is None:
            return None
        return f"{base_url.rstrip('/')}/onboarding/resume/{token}"

    async def get_status(self, application_id: UUID) -> dict[str, Any]:
        app = await self._repo.get(application_id)
        if app is None:
            raise ValueError(f"Application {application_id} not found")
        flow = self._flow.get_flow(app)
        segment_list = await self._segments.list_for_application(application_id)
        progress = compute_aggregate_progress(app, flow, segment_list)
        integrations = await self._repo.get_integration_results(application_id)
        return {
            "application_id": str(application_id),
            "status": app.status.value,
            "current_step_key": app.current_step_key,
            "ready": progress.ready,
            "main_progress": progress.model_dump(mode="json"),
            "integration_count": len(integrations),
            "segments": [s.model_dump(mode="json") for s in segment_list],
        }

    async def get_step_view(
        self, application_id: UUID, step_key: str, *, base_url: str | None = None
    ) -> dict[str, Any]:
        app = await self._repo.get(application_id)
        if app is None:
            raise ValueError(f"Application {application_id} not found")
        ctx = self._flow.get_step_context(app, step_key)
        segment_list = await self._segments.list_for_application(application_id)
        flow = self._flow.get_flow(app)
        progress = compute_aggregate_progress(app, flow, segment_list)
        existing = await self._repo.get_step_submission(application_id, step_key)
        integrations = await self._repo.get_integration_results(application_id)
        resume_link = None
        if base_url and app.status == ApplicationStatus.DRAFT:
            resume_link = await self.get_resume_link(application_id, base_url)
        return {
            "application": app,
            "progress": progress,
            "existing_answers": existing.answers if existing else {},
            "integration_results": integrations,
            "step_integrations": integrations,
            "resume_link": resume_link,
            "processing": app.status == ApplicationStatus.PROCESSING,
            **ctx,
        }

    async def get_review_data(self, application_id: UUID) -> dict[str, Any]:
        app = await self._repo.get(application_id)
        if app is None:
            raise ValueError(f"Application {application_id} not found")
        submissions = await self._repo.get_step_submissions(application_id)
        integrations = await self._repo.get_integration_results(application_id)
        audit_events = await self._events.get_events(application_id)
        segments = await self._segments.list_for_application(application_id)
        flow = self._flow.get_flow(app)
        progress = compute_aggregate_progress(app, flow, segments)
        return {
            "application": app,
            "submissions": [_mask_submission(s) for s in submissions],
            "integrations": integrations,
            "audit_events": audit_events,
            "segments": segments,
            "progress": progress,
        }

    async def list_applications(self) -> list[Application]:
        return await self._repo.list_applications()

    async def list_trace_events(self, limit: int = 100):
        return await self._events.list_all_events(limit=limit)


def _mask_submission(submission: StepSubmission) -> dict[str, Any]:
    masked = {}
    for key, value in submission.answers.items():
        if key in {"national_id", "pesel", "dni", "iban", "email", "phone"}:
            masked[key] = f"***{hash_identifier(str(value))[-4:]}"
        elif key in {"full_name", "company_name", "signatory_name", "account_holder"}:
            parts = str(value).split()
            masked[key] = f"{parts[0][0]}***" if parts else "***"
        else:
            masked[key] = value
    return {"step_key": submission.step_key, "answers": masked}
