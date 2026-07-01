from onboarding.domain.enums import CheckOutcome
from onboarding.integrations.dtos import SanctionsCheckRequest, SanctionsCheckResponse
from onboarding.integrations.mocks.outcomes import sanctions_outcome


class MockSanctionsClient:
    async def screen(self, request: SanctionsCheckRequest) -> SanctionsCheckResponse:
        outcome = sanctions_outcome(request.name)
        score_map = {
            CheckOutcome.NO_HIT: 0.0,
            CheckOutcome.POSSIBLE_HIT: 0.65,
            CheckOutcome.CONFIRMED_HIT: 0.98,
        }
        return SanctionsCheckResponse(
            outcome=outcome,
            provider="mock-sanctions",
            match_score=score_map[outcome],
        )
