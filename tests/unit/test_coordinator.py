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
