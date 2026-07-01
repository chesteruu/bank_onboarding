from typing import Any, Protocol
from uuid import UUID

from onboarding.domain.models import AuditEvent


class IAuditLogger(Protocol):
    async def log_event(
        self,
        application_id: UUID,
        event_type: str,
        *,
        actor: str = "system",
        metadata: dict[str, Any] | None = None,
    ) -> AuditEvent: ...

    async def log_step_completed(
        self, application_id: UUID, step_key: str, *, actor: str = "applicant"
    ) -> AuditEvent: ...

    async def log_integration_result(
        self,
        application_id: UUID,
        check_type: str,
        outcome: str,
        *,
        provider: str,
    ) -> AuditEvent: ...

    async def log_decision(
        self, application_id: UUID, outcome: str, reasons: list[str]
    ) -> AuditEvent: ...

    async def log_submitted(self, application_id: UUID) -> AuditEvent: ...

    async def get_events(self, application_id: UUID) -> list[AuditEvent]: ...
