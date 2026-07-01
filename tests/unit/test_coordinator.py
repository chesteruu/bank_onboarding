import pytest
from fakes import (
    FakeEventRouter,
    FakeOutboxRepository,
    FakeRepository,
    FakeResumeTokenService,
    FakeSegmentRepository,
)

from onboarding.config import FLOWS_DIR, PROJECT_ROOT
from onboarding.decision.engine import RulesDecisionEngine
from onboarding.domain.enums import AccountType, Country
from onboarding.domain.events.catalog import EventType
from onboarding.domain.events.envelope import EventEnvelope
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


@pytest.mark.asyncio
async def test_coordinator_advances_after_integration():
    repo = FakeRepository()
    segments = FakeSegmentRepository()
    events = FakeEventRouter()
    resume = FakeResumeTokenService()
    provider = YamlFlowDefinitionProvider(FLOWS_DIR)
    engine = FlowEngine(provider)
    gateway = MockIntegrationGateway()
    bus = InProcessEventBus()
    publisher = OutboxPublisher(FakeOutboxRepository(), bus)
    orchestrators = build_orchestrator_registry(FLOWS_DIR)
    coordinator = FlowCoordinatorHandler(repo, segments, engine, orchestrators, publisher, resume)
    integration = IntegrationHandler(repo, gateway, publisher)
    trace = TraceProjectionHandler(events)
    rules_dir = PROJECT_ROOT / "src" / "onboarding" / "decision" / "rules"
    decision = DecisionHandler(repo, RulesDecisionEngine(rules_dir), publisher, resume)
    wire_event_system(
        bus,
        {
            "coordinator": coordinator,
            "integration": integration,
            "trace": trace,
            "decision": decision,
        },
    )

    app = await repo.create(
        request_id="req_coord",
        country=Country.SE,
        account_type=AccountType.PRIVATE,
        current_step_key="credit_decision",
        device_id="d1",
    )
    flow = engine.get_flow(app)
    envelope = EventEnvelope(
        event_type=EventType.STEP_SUBMITTED,
        application_id=app.id,
        flow_id=flow.flow_id,
        correlation_id=app.request_id,
        routing_key=f"onboarding.{flow.flow_id}.onboarding.step.submitted",
        segment_key="credit_decision",
        payload={"step_key": "credit_decision", "answers": {}},
    )
    await publisher.enqueue_and_flush(envelope)
    updated = await repo.get(app.id)
    assert updated is not None
    assert updated.current_step_key == "review"


def test_pointer_reached_guard():
    from onboarding.events.handlers.coordinator import _pointer_reached

    provider = YamlFlowDefinitionProvider(FLOWS_DIR)
    flow = provider.get_flow_by_id("se_private")

    # Pointer already at/after the target => advance is a no-op (idempotent).
    assert _pointer_reached(flow, "review", "review") is True
    assert _pointer_reached(flow, "decision", "review") is True
    # Pointer before the target => still needs to advance.
    assert _pointer_reached(flow, "financial", "review") is False
    # Fail open on unknown/None keys so the flow never silently stalls.
    assert _pointer_reached(flow, None, "review") is False
    assert _pointer_reached(flow, "review", None) is False
    assert _pointer_reached(flow, "bogus", "review") is False


@pytest.mark.asyncio
async def test_duplicate_subflow_completed_advances_only_once():
    """A redelivered SUB_FLOW_COMPLETED (distinct id) must not double-advance."""
    repo = FakeRepository()
    segments = FakeSegmentRepository()
    resume = FakeResumeTokenService()
    provider = YamlFlowDefinitionProvider(FLOWS_DIR)
    engine = FlowEngine(provider)
    bus = InProcessEventBus()
    publisher = OutboxPublisher(FakeOutboxRepository(), bus)
    orchestrators = build_orchestrator_registry(FLOWS_DIR)
    coordinator = FlowCoordinatorHandler(repo, segments, engine, orchestrators, publisher, resume)

    app = await repo.create(
        request_id="req_dup",
        country=Country.SE,
        account_type=AccountType.PRIVATE,
        current_step_key="identity",
        device_id="d-dup",
    )
    flow = engine.get_flow(app)

    def _completed() -> EventEnvelope:
        return EventEnvelope(
            event_type=EventType.SUB_FLOW_COMPLETED,
            application_id=app.id,
            flow_id=flow.flow_id,
            correlation_id=app.request_id,
            routing_key=f"onboarding.{flow.flow_id}.onboarding.subflow.completed",
            segment_key="identity",
            payload={"segment_key": "identity"},
        )

    from onboarding.domain.events.envelope import DomainEvent

    await coordinator.handle(DomainEvent(envelope=_completed()))
    assert (await repo.get(app.id)).current_step_key == "contact"

    # Second, distinct completion for the same segment must be ignored.
    await coordinator.handle(DomainEvent(envelope=_completed()))
    assert (await repo.get(app.id)).current_step_key == "contact"
