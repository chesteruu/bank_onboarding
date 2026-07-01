from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from onboarding.audit.redaction import hash_identifier
from onboarding.domain.enums import AccountType, ApplicationStatus, Country
from onboarding.domain.events.catalog import EventType, routing_key_for
from onboarding.domain.events.envelope import EventEnvelope
from onboarding.domain.exceptions import DuplicateDraftError
from onboarding.domain.models import Application, ResumeTokenData, StepSubmission
from onboarding.events.outbox.publisher import OutboxPublisher
from onboarding.i18n.provider import get_locale_provider
from onboarding.interfaces.flow import IFlowEngine
from onboarding.interfaces.persistence import IApplicationRepository
from onboarding.interfaces.resume import IResumeTokenService


def _extract_identifier_hash(answers: dict[str, Any]) -> str | None:
    identifier = answers.get("national_id") or answers.get("pesel") or answers.get("dni")
    if identifier:
        return hash_identifier(str(identifier))
    return None


def _compute_input_hash(answers: dict[str, Any]) -> str:
    normalized = json.dumps(answers, sort_keys=True, default=str)
    return hashlib.sha256(normalized.encode()).hexdigest()


class OnboardingCommandService:
    def __init__(
        self,
        repo: IApplicationRepository,
        flow_engine: IFlowEngine,
        publisher: OutboxPublisher,
        resume_tokens: IResumeTokenService | None = None,
        available_flows: dict[str, list[str]] | None = None,
        legacy_abandon: Any | None = None,
    ) -> None:
        self._repo = repo
        self._flow = flow_engine
        self._publisher = publisher
        self._resume_tokens = resume_tokens
        self._available_flows = available_flows or get_locale_provider().available_flows()
        self._legacy_abandon = legacy_abandon

    def allowed_countries(self, account_type: str) -> list[str]:
        return list(self._available_flows.get(account_type, []))

    async def start_application(
        self, country: str, account_type: str, device_id: str | None = None
    ) -> Application:
        allowed = self._available_flows.get(account_type, [])
        if country not in allowed:
            raise ValueError(f"Country {country} is not available for {account_type} accounts")
        flow = self._flow.get_flow_for(country, account_type)
        if self._legacy_abandon:
            await self._legacy_abandon(device_id)
        first_step = flow.steps[0].key
        request_id = f"req_{uuid.uuid4().hex[:12]}"
        app = await self._repo.create(
            request_id=request_id,
            country=Country(country),
            account_type=AccountType(account_type),
            current_step_key=first_step,
            device_id=device_id,
        )
        if self._resume_tokens:
            await self._resume_tokens.create_token(
                app.id,
                ResumeTokenData(
                    application_id=app.id,
                    current_step_key=app.current_step_key,
                    created_at=app.created_at,
                ),
            )
        await self._publisher.enqueue_and_flush(
            EventEnvelope(
                event_type=EventType.APPLICATION_STARTED,
                application_id=app.id,
                flow_id=flow.flow_id,
                correlation_id=request_id,
                routing_key=routing_key_for(EventType.APPLICATION_STARTED, flow.flow_id),
                payload={"flow_id": flow.flow_id},
            )
        )
        return app

    async def submit_step(
        self,
        application_id: UUID,
        step_key: str,
        answers: dict[str, Any],
        *,
        allow_duplicate: bool = False,
    ) -> Application:
        app = await self._repo.get(application_id)
        if app is None:
            raise ValueError(f"Application {application_id} not found")
        flow = self._flow.get_flow(app)
        step = flow.get_step(step_key)
        if step is None:
            raise ValueError(f"Unknown step {step_key}")
        current = self._flow.get_current_step(app)
        if current != step_key:
            raise ValueError(f"Expected step {current}, got {step_key}")

        identifier_hash = _extract_identifier_hash(answers)
        if identifier_hash and not allow_duplicate:
            existing = await self._repo.find_by_identifier_hash(
                identifier_hash, status=ApplicationStatus.DRAFT
            )
            if existing is not None and existing.id != application_id:
                raise DuplicateDraftError(existing.id)

        submission = StepSubmission(
            application_id=application_id,
            step_key=step_key,
            answers=answers,
            completed_at=datetime.now(timezone.utc),
            input_hash=_compute_input_hash(answers),
        )
        await self._repo.save_step_submission(submission)
        if identifier_hash:
            await self._repo.update_identifier_hash(application_id, identifier_hash)

        await self._publisher.enqueue_and_flush(
            EventEnvelope(
                event_type=EventType.STEP_SUBMITTED,
                application_id=application_id,
                flow_id=flow.flow_id,
                correlation_id=app.request_id,
                routing_key=routing_key_for(EventType.STEP_SUBMITTED, flow.flow_id),
                segment_key=step_key,
                orchestrator_id=step.orchestrator,
                payload={"step_key": step_key, "answers": answers},
            )
        )
        app = await self._repo.get(application_id)
        assert app is not None
        return app

    async def finalize_application(self, application_id: UUID) -> None:
        app = await self._repo.get(application_id)
        if app is None:
            raise ValueError(f"Application {application_id} not found")
        flow = self._flow.get_flow(app)
        await self._publisher.enqueue_and_flush(
            EventEnvelope(
                event_type=EventType.DECISION_REQUESTED,
                application_id=application_id,
                flow_id=flow.flow_id,
                correlation_id=app.request_id,
                routing_key=routing_key_for(EventType.DECISION_REQUESTED, flow.flow_id),
                payload={},
            )
        )

    async def start_over(self, device_id: str) -> None:
        if self._legacy_abandon:
            await self._legacy_abandon(device_id)
