from __future__ import annotations

import asyncio

import pytest

from onboarding.integrations.resilience import (
    AllProvidersFailedError,
    IntegrationCallPolicy,
    ProviderSpec,
    ResilientIntegrationCaller,
)


@pytest.mark.asyncio
async def test_primary_succeeds_on_first_attempt() -> None:
    caller = ResilientIntegrationCaller(
        IntegrationCallPolicy(timeout_seconds=1.0, max_attempts=3, retry_backoff_seconds=0.01)
    )
    calls = {"n": 0}

    async def primary() -> str:
        calls["n"] += 1
        return "ok"

    report = await caller.execute([ProviderSpec("primary", primary)])
    assert report.value == "ok"
    assert report.provider == "primary"
    assert report.used_fallback is False
    assert calls["n"] == 1
    assert len(report.attempts) == 1
    assert report.attempts[0].status == "success"


@pytest.mark.asyncio
async def test_retries_then_succeeds() -> None:
    caller = ResilientIntegrationCaller(
        IntegrationCallPolicy(timeout_seconds=1.0, max_attempts=3, retry_backoff_seconds=0.01)
    )
    calls = {"n": 0}

    async def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("upstream reset")
        return "recovered"

    report = await caller.execute([ProviderSpec("flaky", flaky)])
    assert report.value == "recovered"
    assert calls["n"] == 3
    assert len(report.attempts) == 3
    assert report.attempts[0].status == "error"
    assert report.attempts[2].status == "success"


@pytest.mark.asyncio
async def test_timeout_triggers_fallback() -> None:
    caller = ResilientIntegrationCaller(
        IntegrationCallPolicy(timeout_seconds=0.05, max_attempts=2, retry_backoff_seconds=0.01)
    )

    async def never_completes() -> str:
        await asyncio.Event().wait()
        return "late"

    async def fallback() -> str:
        return "degraded"

    report = await caller.execute(
        [
            ProviderSpec("slow", never_completes),
            ProviderSpec("fallback", fallback),
        ]
    )
    assert report.value == "degraded"
    assert report.used_fallback is True
    assert report.fallback_index == 1
    assert any(a.status == "timeout" for a in report.attempts)


@pytest.mark.asyncio
async def test_all_providers_fail_raises() -> None:
    caller = ResilientIntegrationCaller(
        IntegrationCallPolicy(timeout_seconds=0.05, max_attempts=1, retry_backoff_seconds=0.01)
    )

    async def never_completes() -> str:
        await asyncio.Event().wait()
        return "late"

    with pytest.raises(AllProvidersFailedError) as exc_info:
        await caller.execute(
            [
                ProviderSpec("slow-a", never_completes),
                ProviderSpec("slow-b", never_completes),
            ]
        )
    assert exc_info.value.last_was_timeout is True
    assert len(exc_info.value.attempts) == 2


@pytest.mark.asyncio
async def test_call_metadata_includes_attempts() -> None:
    caller = ResilientIntegrationCaller(
        IntegrationCallPolicy(timeout_seconds=1.0, max_attempts=2, retry_backoff_seconds=0.01)
    )
    calls = {"n": 0}

    async def once_flaky() -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("503")
        return "ok"

    report = await caller.execute([ProviderSpec("svc", once_flaky)])
    meta = report.call_metadata()
    assert meta["provider_used"] == "svc"
    assert meta["used_fallback"] is False
    assert len(meta["attempts"]) == 2
