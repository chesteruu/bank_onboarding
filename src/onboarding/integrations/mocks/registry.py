from onboarding.domain.enums import CheckOutcome
from onboarding.integrations.dtos import RegistryCheckRequest, RegistryCheckResponse
from onboarding.integrations.mocks.outcomes import registry_outcome


class MockRegistryClient:
    async def lookup(self, request: RegistryCheckRequest) -> RegistryCheckResponse:
        outcome = registry_outcome(request.company_number)
        status_map = {
            CheckOutcome.ACTIVE_COMPANY: "active",
            CheckOutcome.DISSOLVED: "dissolved",
            CheckOutcome.UNKNOWN_REPRESENTATIVE: "active",
            CheckOutcome.MISSING_UBO: "active",
        }
        return RegistryCheckResponse(
            outcome=outcome,
            provider=f"mock-registry-{request.country.value.lower()}",
            company_status=status_map.get(outcome, "unknown"),
            details={"company_name": request.company_name},
        )
