from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from onboarding.config import PROJECT_ROOT, get_settings
from onboarding.decision.engine import RulesDecisionEngine
from onboarding.events.bootstrap import build_orchestrator_registry, wire_event_system
from onboarding.events.bus.in_process import InProcessEventBus
from onboarding.events.handlers.coordinator import FlowCoordinatorHandler
from onboarding.events.handlers.decision import DecisionHandler
from onboarding.events.handlers.integration import IntegrationHandler
from onboarding.events.handlers.trace import TraceProjectionHandler
from onboarding.events.outbox.publisher import OutboxPublisher
from onboarding.events.outbox.repository import PostgresOutboxRepository
from onboarding.events.router import TraceTableRouter
from onboarding.flow.engine import FlowEngine
from onboarding.flow.provider import YamlFlowDefinitionProvider
from onboarding.integrations.gateway import MockIntegrationGateway
from onboarding.integrations.resilience import IntegrationCallPolicy, ResilientIntegrationCaller
from onboarding.persistence.database import get_db_session
from onboarding.persistence.repository import PostgresApplicationRepository
from onboarding.persistence.segment_repository import PostgresSegmentRepository
from onboarding.services.command_service import OnboardingCommandService
from onboarding.services.facade import OnboardingFacade
from onboarding.services.query_service import OnboardingQueryService
from onboarding.services.resume_service import PostgresResumeTokenService

_orchestrator_registry = None


def get_orchestrator_registry():
    global _orchestrator_registry
    if _orchestrator_registry is None:
        settings = get_settings()
        _orchestrator_registry = build_orchestrator_registry(settings.flows_dir)
    return _orchestrator_registry


def get_flow_provider() -> YamlFlowDefinitionProvider:
    return YamlFlowDefinitionProvider(get_settings().flows_dir)


def get_flow_engine(
    provider: Annotated[YamlFlowDefinitionProvider, Depends(get_flow_provider)],
) -> FlowEngine:
    return FlowEngine(provider)


def get_integration_gateway() -> MockIntegrationGateway:
    settings = get_settings()
    policy = IntegrationCallPolicy(
        timeout_seconds=settings.integration_timeout_seconds,
        max_attempts=settings.integration_max_attempts,
        retry_backoff_seconds=settings.integration_retry_backoff_seconds,
        retry_backoff_multiplier=settings.integration_retry_backoff_multiplier,
        max_backoff_seconds=settings.integration_max_backoff_seconds,
    )
    return MockIntegrationGateway(
        caller=ResilientIntegrationCaller(default_policy=policy),
    )


def get_decision_engine() -> RulesDecisionEngine:
    rules_dir = PROJECT_ROOT / "src" / "onboarding" / "decision" / "rules"
    if not rules_dir.is_dir():
        rules_dir = PROJECT_ROOT / "onboarding" / "decision" / "rules"
    return RulesDecisionEngine(rules_dir)


async def get_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PostgresApplicationRepository:
    return PostgresApplicationRepository(session)


async def get_segment_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PostgresSegmentRepository:
    return PostgresSegmentRepository(session)


async def get_event_router(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TraceTableRouter:
    return TraceTableRouter(session)


async def get_resume_token_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PostgresResumeTokenService:
    settings = get_settings()
    return PostgresResumeTokenService(
        session,
        secret=settings.resume_token_secret,
        ttl_hours=settings.resume_token_ttl_hours,
    )


def _build_event_bus(
    session: AsyncSession,
    repo: PostgresApplicationRepository,
    segments: PostgresSegmentRepository,
    flow_engine: FlowEngine,
    gateway: MockIntegrationGateway,
    decision_engine: RulesDecisionEngine,
    event_router: TraceTableRouter,
    resume_tokens: PostgresResumeTokenService,
) -> tuple[InProcessEventBus, OutboxPublisher]:
    outbox = PostgresOutboxRepository(session)
    bus = InProcessEventBus()
    publisher = OutboxPublisher(outbox, bus, session=session)
    orchestrators = get_orchestrator_registry()
    coordinator = FlowCoordinatorHandler(
        repo, segments, flow_engine, orchestrators, publisher, resume_tokens
    )
    integration = IntegrationHandler(repo, gateway, publisher)
    trace = TraceProjectionHandler(event_router)
    decision = DecisionHandler(repo, decision_engine, publisher, resume_tokens)
    wire_event_system(
        bus,
        {
            "coordinator": coordinator,
            "integration": integration,
            "trace": trace,
            "decision": decision,
        },
    )
    return bus, publisher


async def get_onboarding_service(
    request: Request,
    repo: Annotated[PostgresApplicationRepository, Depends(get_repository)],
    segments: Annotated[PostgresSegmentRepository, Depends(get_segment_repository)],
    flow_engine: Annotated[FlowEngine, Depends(get_flow_engine)],
    gateway: Annotated[MockIntegrationGateway, Depends(get_integration_gateway)],
    decision_engine: Annotated[RulesDecisionEngine, Depends(get_decision_engine)],
    event_router: Annotated[TraceTableRouter, Depends(get_event_router)],
    resume_tokens: Annotated[PostgresResumeTokenService, Depends(get_resume_token_service)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> OnboardingFacade:
    settings = get_settings()
    query = OnboardingQueryService(repo, segments, flow_engine, event_router, resume_tokens)

    _, publisher = _build_event_bus(
        session, repo, segments, flow_engine, gateway, decision_engine, event_router, resume_tokens
    )

    async def abandon(device_id: str) -> None:
        abandoned = await repo.abandon_drafts_for_device(device_id)
        for app_id in abandoned:
            await resume_tokens.revoke_for_application(app_id)

    command = OnboardingCommandService(
        repo,
        flow_engine,
        publisher,
        resume_tokens,
        settings.available_flows,
        abandon_prior_drafts=abandon,
    )
    return OnboardingFacade(command, query, event_driven=True)
