from __future__ import annotations

from onboarding.integrations.resilience.policy import AttemptRecord


class IntegrationCallError(Exception):
    """Base error for resilient integration execution."""


class ProviderExhaustedError(IntegrationCallError):
    """A single provider exhausted retries (timeout or transport error)."""

    def __init__(
        self,
        message: str,
        *,
        attempts: list[AttemptRecord],
        last_was_timeout: bool = False,
    ) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.last_was_timeout = last_was_timeout


class AllProvidersFailedError(IntegrationCallError):
    """Every provider (including fallbacks) exhausted retries."""

    def __init__(
        self,
        message: str,
        *,
        attempts: list[AttemptRecord],
        last_was_timeout: bool = False,
    ) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.last_was_timeout = last_was_timeout
