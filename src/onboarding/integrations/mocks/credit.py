from onboarding.domain.enums import CheckOutcome
from onboarding.integrations.dtos import CreditCheckRequest, CreditCheckResponse
from onboarding.integrations.mocks.outcomes import credit_outcome, credit_score


class MockCreditClient:
    async def check(self, request: CreditCheckRequest) -> CreditCheckResponse:
        identifier = request.national_id or request.company_number or "0000000000"
        outcome = credit_outcome(identifier, request.monthly_income, request.monthly_expenses)
        score = credit_score(identifier)
        disposable = None
        if request.monthly_income is not None and request.monthly_expenses is not None:
            disposable = request.monthly_income - request.monthly_expenses
        return CreditCheckResponse(
            outcome=outcome,
            provider=f"mock-credit-{request.country.value.lower()}",
            score=score,
            debt_flag=outcome == CheckOutcome.FAIL,
            disposable_income=disposable,
            details={"affordability_checked": request.monthly_income is not None},
        )
