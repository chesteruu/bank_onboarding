from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from onboarding.audit.redaction import hash_payload
from onboarding.domain.enums import CheckOutcome, IntegrationCheckType
from onboarding.domain.models import Application, FlowStep, IntegrationResult
from onboarding.integrations.dtos import (
    AddressCheckRequest,
    BankAccountCheckRequest,
    CreditCheckRequest,
    IdentityCheckRequest,
    KybCheckRequest,
    RegistryCheckRequest,
    SanctionsCheckRequest,
)
from onboarding.integrations.mocks.bank_account import MockBankAccountClient
from onboarding.integrations.mocks.credit import MockCreditClient
from onboarding.integrations.mocks.identity import MockAddressClient, MockIdentityClient
from onboarding.integrations.mocks.kyb import MockKybClient
from onboarding.integrations.mocks.registry import MockRegistryClient
from onboarding.integrations.mocks.sanctions import MockSanctionsClient

INTEGRATION_MAP: dict[str, IntegrationCheckType] = {
    "bankid_identity": IntegrationCheckType.IDENTITY,
    "dni_nie_check": IntegrationCheckType.IDENTITY,
    "pesel_eid_check": IntegrationCheckType.IDENTITY,
    "address_lookup": IntegrationCheckType.ADDRESS,
    "bolagsverket_registry": IntegrationCheckType.REGISTRY,
    "registro_mercantil": IntegrationCheckType.REGISTRY,
    "ceidg_krs_registry": IntegrationCheckType.REGISTRY,
    "signatory_check": IntegrationCheckType.SIGNATORY,
    "ubo_kyc": IntegrationCheckType.UBO,
    "sanctions_screen": IntegrationCheckType.SANCTIONS,
    "credit_bureau": IntegrationCheckType.CREDIT,
    "bik_credit": IntegrationCheckType.CREDIT,
    "affordability": IntegrationCheckType.AFFORDABILITY,
    "kyb_check": IntegrationCheckType.KYB,
    "iban_verify": IntegrationCheckType.BANK_ACCOUNT,
    "bank_verify": IntegrationCheckType.BANK_ACCOUNT,
}


class MockIntegrationGateway:
    def __init__(self) -> None:
        self._identity = MockIdentityClient()
        self._address = MockAddressClient()
        self._registry = MockRegistryClient()
        self._kyb = MockKybClient()
        self._sanctions = MockSanctionsClient()
        self._credit = MockCreditClient()
        self._bank = MockBankAccountClient()

    async def run_checks(
        self,
        application: Application,
        step: FlowStep,
        answers: dict[str, Any],
    ) -> list[IntegrationResult]:
        results: list[IntegrationResult] = []
        for integration_key in step.integrations:
            result = await self._run_single(application.id, application, integration_key, answers)
            if result:
                results.append(result)
        return results

    async def _run_single(
        self,
        application_id: UUID,
        application: Application,
        integration_key: str,
        answers: dict[str, Any],
    ) -> IntegrationResult | None:
        check_type = INTEGRATION_MAP.get(integration_key, IntegrationCheckType.IDENTITY)
        now = datetime.now(timezone.utc)

        if integration_key in ("bankid_identity", "dni_nie_check", "pesel_eid_check"):
            identity_req = IdentityCheckRequest(
                country=application.country,
                national_id=answers.get("national_id")
                or answers.get("pesel")
                or answers.get("dni", ""),
                full_name=answers.get("full_name", ""),
                date_of_birth=answers.get("date_of_birth"),
            )
            identity_resp = await self._identity.verify(identity_req)
            payload = identity_req.model_dump()
            return IntegrationResult(
                application_id=application_id,
                check_type=check_type,
                provider=identity_resp.provider,
                request_payload_hash=hash_payload(payload),
                response=identity_resp.model_dump(mode="json"),
                outcome=identity_resp.outcome,
                ran_at=now,
            )

        elif integration_key == "address_lookup":
            address_req = AddressCheckRequest(
                country=application.country,
                address_line=answers.get("address_line", ""),
                city=answers.get("city", ""),
                postal_code=answers.get("postal_code", ""),
            )
            address_resp = await self._address.verify(address_req)
            return IntegrationResult(
                application_id=application_id,
                check_type=check_type,
                provider=address_resp.provider,
                request_payload_hash=hash_payload(address_req.model_dump()),
                response=address_resp.model_dump(mode="json"),
                outcome=address_resp.outcome,
                ran_at=now,
            )

        elif integration_key in (
            "bolagsverket_registry",
            "registro_mercantil",
            "ceidg_krs_registry",
        ):
            registry_req = RegistryCheckRequest(
                country=application.country,
                company_number=answers.get("company_number", ""),
                company_name=answers.get("company_name", ""),
            )
            registry_resp = await self._registry.lookup(registry_req)
            return IntegrationResult(
                application_id=application_id,
                check_type=check_type,
                provider=registry_resp.provider,
                request_payload_hash=hash_payload(registry_req.model_dump()),
                response=registry_resp.model_dump(mode="json"),
                outcome=registry_resp.outcome,
                ran_at=now,
            )

        elif integration_key == "signatory_check":
            return IntegrationResult(
                application_id=application_id,
                check_type=IntegrationCheckType.SIGNATORY,
                provider="mock-signatory",
                request_payload_hash=hash_payload({"signatory": answers.get("signatory_name", "")}),
                response={"verified": True},
                outcome=CheckOutcome.VERIFIED,
                ran_at=now,
            )

        elif integration_key == "ubo_kyc":
            ubo_count = int(answers.get("ubo_count", 0))
            outcome = CheckOutcome.VERIFIED if ubo_count > 0 else CheckOutcome.MANUAL_REVIEW
            return IntegrationResult(
                application_id=application_id,
                check_type=IntegrationCheckType.UBO,
                provider="mock-ubo",
                request_payload_hash=hash_payload({"ubo_count": ubo_count}),
                response={"ubo_count": ubo_count},
                outcome=outcome,
                ran_at=now,
            )

        elif integration_key == "sanctions_screen":
            name = (
                answers.get("full_name")
                or answers.get("company_name")
                or answers.get("signatory_name", "")
            )
            sanctions_req = SanctionsCheckRequest(country=application.country, name=name)
            sanctions_resp = await self._sanctions.screen(sanctions_req)
            return IntegrationResult(
                application_id=application_id,
                check_type=check_type,
                provider=sanctions_resp.provider,
                request_payload_hash=hash_payload(sanctions_req.model_dump()),
                response=sanctions_resp.model_dump(mode="json"),
                outcome=sanctions_resp.outcome,
                ran_at=now,
            )

        elif integration_key in ("credit_bureau", "bik_credit", "affordability"):
            credit_req = CreditCheckRequest(
                country=application.country,
                national_id=answers.get("national_id")
                or answers.get("pesel")
                or answers.get("dni"),
                company_number=answers.get("company_number"),
                monthly_income=_float_or_none(answers.get("monthly_income")),
                monthly_expenses=_float_or_none(answers.get("monthly_expenses")),
            )
            credit_resp = await self._credit.check(credit_req)
            ctype = (
                IntegrationCheckType.AFFORDABILITY
                if integration_key == "affordability"
                else IntegrationCheckType.CREDIT
            )
            return IntegrationResult(
                application_id=application_id,
                check_type=ctype,
                provider=credit_resp.provider,
                request_payload_hash=hash_payload(credit_req.model_dump()),
                response=credit_resp.model_dump(mode="json"),
                outcome=credit_resp.outcome,
                ran_at=now,
            )

        elif integration_key == "kyb_check":
            kyb_req = KybCheckRequest(
                country=application.country,
                company_number=answers.get("company_number", ""),
                ubo_count=int(answers.get("ubo_count", 0)),
            )
            kyb_resp = await self._kyb.verify(kyb_req)
            return IntegrationResult(
                application_id=application_id,
                check_type=check_type,
                provider=kyb_resp.provider,
                request_payload_hash=hash_payload(kyb_req.model_dump()),
                response=kyb_resp.model_dump(mode="json"),
                outcome=kyb_resp.outcome,
                ran_at=now,
            )

        elif integration_key in ("iban_verify", "bank_verify"):
            bank_req = BankAccountCheckRequest(
                country=application.country,
                iban=answers.get("iban", ""),
                account_holder=answers.get("account_holder") or answers.get("company_name", ""),
            )
            bank_resp = await self._bank.verify(bank_req)
            outcome = bank_resp.outcome
            if outcome == CheckOutcome.TIMEOUT:
                outcome = CheckOutcome.MANUAL_REVIEW
            return IntegrationResult(
                application_id=application_id,
                check_type=check_type,
                provider=bank_resp.provider,
                request_payload_hash=hash_payload(bank_req.model_dump()),
                response=bank_resp.model_dump(mode="json"),
                outcome=outcome,
                ran_at=now,
            )

        return None


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)
