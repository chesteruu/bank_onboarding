from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Generic, Literal, TypeVar

T = TypeVar("T")

AttemptStatus = Literal["success", "timeout", "error"]


@dataclass(frozen=True)
class IntegrationCallPolicy:
    """Production-style limits for a single provider endpoint."""

    timeout_seconds: float = 5.0
    max_attempts: int = 3
    retry_backoff_seconds: float = 0.25
    retry_backoff_multiplier: float = 2.0
    max_backoff_seconds: float = 2.0


@dataclass(frozen=True)
class ProviderSpec(Generic[T]):
    """One integration endpoint (primary or fallback)."""

    name: str
    call: Callable[[], Awaitable[T]]
    policy: IntegrationCallPolicy | None = None


@dataclass
class AttemptRecord:
    provider: str
    attempt: int
    status: AttemptStatus
    latency_ms: float
    error: str | None = None


@dataclass
class IntegrationCallReport(Generic[T]):
    """Successful result plus full observability for audit/decisioning."""

    value: T
    provider: str
    attempts: list[AttemptRecord] = field(default_factory=list)
    used_fallback: bool = False
    fallback_index: int | None = None

    def call_metadata(self) -> dict[str, Any]:
        return {
            "provider_used": self.provider,
            "used_fallback": self.used_fallback,
            "fallback_index": self.fallback_index,
            "attempts": [
                {
                    "provider": a.provider,
                    "attempt": a.attempt,
                    "status": a.status,
                    "latency_ms": round(a.latency_ms, 2),
                    "error": a.error,
                }
                for a in self.attempts
            ],
        }
