from __future__ import annotations

from onboarding.flow.component_provider import ComponentFlowProvider
from onboarding.flow.orchestrators.component import YamlComponentOrchestrator
from onboarding.interfaces.flow_orchestrator import IFlowOrchestrator


class OrchestratorRegistry:
    def __init__(self, component_provider: ComponentFlowProvider) -> None:
        self._orchestrators: dict[str, IFlowOrchestrator] = {}
        self._provider = component_provider

    def register(self, orchestrator_id: str) -> None:
        self._orchestrators[orchestrator_id] = YamlComponentOrchestrator(
            orchestrator_id, self._provider
        )

    def register_defaults(self) -> None:
        for oid in (
            "identity",
            "contact",
            "compliance",
            "affordability_input",
            "credit",
            "kyb",
            "review",
            "decision",
            "financial",
            "company",
            "signatory",
            "representative",
            "board",
            "ubo",
            "bank",
        ):
            self.register(oid)

    def get(self, orchestrator_id: str) -> IFlowOrchestrator | None:
        if orchestrator_id not in self._orchestrators:
            self.register(orchestrator_id)
        return self._orchestrators.get(orchestrator_id)
