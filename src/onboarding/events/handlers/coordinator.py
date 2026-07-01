from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from onboarding.audit.redaction import redact_pii
from onboarding.domain.enums import ApplicationStatus
from onboarding.domain.events.catalog import EventType, routing_key_for
from onboarding.domain.events.envelope import DomainEvent, EventEnvelope
from onboarding.domain.events.segment import FlowSegment, SegmentStatus
from onboarding.domain.models import FlowEvent, FlowStep
from onboarding.events.outbox.publisher import OutboxPublisher
from onboarding.flow.orchestrators.registry import OrchestratorRegistry
from onboarding.flow.progress import compute_aggregate_progress
from onboarding.interfaces.flow import IFlowEngine
from onboarding.interfaces.flow_orchestrator import OrchestratorContext
from onboarding.interfaces.persistence import IApplicationRepository
from onboarding.interfaces.resume import IResumeTokenService
from onboarding.interfaces.segment_repository import ISegmentRepository
from onboarding.domain.models import ResumeTokenData


class FlowCoordinatorHandler:
    """Owns shell step pointer and syncs sub-flow segments to main progress."""

    def __init__(
        self,
        repo: IApplicationRepository,
        segments: ISegmentRepository,
        flow_engine: IFlowEngine,
        orchestrators: OrchestratorRegistry,
        publisher: OutboxPublisher,
        resume_tokens: IResumeTokenService | None = None,
    ) -> None:
        self._repo = repo
        self._segments = segments
        self._flow = flow_engine
        self._orchestrators = orchestrators
        self._publisher = publisher
        self._resume_tokens = resume_tokens

    async def handle(self, event: DomainEvent) -> None:
        et = event.event_type
        if et == EventType.STEP_SUBMITTED:
            await self._on_step_submitted(event)
        elif et == EventType.INTEGRATION_COMPLETED:
            await self._on_integration_completed(event)
        elif et == EventType.INTEGRATION_FAILED:
            await self._on_integration_failed(event)
        elif et == EventType.SUB_FLOW_COMPLETED:
            await self._on_subflow_completed(event)

    async def _on_step_submitted(self, event: DomainEvent) -> None:
        app = await self._repo.get(event.application_id)
        if app is None:
            return
        flow = self._flow.get_flow(app)
        step_key = event.payload["step_key"]
        step = flow.get_step(step_key)
        if step is None:
            return

        if step.orchestrator and step.component_flow:
            await self._start_component(app, flow.flow_id, step, event.payload.get("answers", {}))
        elif step.integrations:
            await self._start_inline_integrations(app, flow.flow_id, step)
        else:
            await self._advance_shell(app, flow, step_key)

    async def _start_component(
        self, app, flow_id: str, step: FlowStep, answers: dict[str, Any]
    ) -> None:
        orchestrator = self._orchestrators.get(step.orchestrator or "")
        if orchestrator is None:
            return

        segment = FlowSegment(
            application_id=app.id,
            segment_key=step.key,
            orchestrator_id=step.orchestrator or "",
            component_flow_id=step.component_flow or "",
            status=SegmentStatus.ACTIVE,
        )
        segment = await self._segments.upsert(segment)

        ctx = OrchestratorContext(
            application=app,
            flow_id=flow_id,
            segment_key=step.key,
            orchestrator_id=step.orchestrator or "",
            component_flow_id=step.component_flow or "",
            segment=segment,
            shell_step_integrations=step.integrations,
            form_schema=step.form_schema,
        )

        if answers or step.form_schema:
            result = await orchestrator.on_step_submitted(ctx, answers)
        else:
            result = await orchestrator.on_subflow_started(ctx)

        segment = await self._segments.upsert(result.segment)
        await self._repo.update_status(app.id, ApplicationStatus.PROCESSING)

        await self._publish(EventType.SUB_FLOW_STARTED, app.id, flow_id, step.key, step.orchestrator, {
            "segment_key": step.key,
        })

        if result.pending_integrations:
            for internal_key, integration_key in result.pending_integrations:
                await self._request_integration(
                    app.id, flow_id, step.key, step.orchestrator or "", internal_key, integration_key
                )
        elif result.completed:
            await self._complete_subflow(app.id, flow_id, step.key, step.orchestrator or "")
        elif result.failed:
            await self._repo.update_status(app.id, ApplicationStatus.DRAFT)

    async def _start_inline_integrations(self, app, flow_id: str, step: FlowStep) -> None:
        segment = FlowSegment(
            application_id=app.id,
            segment_key=step.key,
            orchestrator_id=step.orchestrator or "inline",
            component_flow_id="inline",
            status=SegmentStatus.PROCESSING,
            internal_step_key=step.key,
            internal_total_steps=1,
            percent=50,
        )
        await self._segments.upsert(segment)
        await self._repo.update_status(app.id, ApplicationStatus.PROCESSING)
        for integration_key in step.integrations:
            await self._request_integration(
                app.id, flow_id, step.key, step.orchestrator or "inline", step.key, integration_key
            )

    async def _on_integration_completed(self, event: DomainEvent) -> None:
        app = await self._repo.get(event.application_id)
        if app is None:
            return
        segment_key = event.payload.get("segment_key", app.current_step_key)
        if not segment_key:
            return
        segment = await self._segments.get(app.id, segment_key)
        flow = self._flow.get_flow(app)
        step = flow.get_step(segment_key)
        if step is None:
            return

        if segment and segment.component_flow_id != "inline":
            orchestrator = self._orchestrators.get(segment.orchestrator_id)
            if orchestrator is None:
                return
            from onboarding.domain.models import IntegrationResult
            from onboarding.domain.enums import CheckOutcome, IntegrationCheckType

            result = IntegrationResult(
                application_id=app.id,
                check_type=IntegrationCheckType(event.payload["check_type"]),
                provider=event.payload.get("provider", "mock"),
                request_payload_hash=event.payload.get("request_payload_hash", ""),
                response=event.payload.get("response", {}),
                outcome=CheckOutcome(event.payload["outcome"]),
                ran_at=datetime.now(timezone.utc),
            )
            ctx = OrchestratorContext(
                application=app,
                flow_id=flow.flow_id,
                segment_key=segment_key,
                orchestrator_id=segment.orchestrator_id,
                component_flow_id=segment.component_flow_id,
                segment=segment,
            )
            orch_result = await orchestrator.on_integration_completed(ctx, result)
            segment = await self._segments.upsert(orch_result.segment)
            await self._publish(
                EventType.SEGMENT_PROGRESS_UPDATED,
                app.id,
                flow.flow_id,
                segment_key,
                segment.orchestrator_id,
                {"percent": segment.percent, "internal_step_key": segment.internal_step_key},
                sequence=segment.sequence,
            )
            if orch_result.pending_integrations:
                for internal_key, integration_key in orch_result.pending_integrations:
                    await self._request_integration(
                        app.id, flow.flow_id, segment_key, segment.orchestrator_id, internal_key, integration_key
                    )
            elif orch_result.completed:
                await self._complete_subflow(app.id, flow.flow_id, segment_key, segment.orchestrator_id)
            return

        # Inline shell integrations: advance when all done
        pending = event.payload.get("pending_count", 0)
        if pending <= 0:
            await self._advance_shell(app, flow, segment_key)

    async def _on_integration_failed(self, event: DomainEvent) -> None:
        segment_key = event.payload.get("segment_key")
        if segment_key:
            segment = await self._segments.get(event.application_id, segment_key)
            if segment:
                await self._segments.upsert(
                    segment.model_copy(update={"status": SegmentStatus.FAILED})
                )
        await self._repo.update_status(event.application_id, ApplicationStatus.DRAFT)

    async def _on_subflow_completed(self, event: DomainEvent) -> None:
        app = await self._repo.get(event.application_id)
        if app is None:
            return
        flow = self._flow.get_flow(app)
        await self._advance_shell(app, flow, event.payload["segment_key"])

    async def _complete_subflow(
        self, application_id: UUID, flow_id: str, segment_key: str, orchestrator_id: str
    ) -> None:
        segment = await self._segments.get(application_id, segment_key)
        if segment:
            await self._segments.upsert(
                segment.model_copy(update={"status": SegmentStatus.COMPLETED, "percent": 100})
            )
        app = await self._repo.get(application_id)
        if app is None:
            return
        flow = self._flow.get_flow(app)
        await self._publish(
            EventType.SEGMENT_PROGRESS_UPDATED,
            application_id,
            flow_id,
            segment_key,
            orchestrator_id,
            {"percent": 100, "status": "completed"},
        )
        await self._publish(
            EventType.SUB_FLOW_COMPLETED,
            application_id,
            flow_id,
            segment_key,
            orchestrator_id,
            {"segment_key": segment_key},
        )

    async def _advance_shell(self, app, flow, step_key: str) -> None:
        step = flow.get_step(step_key)
        next_key = flow.next_step_key(step_key) if step else None
        if next_key:
            app = await self._repo.update_status(
                app.id, ApplicationStatus.DRAFT, current_step_key=next_key
            )
            await self._publish(
                EventType.STEP_ADVANCED,
                app.id,
                flow.flow_id,
                step_key,
                None,
                {"from_step": step_key, "to_step": next_key},
            )
            if self._resume_tokens:
                await self._resume_tokens.sync_resumption(
                    app.id,
                    ResumeTokenData(
                        application_id=app.id,
                        current_step_key=next_key,
                        identifier_hash=app.identifier_hash,
                        created_at=app.created_at,
                    ),
                )
        else:
            await self._repo.update_status(app.id, ApplicationStatus.DRAFT)

        segments = await self._segments.list_for_application(app.id)
        progress = compute_aggregate_progress(app, flow, segments)
        await self._publish(
            EventType.MAIN_PROGRESS_UPDATED,
            app.id,
            flow.flow_id,
            app.current_step_key or step_key,
            None,
            progress.model_dump(mode="json"),
        )

    async def _request_integration(
        self,
        application_id: UUID,
        flow_id: str,
        segment_key: str,
        orchestrator_id: str,
        internal_step_key: str,
        integration_key: str,
    ) -> None:
        await self._publish(
            EventType.INTEGRATION_REQUESTED,
            application_id,
            flow_id,
            segment_key,
            orchestrator_id,
            {
                "segment_key": segment_key,
                "internal_step_key": internal_step_key,
                "integration_key": integration_key,
            },
        )

    async def _publish(
        self,
        event_type: EventType,
        application_id: UUID,
        flow_id: str,
        segment_key: str | None,
        orchestrator_id: str | None,
        payload: dict[str, Any],
        sequence: int = 0,
    ) -> None:
        app = await self._repo.get(application_id)
        envelope = EventEnvelope(
            event_type=event_type,
            application_id=application_id,
            flow_id=flow_id,
            correlation_id=app.request_id if app else "",
            routing_key=routing_key_for(event_type, flow_id, orchestrator_id),
            segment_key=segment_key,
            orchestrator_id=orchestrator_id,
            sequence=sequence,
            payload=redact_pii(payload),
        )
        await self._publisher.enqueue_and_flush(envelope)
