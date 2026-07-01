from __future__ import annotations

from onboarding.events.bus.in_process import InProcessEventBus
from onboarding.events.handlers.coordinator import FlowCoordinatorHandler
from onboarding.events.handlers.decision import DecisionHandler
from onboarding.events.handlers.integration import IntegrationHandler
from onboarding.events.handlers.trace import TraceProjectionHandler
from onboarding.events.outbox.publisher import OutboxPublisher
from onboarding.flow.component_provider import ComponentFlowProvider
from onboarding.flow.orchestrators.registry import OrchestratorRegistry


def wire_event_system(bus: InProcessEventBus, handlers: dict) -> InProcessEventBus:
    coordinator: FlowCoordinatorHandler = handlers["coordinator"]
    integration: IntegrationHandler = handlers["integration"]
    trace: TraceProjectionHandler = handlers["trace"]
    decision: DecisionHandler = handlers["decision"]

    bus.subscribe("*step.submitted*", coordinator.handle)
    bus.subscribe("*integration.completed*", coordinator.handle)
    bus.subscribe("*integration.failed*", coordinator.handle)
    bus.subscribe("*subflow.completed*", coordinator.handle)
    bus.subscribe("*integration.requested*", integration.handle)
    bus.subscribe("*decision.requested*", decision.handle)
    bus.subscribe("onboarding.*", trace.handle)
    return bus


def build_orchestrator_registry(flows_dir) -> OrchestratorRegistry:
    provider = ComponentFlowProvider(flows_dir)
    registry = OrchestratorRegistry(provider)
    registry.register_defaults()
    return registry
