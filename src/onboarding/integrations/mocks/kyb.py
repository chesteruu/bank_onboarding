from onboarding.domain.enums import CheckOutcome
from onboarding.integrations.dtos import KybCheckRequest, KybCheckResponse
from onboarding.integrations.mocks.outcomes import kyb_outcome


class MockKybClient:
    async def verify(self, request: KybCheckRequest) -> KybCheckResponse:
        outcome = kyb_outcome(request.company_number, request.ubo_count)
        risk = "low" if outcome == CheckOutcome.PASS else "high"
        return KybCheckResponse(
            outcome=outcome,
            provider=f"mock-kyb-{request.country.value.lower()}",
            risk_level=risk,
        )
