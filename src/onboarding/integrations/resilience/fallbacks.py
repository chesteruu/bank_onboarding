from __future__ import annotations

from onboarding.domain.enums import CheckOutcome
from onboarding.integrations.dtos import (
    AddressCheckRequest,
    AddressCheckResponse,
    BankAccountCheckRequest,
    BankAccountCheckResponse,
    CreditCheckRequest,
    CreditCheckResponse,
    IdentityCheckRequest,
    IdentityCheckResponse,
    KybCheckRequest,
    KybCheckResponse,
    RegistryCheckRequest,
    RegistryCheckResponse,
    SanctionsCheckRequest,
    SanctionsCheckResponse,
)


async def degraded_identity(req: IdentityCheckRequest) -> IdentityCheckResponse:
    return IdentityCheckResponse(
        outcome=CheckOutcome.MANUAL_REVIEW,
        provider=f"fallback-{req.country.value.lower()}-identity",
        reference="FB-DEGRADED",
        details={"degraded": True, "reason": "primary_unavailable"},
    )


async def degraded_address(req: AddressCheckRequest) -> AddressCheckResponse:
    return AddressCheckResponse(
        outcome=CheckOutcome.MANUAL_REVIEW,
        provider=f"fallback-{req.country.value.lower()}-address",
        details={"degraded": True, "reason": "primary_unavailable"},
    )


async def degraded_registry(req: RegistryCheckRequest) -> RegistryCheckResponse:
    return RegistryCheckResponse(
        outcome=CheckOutcome.MANUAL_REVIEW,
        provider=f"fallback-{req.country.value.lower()}-registry",
        company_status="unknown",
        details={"degraded": True, "reason": "primary_unavailable"},
    )


async def degraded_sanctions(req: SanctionsCheckRequest) -> SanctionsCheckResponse:
    return SanctionsCheckResponse(
        outcome=CheckOutcome.MANUAL_REVIEW,
        provider=f"fallback-{req.country.value.lower()}-sanctions",
        details={"degraded": True, "reason": "primary_unavailable"},
    )


async def degraded_credit(req: CreditCheckRequest) -> CreditCheckResponse:
    return CreditCheckResponse(
        outcome=CheckOutcome.MANUAL_REVIEW,
        provider=f"fallback-{req.country.value.lower()}-credit",
        score=0,
        details={"degraded": True, "reason": "primary_unavailable"},
    )


async def degraded_kyb(req: KybCheckRequest) -> KybCheckResponse:
    return KybCheckResponse(
        outcome=CheckOutcome.MANUAL_REVIEW,
        provider=f"fallback-{req.country.value.lower()}-kyb",
        risk_level="unknown",
        details={"degraded": True, "reason": "primary_unavailable"},
    )


async def degraded_bank(req: BankAccountCheckRequest) -> BankAccountCheckResponse:
    return BankAccountCheckResponse(
        outcome=CheckOutcome.MANUAL_REVIEW,
        provider=f"fallback-{req.country.value.lower()}-bank",
        details={"degraded": True, "reason": "primary_unavailable"},
    )
