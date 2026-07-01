from onboarding.domain.enums import CheckOutcome
from onboarding.integrations.dtos import BankAccountCheckRequest, BankAccountCheckResponse
from onboarding.integrations.mocks.outcomes import bank_outcome


class MockBankAccountClient:
    async def verify(self, request: BankAccountCheckRequest) -> BankAccountCheckResponse:
        outcome = bank_outcome(request.iban)
        return BankAccountCheckResponse(
            outcome=outcome,
            provider=f"mock-bank-{request.country.value.lower()}",
            bank_name="Mock Bank" if outcome == CheckOutcome.IBAN_VERIFIED else None,
            details={"fallback": outcome == CheckOutcome.TIMEOUT},
        )
