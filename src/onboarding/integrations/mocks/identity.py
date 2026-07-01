from onboarding.domain.enums import CheckOutcome
from onboarding.integrations.dtos import (
    AddressCheckRequest,
    AddressCheckResponse,
    IdentityCheckRequest,
    IdentityCheckResponse,
)
from onboarding.integrations.mocks.outcomes import identity_outcome


class MockIdentityClient:
    async def verify(self, request: IdentityCheckRequest) -> IdentityCheckResponse:
        outcome = identity_outcome(request.national_id)
        return IdentityCheckResponse(
            outcome=outcome,
            provider="mock-bankid" if request.country.value == "SE" else "mock-eid",
            reference=f"ID-{request.national_id[-4:]}",
            details={"method": "mock"},
        )


class MockAddressClient:
    async def verify(self, request: AddressCheckRequest) -> AddressCheckResponse:
        if "invalid" in request.address_line.lower():
            return AddressCheckResponse(
                outcome=CheckOutcome.MANUAL_REVIEW,
                provider="mock-address",
                normalized_address=None,
            )
        normalized = f"{request.address_line}, {request.postal_code} {request.city}"
        return AddressCheckResponse(
            outcome=CheckOutcome.VERIFIED,
            provider="mock-address",
            normalized_address=normalized,
        )
