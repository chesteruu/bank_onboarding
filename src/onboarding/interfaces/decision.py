from typing import Protocol

from onboarding.domain.models import Application, DecisionResult, IntegrationResult


class IDecisionEngine(Protocol):
    def evaluate(
        self,
        application: Application,
        integration_results: list[IntegrationResult],
        *,
        aggregated_answers: dict | None = None,
    ) -> DecisionResult: ...
