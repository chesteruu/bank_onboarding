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
from onboarding.integrations.resilience import (
    AllProvidersFailedError,
    IntegrationCallPolicy,
    IntegrationCallReport,
    ProviderSpec,
    ResilientIntegrationCaller,
)
from onboarding.integrations.resilience import fallbacks as degraded

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
    def __init__(
        self,
        *,
        caller: ResilientIntegrationCaller | None = None,
        policy: IntegrationCallPolicy | None = None,
    ) -> None:
        self._caller = caller or ResilientIntegrationCaller(default_policy=policy)
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
        *,
        prior_results: list[IntegrationResult] | None = None,
    ) -> list[IntegrationResult]:
        prior = _prior_lookup(prior_results)
        results: list[IntegrationResult] = []
        for integration_key in step.integrations:
            result = await self._run_single(
                application.id, application, integration_key, answers, prior
            )
            if result:
                results.append(result)
        return results

    async def _run_single(
        self,
        application_id: UUID,
        application: Application,
        integration_key: str,
        answers: dict[str, Any],
        prior: dict[tuple[IntegrationCheckType, str], IntegrationResult],
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
            return await self._invoke(
                application_id=application_id,
                check_type=check_type,
                request_payload=identity_req.model_dump(),
                providers=[
                    ProviderSpec(
                        f"mock-identity-{application.country.value.lower()}",
                        lambda: self._identity.verify(identity_req),
                    ),
                    ProviderSpec(
                        f"fallback-identity-{application.country.value.lower()}",
                        lambda: degraded.degraded_identity(identity_req),
                    ),
                ],
                ran_at=now,
                prior=prior,
            )

        if integration_key == "address_lookup":
            address_req = AddressCheckRequest(
                country=application.country,
                address_line=answers.get("address_line", ""),
                city=answers.get("city", ""),
                postal_code=answers.get("postal_code", ""),
            )
            return await self._invoke(
                application_id=application_id,
                check_type=check_type,
                request_payload=address_req.model_dump(),
                providers=[
                    ProviderSpec(
                        f"mock-address-{application.country.value.lower()}",
                        lambda: self._address.verify(address_req),
                    ),
                    ProviderSpec(
                        f"fallback-address-{application.country.value.lower()}",
                        lambda: degraded.degraded_address(address_req),
                    ),
                ],
                ran_at=now,
                prior=prior,
            )

        if integration_key in (
            "bolagsverket_registry",
            "registro_mercantil",
            "ceidg_krs_registry",
        ):
            registry_req = RegistryCheckRequest(
                country=application.country,
                company_number=answers.get("company_number", ""),
                company_name=answers.get("company_name", ""),
            )
            provider_name = integration_key.replace("_registry", "").replace("_", "-")
            return await self._invoke(
                application_id=application_id,
                check_type=check_type,
                request_payload=registry_req.model_dump(),
                providers=[
                    ProviderSpec(provider_name, lambda: self._registry.lookup(registry_req)),
                    ProviderSpec(
                        f"fallback-{provider_name}",
                        lambda: degraded.degraded_registry(registry_req),
                    ),
                ],
                ran_at=now,
                prior=prior,
            )

        if integration_key == "signatory_check":
            payload_hash = hash_payload({"signatory": answers.get("signatory_name", "")})
            reused = _reuse(prior, IntegrationCheckType.SIGNATORY, payload_hash)
            if reused is not None:
                return reused
            return IntegrationResult(
                application_id=application_id,
                check_type=IntegrationCheckType.SIGNATORY,
                provider="mock-signatory",
                request_payload_hash=payload_hash,
                response={"verified": True},
                outcome=CheckOutcome.VERIFIED,
                ran_at=now,
            )

        if integration_key == "ubo_kyc":
            ubo_count = int(answers.get("ubo_count", 0))
            payload_hash = hash_payload({"ubo_count": ubo_count})
            reused = _reuse(prior, IntegrationCheckType.UBO, payload_hash)
            if reused is not None:
                return reused
            outcome = CheckOutcome.VERIFIED if ubo_count > 0 else CheckOutcome.MANUAL_REVIEW
            return IntegrationResult(
                application_id=application_id,
                check_type=IntegrationCheckType.UBO,
                provider="mock-ubo",
                request_payload_hash=payload_hash,
                response={"ubo_count": ubo_count},
                outcome=outcome,
                ran_at=now,
            )

        if integration_key == "sanctions_screen":
            name = (
                answers.get("full_name")
                or answers.get("company_name")
                or answers.get("signatory_name", "")
            )
            sanctions_req = SanctionsCheckRequest(country=application.country, name=name)
            return await self._invoke(
                application_id=application_id,
                check_type=check_type,
                request_payload=sanctions_req.model_dump(),
                providers=[
                    ProviderSpec(
                        f"mock-sanctions-{application.country.value.lower()}",
                        lambda: self._sanctions.screen(sanctions_req),
                    ),
                    ProviderSpec(
                        f"fallback-sanctions-{application.country.value.lower()}",
                        lambda: degraded.degraded_sanctions(sanctions_req),
                    ),
                ],
                ran_at=now,
                prior=prior,
            )

        if integration_key in ("credit_bureau", "bik_credit", "affordability"):
            credit_req = CreditCheckRequest(
                country=application.country,
                national_id=answers.get("national_id")
                or answers.get("pesel")
                or answers.get("dni"),
                company_number=answers.get("company_number"),
                monthly_income=_float_or_none(answers.get("monthly_income")),
                monthly_expenses=_float_or_none(answers.get("monthly_expenses")),
            )
            ctype = (
                IntegrationCheckType.AFFORDABILITY
                if integration_key == "affordability"
                else IntegrationCheckType.CREDIT
            )
            return await self._invoke(
                application_id=application_id,
                check_type=ctype,
                request_payload=credit_req.model_dump(),
                providers=[
                    ProviderSpec(
                        f"mock-credit-{application.country.value.lower()}",
                        lambda: self._credit.check(credit_req),
                    ),
                    ProviderSpec(
                        f"fallback-credit-{application.country.value.lower()}",
                        lambda: degraded.degraded_credit(credit_req),
                    ),
                ],
                ran_at=now,
                prior=prior,
            )

        if integration_key == "kyb_check":
            kyb_req = KybCheckRequest(
                country=application.country,
                company_number=answers.get("company_number", ""),
                ubo_count=int(answers.get("ubo_count", 0)),
            )
            return await self._invoke(
                application_id=application_id,
                check_type=check_type,
                request_payload=kyb_req.model_dump(),
                providers=[
                    ProviderSpec(
                        f"mock-kyb-{application.country.value.lower()}",
                        lambda: self._kyb.verify(kyb_req),
                    ),
                    ProviderSpec(
                        f"fallback-kyb-{application.country.value.lower()}",
                        lambda: degraded.degraded_kyb(kyb_req),
                    ),
                ],
                ran_at=now,
                prior=prior,
            )

        if integration_key in ("iban_verify", "bank_verify"):
            bank_req = BankAccountCheckRequest(
                country=application.country,
                iban=answers.get("iban", ""),
                account_holder=answers.get("account_holder") or answers.get("company_name", ""),
            )
            return await self._invoke(
                application_id=application_id,
                check_type=check_type,
                request_payload=bank_req.model_dump(),
                providers=[
                    ProviderSpec(
                        f"mock-bank-{application.country.value.lower()}",
                        lambda: self._bank.verify(bank_req),
                    ),
                    ProviderSpec(
                        f"fallback-bank-{application.country.value.lower()}",
                        lambda: degraded.degraded_bank(bank_req),
                    ),
                ],
                ran_at=now,
                prior=prior,
            )

        return None

    async def _invoke(
        self,
        *,
        application_id: UUID,
        check_type: IntegrationCheckType,
        request_payload: dict[str, Any],
        providers: list[ProviderSpec[Any]],
        ran_at: datetime,
        prior: dict[tuple[IntegrationCheckType, str], IntegrationResult],
    ) -> IntegrationResult:
        payload_hash = hash_payload(request_payload)

        reused = _reuse(prior, check_type, payload_hash)
        if reused is not None:
            return reused

        try:
            report = await self._caller.execute(providers)
        except AllProvidersFailedError as exc:
            outcome = CheckOutcome.TIMEOUT if exc.last_was_timeout else CheckOutcome.UNREACHABLE
            return IntegrationResult(
                application_id=application_id,
                check_type=check_type,
                provider="unavailable",
                request_payload_hash=payload_hash,
                response={
                    "error": str(exc),
                    "call_metadata": _call_metadata_from_attempts(exc.attempts),
                },
                outcome=outcome,
                ran_at=ran_at,
            )

        response = _enrich_response(report)
        return IntegrationResult(
            application_id=application_id,
            check_type=check_type,
            provider=_response_provider(response, report),
            request_payload_hash=payload_hash,
            response=response,
            outcome=CheckOutcome(response["outcome"]),
            ran_at=ran_at,
        )


def _prior_lookup(
    prior_results: list[IntegrationResult] | None,
) -> dict[tuple[IntegrationCheckType, str], IntegrationResult]:
    """Index prior results by (check_type, payload hash) for idempotent reuse.

    Later results win so we reuse the most recent outcome for a given input."""
    lookup: dict[tuple[IntegrationCheckType, str], IntegrationResult] = {}
    for result in prior_results or []:
        lookup[(result.check_type, result.request_payload_hash)] = result
    return lookup


def _reuse(
    prior: dict[tuple[IntegrationCheckType, str], IntegrationResult],
    check_type: IntegrationCheckType,
    payload_hash: str,
) -> IntegrationResult | None:
    """Return a prior result flagged as reused when the input is unchanged.

    This avoids re-running expensive or sensitive external checks unless the
    request payload changed. The returned copy is marked ``reused`` so callers
    can skip re-persisting it while still driving flow progression."""
    match = prior.get((check_type, payload_hash))
    if match is None:
        return None
    return match.model_copy(update={"reused": True})


def _enrich_response(report: IntegrationCallReport[Any]) -> dict[str, Any]:
    payload: dict[str, Any] = report.value.model_dump(mode="json")
    details = dict(payload.get("details") or {})
    details.update(report.call_metadata())
    payload["details"] = details
    return payload


def _response_provider(response: dict[str, Any], report: IntegrationCallReport[Any]) -> str:
    return str(response.get("provider") or report.provider)


def _call_metadata_from_attempts(attempts: list[Any]) -> dict[str, Any]:
    return {
        "attempts": [
            {
                "provider": a.provider,
                "attempt": a.attempt,
                "status": a.status,
                "latency_ms": round(a.latency_ms, 2),
                "error": a.error,
            }
            for a in attempts
        ],
    }


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)
