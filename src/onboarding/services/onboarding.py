from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from onboarding.audit.redaction import hash_identifier
from onboarding.domain.enums import AccountType, ApplicationStatus, Country, DecisionOutcome
from onboarding.domain.exceptions import DuplicateDraftError
from onboarding.domain.models import (
    Application,
    DecisionResult,
    FlowEvent,
    IntegrationResult,
    ResumeTokenData,
    StepSubmission,
)
from onboarding.i18n.provider import get_locale_provider
from onboarding.interfaces.decision import IDecisionEngine
from onboarding.interfaces.events import IEventRouter
from onboarding.interfaces.flow import IFlowEngine
from onboarding.interfaces.integrations import IIntegrationGateway
from onboarding.interfaces.persistence import IApplicationRepository
from onboarding.interfaces.resume import IResumeTokenService


def _extract_identifier_hash(answers: dict[str, Any]) -> str | None:
    identifier = answers.get("national_id") or answers.get("pesel") or answers.get("dni")
    if identifier:
        return hash_identifier(str(identifier))
    return None


class OnboardingService:
    def __init__(
        self,
        repo: IApplicationRepository,
        flow_engine: IFlowEngine,
        gateway: IIntegrationGateway,
        decision_engine: IDecisionEngine,
        event_router: IEventRouter,
        resume_token_service: IResumeTokenService | None = None,
        available_flows: dict[str, list[str]] | None = None,
    ) -> None:
        self._repo = repo
        self._flow = flow_engine
        self._gateway = gateway
        self._decision = decision_engine
        self._event_router = event_router
        self._resume_tokens = resume_token_service
        self._available_flows = available_flows or get_locale_provider().available_flows()

    def allowed_countries(self, account_type: str) -> list[str]:
        return list(self._available_flows.get(account_type, []))

    def _validate_flow(self, country: str, account_type: str) -> None:
        allowed = self._available_flows.get(account_type, [])
        if country not in allowed:
            raise ValueError(f"Country {country} is not available for {account_type} accounts")
        try:
            self._flow.get_flow_for(country, account_type)
        except (KeyError, ValueError) as exc:
            raise ValueError(f"No flow defined for {country}/{account_type}") from exc

    async def start_application(
        self, country: str, account_type: str, device_id: str | None = None
    ) -> Application:
        self._validate_flow(country, account_type)
        await self._ensure_single_device_draft(device_id)
        flow = self._flow.get_flow_for(country, account_type)
        first_step = flow.steps[0].key
        request_id = f"req_{uuid.uuid4().hex[:12]}"
        app = await self._repo.create(
            request_id=request_id,
            country=Country(country),
            account_type=AccountType(account_type),
            current_step_key=first_step,
            device_id=device_id,
        )
        await self._event_router.emit(
            FlowEvent(
                application_id=app.id,
                event_type="application_started",
                actor="system",
                metadata={"flow_id": flow.flow_id},
            )
        )
        if self._resume_tokens is not None:
            await self._resume_tokens.create_token(
                app.id,
                ResumeTokenData(
                    application_id=app.id,
                    current_step_key=app.current_step_key,
                    created_at=app.created_at,
                ),
            )
        return app

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
        if app is None or app.status != ApplicationStatus.DRAFT:
            return None
        if app.current_step_key is None:
            return None
        return app

    async def get_resume_link(self, application_id: UUID, base_url: str) -> str | None:
        if self._resume_tokens is None:
            return None
        token = await self._resume_tokens.get_active_token(application_id)
        if token is None:
            return None
        return f"{base_url.rstrip('/')}/onboarding/resume/{token}"

    async def _sync_resume_token(self, app: Application) -> None:
        if self._resume_tokens is None:
            return
        await self._resume_tokens.sync_resumption(
            app.id,
            ResumeTokenData(
                application_id=app.id,
                current_step_key=app.current_step_key,
                identifier_hash=app.identifier_hash,
                created_at=app.created_at,
            ),
        )

    async def start_over(self, device_id: str) -> None:
        """Abandon in-progress drafts and revoke resume tokens for this device."""
        await self._abandon_device_drafts(device_id, reason="start_over")

    async def _ensure_single_device_draft(self, device_id: str | None) -> None:
        if device_id is None:
            return
        await self._abandon_device_drafts(device_id, reason="superseded")

    async def _abandon_device_drafts(self, device_id: str, *, reason: str) -> None:
        abandoned_ids = await self._repo.abandon_drafts_for_device(device_id)
        if self._resume_tokens is not None:
            for app_id in abandoned_ids:
                await self._resume_tokens.revoke_for_application(app_id)
        for app_id in abandoned_ids:
            await self._event_router.emit(
                FlowEvent(
                    application_id=app_id,
                    event_type="application_abandoned",
                    actor="applicant",
                    metadata={"reason": reason, "device_id": device_id},
                )
            )

    async def get_step_view(
        self, application_id: UUID, step_key: str, *, base_url: str | None = None
    ) -> dict[str, Any]:
        app = await self._require_app(application_id)
        ctx = self._flow.get_step_context(app, step_key)
        progress = self._flow.get_progress(app)
        existing = await self._repo.get_step_submission(application_id, step_key)
        integrations = await self._repo.get_integration_results(application_id)
        step_integrations = [
            r for r in integrations if r.check_type.value in ctx["step"].integrations
        ]
        resume_link = None
        if base_url and app.status == ApplicationStatus.DRAFT:
            resume_link = await self.get_resume_link(application_id, base_url)
        return {
            "application": app,
            "progress": progress,
            "existing_answers": existing.answers if existing else {},
            "integration_results": integrations,
            "step_integrations": step_integrations,
            "resume_link": resume_link,
            **ctx,
        }

    async def submit_step(
        self,
        application_id: UUID,
        step_key: str,
        answers: dict[str, Any],
        *,
        allow_duplicate: bool = False,
    ) -> tuple[Application, list[IntegrationResult]]:
        app = await self._require_app(application_id)
        flow = self._flow.get_flow(app)
        step = flow.get_step(step_key)
        if step is None:
            raise ValueError(f"Unknown step {step_key}")

        current = self._flow.get_current_step(app)
        if current != step_key:
            raise ValueError(f"Expected step {current}, got {step_key}")

        input_hash = _compute_input_hash(answers)
        submission = StepSubmission(
            application_id=application_id,
            step_key=step_key,
            answers=answers,
            completed_at=datetime.now(timezone.utc),
            input_hash=input_hash,
        )
        identifier_hash = _extract_identifier_hash(answers)
        if identifier_hash and not allow_duplicate:
            existing = await self._repo.find_by_identifier_hash(
                identifier_hash, status=ApplicationStatus.DRAFT
            )
            if existing is not None and existing.id != application_id:
                raise DuplicateDraftError(existing.id)

        await self._repo.save_step_submission(submission)

        if identifier_hash:
            await self._repo.update_identifier_hash(application_id, identifier_hash)

        await self._event_router.emit(
            FlowEvent(
                application_id=application_id,
                event_type="step_completed",
                actor="applicant",
                metadata={"step_key": step_key},
            )
        )

        aggregated = await self._repo.get_aggregated_answers(application_id)
        integration_results: list[IntegrationResult] = []
        if step.integrations:
            integration_results = await self._gateway.run_checks(app, step, aggregated)
            for result in integration_results:
                await self._repo.save_integration_result(result)
                await self._event_router.emit(
                    FlowEvent(
                        application_id=application_id,
                        event_type="integration_result",
                        metadata={
                            "check_type": result.check_type.value,
                            "outcome": result.outcome.value,
                            "provider": result.provider,
                        },
                    )
                )

        next_key = flow.next_step_key(step_key)
        if next_key:
            app = await self._repo.update_status(
                application_id,
                ApplicationStatus.DRAFT,
                current_step_key=next_key,
            )
            await self._sync_resume_token(app)
        return app, integration_results

    async def finalize_application(self, application_id: UUID) -> DecisionResult:
        app = await self._require_app(application_id)
        flow = self._flow.get_flow(app)
        review_step = next((s for s in flow.steps if s.is_review), None)
        if review_step and self._flow.get_current_step(app) != review_step.key:
            raise ValueError("Application not at review step")

        integrations = await self._repo.get_integration_results(application_id)
        answers = await self._repo.get_aggregated_answers(application_id)
        decision = self._decision.evaluate(app, integrations, aggregated_answers=answers)

        status_map = {
            DecisionOutcome.APPROVED: ApplicationStatus.APPROVED,
            DecisionOutcome.MANUAL_REVIEW: ApplicationStatus.MANUAL_REVIEW,
            DecisionOutcome.REJECTED: ApplicationStatus.REJECTED,
        }
        await self._repo.update_status(
            application_id,
            ApplicationStatus.SUBMITTED,
            final_decision=decision.outcome,
        )
        await self._repo.update_status(
            application_id,
            status_map[decision.outcome],
            final_decision=decision.outcome,
        )
        await self._event_router.emit(
            FlowEvent(
                application_id=application_id,
                event_type="submitted",
                actor="applicant",
            )
        )
        await self._event_router.emit(
            FlowEvent(
                application_id=application_id,
                event_type="decision",
                metadata={"outcome": decision.outcome.value, "reasons": decision.reasons},
            )
        )
        if self._resume_tokens is not None:
            await self._resume_tokens.revoke_for_application(application_id)
        return decision

    async def get_review_data(self, application_id: UUID) -> dict[str, Any]:
        app = await self._require_app(application_id)
        submissions = await self._repo.get_step_submissions(application_id)
        integrations = await self._repo.get_integration_results(application_id)
        audit_events = await self._event_router.get_events(application_id)
        masked_answers = [_mask_submission(s) for s in submissions]
        return {
            "application": app,
            "submissions": masked_answers,
            "integrations": integrations,
            "audit_events": audit_events,
            "progress": self._flow.get_progress(app),
        }

    async def list_applications(self) -> list[Application]:
        return await self._repo.list_applications()

    async def get_admin_application_detail(self, application_id: UUID) -> dict[str, Any]:
        return await self.get_review_data(application_id)

    async def list_trace_events(self, limit: int = 100) -> list[FlowEvent]:
        return await self._event_router.list_all_events(limit=limit)

    async def _require_app(self, application_id: UUID) -> Application:
        app = await self._repo.get(application_id)
        if app is None:
            raise ValueError(f"Application {application_id} not found")
        return app


def _compute_input_hash(answers: dict[str, Any]) -> str:
    normalized = json.dumps(answers, sort_keys=True, default=str)
    return hashlib.sha256(normalized.encode()).hexdigest()


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
