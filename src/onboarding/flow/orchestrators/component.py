from __future__ import annotations

from typing import Any

from onboarding.domain.events.segment import FlowSegment, SegmentProgress, SegmentStatus
from onboarding.domain.models import IntegrationResult
from onboarding.flow.component_provider import ComponentFlowProvider
from onboarding.interfaces.flow_orchestrator import (
    IFlowOrchestrator,
    OrchestratorContext,
    OrchestratorResult,
)


class YamlComponentOrchestrator(IFlowOrchestrator):
    """YAML-driven sub-flow orchestrator shared by all component types."""

    def __init__(self, orchestrator_id: str, component_provider: ComponentFlowProvider) -> None:
        self.orchestrator_id = orchestrator_id
        self._components = component_provider

    async def on_subflow_started(self, ctx: OrchestratorContext) -> OrchestratorResult:
        component = self._components.load(ctx.component_flow_id)
        first = component.internal_steps[0]
        segment = ctx.segment.model_copy(
            update={
                "status": SegmentStatus.PROCESSING if first.integrations else SegmentStatus.ACTIVE,
                "internal_step_key": first.key,
                "internal_total_steps": len(component.internal_steps),
                "percent": self._percent(component, first.key),
                "sequence": ctx.segment.sequence + 1,
            }
        )
        pending = list(first.integrations) if first.integrations else []
        if not pending and len(component.internal_steps) == 1:
            segment = segment.model_copy(update={"status": SegmentStatus.COMPLETED, "percent": 100})
            return OrchestratorResult(segment=segment, completed=True)
        return OrchestratorResult(
            segment=segment,
            pending_integrations=[(first.key, i) for i in pending],
        )

    async def on_step_submitted(
        self, ctx: OrchestratorContext, answers: dict[str, Any]
    ) -> OrchestratorResult:
        component = self._components.load(ctx.component_flow_id)
        current_key = ctx.segment.internal_step_key or component.internal_steps[0].key
        step = component.get_step(current_key)
        if step is None:
            return OrchestratorResult(segment=ctx.segment, completed=True)

        if step.integrations:
            segment = ctx.segment.model_copy(
                update={
                    "status": SegmentStatus.PROCESSING,
                    "percent": self._percent(component, current_key),
                    "sequence": ctx.segment.sequence + 1,
                }
            )
            return OrchestratorResult(
                segment=segment,
                pending_integrations=[(current_key, i) for i in step.integrations],
            )

        return await self._advance(component, ctx.segment, current_key)

    async def on_integration_completed(
        self, ctx: OrchestratorContext, result: IntegrationResult
    ) -> OrchestratorResult:
        component = self._components.load(ctx.component_flow_id)
        current_key = ctx.segment.internal_step_key or component.internal_steps[0].key
        return await self._advance(component, ctx.segment, current_key)

    async def _advance(
        self, component, segment: FlowSegment, current_key: str
    ) -> OrchestratorResult:
        next_key = component.next_step_key(current_key)
        if next_key is None or next_key == "complete":
            return OrchestratorResult(
                segment=segment.model_copy(
                    update={
                        "status": SegmentStatus.COMPLETED,
                        "percent": 100,
                        "sequence": segment.sequence + 1,
                    }
                ),
                completed=True,
            )
        next_step = component.get_step(next_key)
        if next_step and next_step.optional:
            next_key = component.next_step_key(next_key) or "complete"
            if next_key == "complete":
                return OrchestratorResult(
                    segment=segment.model_copy(
                        update={
                            "status": SegmentStatus.COMPLETED,
                            "percent": 100,
                            "internal_step_key": current_key,
                            "sequence": segment.sequence + 1,
                        }
                    ),
                    completed=True,
                )
            next_step = component.get_step(next_key)

        assert next_step is not None
        updated = segment.model_copy(
            update={
                "internal_step_key": next_key,
                "status": SegmentStatus.PROCESSING
                if next_step.integrations
                else SegmentStatus.ACTIVE,
                "percent": self._percent(component, next_key),
                "sequence": segment.sequence + 1,
            }
        )
        if next_step.integrations:
            return OrchestratorResult(
                segment=updated,
                pending_integrations=[(next_key, i) for i in next_step.integrations],
            )
        if next_key == component.internal_steps[-1].key:
            return OrchestratorResult(
                segment=updated.model_copy(
                    update={"status": SegmentStatus.COMPLETED, "percent": 100}
                ),
                completed=True,
            )
        return OrchestratorResult(segment=updated)

    def get_progress(self, segment: FlowSegment) -> SegmentProgress:
        return SegmentProgress(
            segment_key=segment.segment_key,
            orchestrator_id=segment.orchestrator_id,
            status=segment.status,
            internal_step_key=segment.internal_step_key,
            internal_step_title=(segment.internal_step_key or "").replace("_", " ").title(),
            percent=segment.percent,
        )

    @staticmethod
    def _percent(component, step_key: str) -> int:
        keys = component.step_keys()
        if not keys:
            return 100
        try:
            idx = keys.index(step_key)
        except ValueError:
            return 0
        return int(((idx + 1) / len(keys)) * 100)
