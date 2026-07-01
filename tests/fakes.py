from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from onboarding.domain.enums import ApplicationStatus, CheckOutcome, IntegrationCheckType
from onboarding.i18n.provider import get_locale_provider
from onboarding.domain.events.envelope import EventEnvelope
from onboarding.domain.events.segment import FlowSegment
from onboarding.domain.models import (
    Application,
    FlowEvent,
    IntegrationResult,
    ResumeTokenData,
    StepSubmission,
)


class FakeRepository:
    def __init__(self) -> None:
        self.applications: dict[UUID, Application] = {}
        self.submissions: list[StepSubmission] = []
        self.integrations: list[IntegrationResult] = []
        self._sequences: dict[UUID, int] = {}
        self._counter = 0

    def _next_sequence(self) -> int:
        self._counter += 1
        return self._counter

    async def create(
        self, *, request_id, country, account_type, current_step_key, device_id=None
    ):
        now = datetime.now(timezone.utc)
        seq = self._next_sequence()
        app = Application(
            id=uuid4(),
            request_id=request_id,
            country=country,
            account_type=account_type,
            device_id=device_id,
            status=ApplicationStatus.DRAFT,
            current_step_key=current_step_key,
            created_at=now,
            updated_at=now,
        )
        # Store sequence for deterministic ordering in tests.
        self._sequences[app.id] = seq
        self.applications[app.id] = app
        return app

    def _sequence(self, app: Application) -> int:
        return self._sequences.get(app.id, 0)

    async def get(self, application_id: UUID):
        return self.applications.get(application_id)

    async def list_applications(self):
        return sorted(
            self.applications.values(),
            key=lambda a: (a.created_at, self._sequence(a)),
            reverse=True,
        )

    async def update_status(
        self, application_id, status, *, final_decision=None, current_step_key=None
    ):
        app = self.applications[application_id]
        app = app.model_copy(
            update={
                "status": status,
                "final_decision": final_decision or app.final_decision,
                "current_step_key": current_step_key or app.current_step_key,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        self.applications[application_id] = app
        return app

    async def save_step_submission(self, submission):
        self.submissions.append(submission)
        return submission

    async def get_step_submissions(self, application_id):
        return [s for s in self.submissions if s.application_id == application_id]

    async def get_step_submission(self, application_id, step_key):
        for s in self.submissions:
            if s.application_id == application_id and s.step_key == step_key:
                return s
        return None

    async def save_integration_result(self, result):
        self.integrations.append(result)
        return result

    async def get_integration_results(self, application_id):
        return [r for r in self.integrations if r.application_id == application_id]

    async def get_aggregated_answers(self, application_id):
        agg: dict[str, Any] = {}
        for s in self.submissions:
            if s.application_id == application_id:
                agg.update(s.answers)
        return agg

    async def get_latest_by_device(self, device_id, status=None):
        apps = [a for a in self.applications.values() if a.device_id == device_id]
        if status is not None:
            apps = [a for a in apps if a.status == status]
        if not apps:
            return None
        return max(
            apps,
            key=lambda a: (a.created_at, self._sequence(a)),
        )

    async def find_by_identifier_hash(self, identifier_hash, status=None):
        apps = [a for a in self.applications.values() if a.identifier_hash == identifier_hash]
        if status is not None:
            apps = [a for a in apps if a.status == status]
        if not apps:
            return None
        return max(apps, key=lambda a: (a.created_at, self._sequence(a)))

    async def update_identifier_hash(self, application_id, identifier_hash):
        app = self.applications[application_id]
        app = app.model_copy(update={"identifier_hash": identifier_hash})
        self.applications[application_id] = app
        return app

    async def list_by_device(self, device_id, status=None):
        apps = [a for a in self.applications.values() if a.device_id == device_id]
        if status is not None:
            apps = [a for a in apps if a.status == status]
        return sorted(
            apps,
            key=lambda a: (a.created_at, self._sequence(a)),
            reverse=True,
        )

    async def abandon_drafts_for_device(self, device_id):
        abandoned = []
        for app_id, app in list(self.applications.items()):
            if app.device_id == device_id and app.status == ApplicationStatus.DRAFT:
                self.applications[app_id] = app.model_copy(
                    update={
                        "status": ApplicationStatus.ABANDONED,
                        "current_step_key": None,
                        "updated_at": datetime.now(timezone.utc),
                    }
                )
                abandoned.append(app_id)
        return abandoned


class FakeEventRouter:
    def __init__(self) -> None:
        self.events: list[FlowEvent] = []

    async def emit(self, event: FlowEvent) -> None:
        self.events.append(event)

    async def get_events(self, application_id: UUID) -> list[FlowEvent]:
        return [e for e in self.events if e.application_id == application_id]

    async def list_all_events(self, limit: int = 100) -> list[FlowEvent]:
        return sorted(
            self.events,
            key=lambda e: e.created_at or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )[:limit]


class FakeResumeTokenService:
    def __init__(self) -> None:
        self.tokens: dict[str, ResumeTokenData] = {}
        self.expires_at: dict[str, datetime] = {}
        self.used: set[str] = set()
        self.app_tokens: dict[UUID, str] = {}

    async def create_token(
        self, application_id: UUID, resumption_data: ResumeTokenData
    ) -> str:
        token = uuid4().hex
        self.tokens[token] = resumption_data
        self.expires_at[token] = datetime.now(timezone.utc) + timedelta(hours=24)
        self.app_tokens[application_id] = token
        return token

    async def validate_token(self, token: str) -> ResumeTokenData | None:
        if (
            token in self.used
            or token not in self.tokens
            or self.expires_at[token] < datetime.now(timezone.utc)
        ):
            return None
        return self.tokens[token]

    async def mark_used(self, token: str) -> None:
        self.used.add(token)

    async def revoke_for_application(self, application_id: UUID) -> int:
        revoked = 0
        for token, data in list(self.tokens.items()):
            if data.application_id == application_id and token not in self.used:
                self.used.add(token)
                revoked += 1
        self.app_tokens.pop(application_id, None)
        return revoked

    async def get_active_token(self, application_id: UUID) -> str | None:
        token = self.app_tokens.get(application_id)
        if token is None:
            return None
        if (
            token in self.used
            or self.expires_at.get(token, datetime.min.replace(tzinfo=timezone.utc))
            < datetime.now(timezone.utc)
        ):
            return None
        return token

    async def sync_resumption(
        self, application_id: UUID, resumption_data: ResumeTokenData
    ) -> None:
        token = await self.get_active_token(application_id)
        if token is not None:
            self.tokens[token] = resumption_data
            return
        await self.create_token(application_id, resumption_data)

    async def cleanup_expired(self) -> int:
        now = datetime.now(timezone.utc)
        expired = [t for t, exp in self.expires_at.items() if exp < now]
        for t in expired:
            self.tokens.pop(t, None)
            self.expires_at.pop(t, None)
        return len(expired)


class FakeSegmentRepository:
    def __init__(self) -> None:
        self.segments: dict[tuple[UUID, str], FlowSegment] = {}

    async def upsert(self, segment: FlowSegment) -> FlowSegment:
        key = (segment.application_id, segment.segment_key)
        if segment.id is None:
            segment = segment.model_copy(update={"id": uuid4()})
        existing = self.segments.get(key)
        if existing and segment.sequence < existing.sequence:
            segment = segment.model_copy(update={"sequence": existing.sequence})
        self.segments[key] = segment.model_copy(
            update={"updated_at": datetime.now(timezone.utc)}
        )
        return self.segments[key]

    async def get(self, application_id: UUID, segment_key: str) -> FlowSegment | None:
        return self.segments.get((application_id, segment_key))

    async def list_for_application(self, application_id: UUID) -> list[FlowSegment]:
        return [s for (aid, _), s in self.segments.items() if aid == application_id]

    async def get_active(self, application_id: UUID) -> FlowSegment | None:
        from onboarding.domain.events.segment import SegmentStatus

        active = [
            s
            for (aid, _), s in self.segments.items()
            if aid == application_id and s.status in (SegmentStatus.ACTIVE, SegmentStatus.PROCESSING)
        ]
        return active[0] if active else None


class FakeOutboxRepository:
    def __init__(self) -> None:
        self._pending: dict[UUID, EventEnvelope] = {}
        self.published: list[UUID] = []

    async def enqueue(self, envelope: EventEnvelope) -> UUID:
        oid = uuid4()
        self._pending[oid] = envelope
        return oid

    async def fetch_pending(self, limit: int = 50) -> list[tuple[UUID, EventEnvelope]]:
        items = list(self._pending.items())[:limit]
        return [(oid, env) for oid, env in items if oid not in self.published]

    async def mark_published(self, outbox_id: UUID) -> None:
        self.published.append(outbox_id)

    async def increment_attempts(self, outbox_id: UUID) -> None:
        pass


def build_event_facade(
    *,
    available_flows: dict[str, list[str]] | None = None,
):
    """Build an event-driven OnboardingFacade wired with in-memory fakes."""
    from onboarding.config import FLOWS_DIR, PROJECT_ROOT
    from onboarding.decision.engine import RulesDecisionEngine
    from onboarding.events.bootstrap import build_orchestrator_registry, wire_event_system
    from onboarding.events.bus.in_process import InProcessEventBus
    from onboarding.events.handlers.coordinator import FlowCoordinatorHandler
    from onboarding.events.handlers.decision import DecisionHandler
    from onboarding.events.handlers.integration import IntegrationHandler
    from onboarding.events.handlers.trace import TraceProjectionHandler
    from onboarding.events.outbox.publisher import OutboxPublisher
    from onboarding.flow.engine import FlowEngine
    from onboarding.flow.provider import YamlFlowDefinitionProvider
    from onboarding.integrations.gateway import MockIntegrationGateway
    from onboarding.services.command_service import OnboardingCommandService
    from onboarding.services.facade import OnboardingFacade
    from onboarding.services.query_service import OnboardingQueryService
    from onboarding.domain.events.envelope import EventEnvelope

    repo = FakeRepository()
    segments = FakeSegmentRepository()
    events = FakeEventRouter()
    resume = FakeResumeTokenService()
    provider = YamlFlowDefinitionProvider(FLOWS_DIR)
    engine = FlowEngine(provider)
    gateway = MockIntegrationGateway()
    rules_dir = PROJECT_ROOT / "src" / "onboarding" / "decision" / "rules"
    decision_engine = RulesDecisionEngine(rules_dir)
    bus = InProcessEventBus()
    outbox = FakeOutboxRepository()
    publisher = OutboxPublisher(outbox, bus)
    orchestrators = build_orchestrator_registry(FLOWS_DIR)

    async def abandon(device_id: str) -> None:
        abandoned = await repo.abandon_drafts_for_device(device_id)
        for app_id in abandoned:
            await resume.revoke_for_application(app_id)

    coordinator = FlowCoordinatorHandler(
        repo, segments, engine, orchestrators, publisher, resume
    )
    integration = IntegrationHandler(repo, gateway, publisher)
    trace = TraceProjectionHandler(events)
    decision = DecisionHandler(repo, decision_engine, publisher, resume)
    wire_event_system(
        bus,
        {
            "coordinator": coordinator,
            "integration": integration,
            "trace": trace,
            "decision": decision,
        },
    )
    flows = available_flows or get_locale_provider().available_flows()
    command = OnboardingCommandService(
        repo, engine, publisher, resume, flows, legacy_abandon=abandon
    )
    query = OnboardingQueryService(repo, segments, engine, events, resume)
    facade = OnboardingFacade(command, query, event_driven=True)
    facade._repo = repo  # type: ignore[attr-defined]
    facade._segments = segments  # type: ignore[attr-defined]
    facade._resume_tokens = resume  # type: ignore[attr-defined]
    facade._outbox = outbox  # type: ignore[attr-defined]
    facade._events = events  # type: ignore[attr-defined]
    return facade


def make_integration(
    app_id: UUID,
    check_type: IntegrationCheckType,
    outcome: CheckOutcome,
) -> IntegrationResult:
    return IntegrationResult(
        application_id=app_id,
        check_type=check_type,
        provider="mock",
        request_payload_hash="abc",
        response={"score": 750},
        outcome=outcome,
        ran_at=datetime.now(timezone.utc),
    )
