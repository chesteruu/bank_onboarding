from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from onboarding.domain.enums import AccountType, CheckOutcome, Country, IntegrationCheckType
from onboarding.domain.models import Application, ApplicationStatus
from onboarding.integrations.gateway import MockIntegrationGateway
from onboarding.integrations.resilience import IntegrationCallPolicy, ResilientIntegrationCaller


def _app() -> Application:
    now = datetime.now(timezone.utc)
    return Application(
        id=uuid4(),
        request_id="req-test",
        country=Country.SE,
        account_type=AccountType.PRIVATE,
        status=ApplicationStatus.DRAFT,
        current_step_key="identity",
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_gateway_uses_fallback_when_primary_times_out() -> None:
    policy = IntegrationCallPolicy(timeout_seconds=0.05, max_attempts=1, retry_backoff_seconds=0.01)
    caller = ResilientIntegrationCaller(default_policy=policy)
    gateway = MockIntegrationGateway(caller=caller)

    async def never_verify(_req):  # noqa: ANN001
        await asyncio.Event().wait()
        from onboarding.domain.enums import CheckOutcome
        from onboarding.integrations.dtos import IdentityCheckResponse

        return IdentityCheckResponse(
            outcome=CheckOutcome.VERIFIED,
            provider="slow-mock",
            reference="SLOW",
        )

    gateway._identity.verify = never_verify  # type: ignore[method-assign]

    from onboarding.domain.models import FlowStep

    step = FlowStep(key="identity", title="Identity", integrations=["bankid_identity"])
    results = await gateway.run_checks(
        _app(),
        step,
        {"national_id": "1234567890", "full_name": "Test User"},
    )
    assert len(results) == 1
    result = results[0]
    assert result.outcome == CheckOutcome.MANUAL_REVIEW
    assert result.response["details"]["used_fallback"] is True
    assert "fallback" in result.provider


@pytest.mark.asyncio
async def test_gateway_maps_total_failure_to_unreachable() -> None:
    policy = IntegrationCallPolicy(timeout_seconds=0.05, max_attempts=1, retry_backoff_seconds=0.01)
    caller = ResilientIntegrationCaller(default_policy=policy)
    gateway = MockIntegrationGateway(caller=caller)

    async def never(_req):  # noqa: ANN001
        await asyncio.Event().wait()
        return None

    gateway._identity.verify = never  # type: ignore[method-assign]

    from onboarding.integrations.resilience import fallbacks

    fallbacks.degraded_identity = never  # type: ignore[assignment]

    from onboarding.domain.models import FlowStep

    step = FlowStep(key="identity", title="Identity", integrations=["bankid_identity"])
    results = await gateway.run_checks(
        _app(),
        step,
        {"national_id": "1234567890", "full_name": "Test User"},
    )
    assert results[0].outcome == CheckOutcome.TIMEOUT
    assert results[0].provider == "unavailable"
    assert "call_metadata" in results[0].response


@pytest.mark.asyncio
async def test_gateway_bank_timeout_outcome_preserved_for_decision_engine() -> None:
    from onboarding.domain.models import FlowStep

    gateway = MockIntegrationGateway()
    step = FlowStep(key="bank", title="Bank", integrations=["iban_verify"])
    results = await gateway.run_checks(
        _app(),
        step,
        {"iban": "SE1237777777777777777777", "account_holder": "Test"},
    )
    assert len(results) == 1
    assert results[0].check_type == IntegrationCheckType.BANK_ACCOUNT
    assert results[0].outcome == CheckOutcome.TIMEOUT


@pytest.mark.asyncio
async def test_gateway_reuses_prior_result_when_input_unchanged() -> None:
    from onboarding.domain.models import FlowStep

    gateway = MockIntegrationGateway()
    step = FlowStep(key="identity", title="Identity", integrations=["bankid_identity"])
    answers = {"national_id": "199001011234", "full_name": "Verified User"}

    first = await gateway.run_checks(_app(), step, answers)
    assert first[0].reused is False
    assert first[0].outcome == CheckOutcome.VERIFIED

    calls = {"n": 0}
    original_verify = gateway._identity.verify

    async def counting_verify(req):  # noqa: ANN001
        calls["n"] += 1
        return await original_verify(req)

    gateway._identity.verify = counting_verify  # type: ignore[method-assign]

    second = await gateway.run_checks(_app(), step, answers, prior_results=first)
    assert calls["n"] == 0, "external provider must not be called when input is unchanged"
    assert second[0].reused is True
    assert second[0].outcome == first[0].outcome
    assert second[0].request_payload_hash == first[0].request_payload_hash


@pytest.mark.asyncio
async def test_gateway_reruns_when_input_changes() -> None:
    from onboarding.domain.models import FlowStep

    gateway = MockIntegrationGateway()
    step = FlowStep(key="identity", title="Identity", integrations=["bankid_identity"])

    first = await gateway.run_checks(
        _app(), step, {"national_id": "199001011234", "full_name": "Verified User"}
    )
    second = await gateway.run_checks(
        _app(),
        step,
        {"national_id": "199001019999", "full_name": "Mismatch User"},
        prior_results=first,
    )
    assert second[0].reused is False
    assert second[0].outcome == CheckOutcome.DOCUMENT_MISMATCH
    assert second[0].request_payload_hash != first[0].request_payload_hash


@pytest.mark.asyncio
async def test_gateway_reuses_inline_ubo_result() -> None:
    from onboarding.domain.models import FlowStep

    gateway = MockIntegrationGateway()
    step = FlowStep(key="ubo", title="UBO", integrations=["ubo_kyc"])
    answers = {"ubo_count": 2}

    first = await gateway.run_checks(_app(), step, answers)
    assert first[0].reused is False

    second = await gateway.run_checks(_app(), step, answers, prior_results=first)
    assert second[0].reused is True
    assert second[0].check_type == IntegrationCheckType.UBO
