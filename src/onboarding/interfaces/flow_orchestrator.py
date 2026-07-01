from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from onboarding.domain.events.segment import FlowSegment, SegmentProgress
from onboarding.domain.models import Application, IntegrationResult


@dataclass
class OrchestratorContext:
    application: Application
    flow_id: str
    segment_key: str
    orchestrator_id: str
    component_flow_id: str
    segment: FlowSegment
    shell_step_integrations: list[str] = field(default_factory=list)
    form_schema: str | None = None


@dataclass
class OrchestratorResult:
    segment: FlowSegment
    publish_events: list[Any] = field(default_factory=list)
    completed: bool = False
    failed: bool = False
    pending_integrations: list[tuple[str, str]] = field(default_factory=list)


class IFlowOrchestrator(Protocol):
    orchestrator_id: str

    async def on_subflow_started(self, ctx: OrchestratorContext) -> OrchestratorResult: ...

    async def on_step_submitted(
        self, ctx: OrchestratorContext, answers: dict[str, Any]
    ) -> OrchestratorResult: ...

    async def on_integration_completed(
        self, ctx: OrchestratorContext, result: IntegrationResult
    ) -> OrchestratorResult: ...

    def get_progress(self, segment: FlowSegment) -> SegmentProgress: ...
