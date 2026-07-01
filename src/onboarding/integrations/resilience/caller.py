from __future__ import annotations

import asyncio
import time
from typing import TypeVar

from onboarding.integrations.resilience.errors import (
    AllProvidersFailedError,
    ProviderExhaustedError,
)
from onboarding.integrations.resilience.policy import (
    AttemptRecord,
    IntegrationCallPolicy,
    IntegrationCallReport,
    ProviderSpec,
)

T = TypeVar("T")


class ResilientIntegrationCaller:
    """Execute integration calls with timeout, retry, and ordered fallback providers.

    Typical production wiring:
    - ``providers[0]`` primary vendor API
    - ``providers[1+]`` secondary vendor, regional mirror, or controlled degraded path
    """

    def __init__(self, default_policy: IntegrationCallPolicy | None = None) -> None:
        self._default_policy = default_policy or IntegrationCallPolicy()

    async def execute(self, providers: list[ProviderSpec[T]]) -> IntegrationCallReport[T]:
        if not providers:
            raise ValueError("At least one provider is required")

        all_attempts: list[AttemptRecord] = []
        last_was_timeout = False

        for index, provider in enumerate(providers):
            policy = provider.policy or self._default_policy
            try:
                value, attempts = await self._execute_provider(provider, policy)
                all_attempts.extend(attempts)
                return IntegrationCallReport(
                    value=value,
                    provider=provider.name,
                    attempts=all_attempts,
                    used_fallback=index > 0,
                    fallback_index=index if index > 0 else None,
                )
            except ProviderExhaustedError as exc:
                all_attempts.extend(exc.attempts)
                last_was_timeout = exc.last_was_timeout
                continue

        raise AllProvidersFailedError(
            f"All {len(providers)} integration provider(s) failed",
            attempts=all_attempts,
            last_was_timeout=last_was_timeout,
        )

    async def _execute_provider(
        self,
        provider: ProviderSpec[T],
        policy: IntegrationCallPolicy,
    ) -> tuple[T, list[AttemptRecord]]:
        attempts: list[AttemptRecord] = []
        backoff = policy.retry_backoff_seconds
        last_was_timeout = False

        for attempt in range(1, policy.max_attempts + 1):
            started = time.perf_counter()
            try:
                value = await asyncio.wait_for(
                    provider.call(),
                    timeout=policy.timeout_seconds,
                )
            except (asyncio.TimeoutError, asyncio.CancelledError) as exc:
                last_was_timeout = True
                latency_ms = (time.perf_counter() - started) * 1000
                attempts.append(
                    AttemptRecord(
                        provider=provider.name,
                        attempt=attempt,
                        status="timeout",
                        latency_ms=latency_ms,
                        error="deadline exceeded",
                    )
                )
                if attempt >= policy.max_attempts:
                    raise ProviderExhaustedError(
                        f"{provider.name} timed out after {policy.max_attempts} attempt(s)",
                        attempts=attempts,
                        last_was_timeout=True,
                    ) from exc
                await asyncio.sleep(backoff)
                backoff = min(backoff * policy.retry_backoff_multiplier, policy.max_backoff_seconds)
                continue
            except Exception as exc:
                latency_ms = (time.perf_counter() - started) * 1000
                attempts.append(
                    AttemptRecord(
                        provider=provider.name,
                        attempt=attempt,
                        status="error",
                        latency_ms=latency_ms,
                        error=str(exc),
                    )
                )
                if attempt >= policy.max_attempts:
                    raise ProviderExhaustedError(
                        f"{provider.name} failed after {policy.max_attempts} attempt(s): {exc}",
                        attempts=attempts,
                        last_was_timeout=last_was_timeout,
                    ) from exc
                await asyncio.sleep(backoff)
                backoff = min(backoff * policy.retry_backoff_multiplier, policy.max_backoff_seconds)
                continue

            latency_ms = (time.perf_counter() - started) * 1000
            attempts.append(
                AttemptRecord(
                    provider=provider.name,
                    attempt=attempt,
                    status="success",
                    latency_ms=latency_ms,
                )
            )
            return value, attempts

        raise ProviderExhaustedError(
            f"{provider.name} exhausted attempts",
            attempts=attempts,
            last_was_timeout=last_was_timeout,
        )
