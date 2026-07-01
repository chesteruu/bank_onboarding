from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from onboarding.domain.enums import (
    AccountType,
    ApplicationStatus,
    CheckOutcome,
    Country,
    DecisionOutcome,
    IntegrationCheckType,
)


class FlowStep(BaseModel):
    key: str
    title: str
    form_schema: str | None = None
    integrations: list[str] = Field(default_factory=list)
    orchestrator: str | None = None
    component_flow: str | None = None
    on_complete: str | None = None
    triggers_decision: bool = False
    is_review: bool = False
    child_flow_route: dict[str, Any] | None = None


class FlowDefinition(BaseModel):
    flow_id: str
    country: Country | None = None
    account_type: AccountType | None = None
    child_flows: dict[str, str] = Field(default_factory=dict)
    steps: list[FlowStep]

    def step_keys(self) -> list[str]:
        return [s.key for s in self.steps]

    def get_step(self, key: str) -> FlowStep | None:
        return next((s for s in self.steps if s.key == key), None)

    def next_step_key(self, current_key: str) -> str | None:
        step = self.get_step(current_key)
        if step and step.on_complete:
            return step.on_complete
        keys = self.step_keys()
        try:
            idx = keys.index(current_key)
        except ValueError:
            return None
        if idx + 1 < len(keys):
            return keys[idx + 1]
        return None

    def previous_step_key(self, current_key: str) -> str | None:
        keys = self.step_keys()
        try:
            idx = keys.index(current_key)
        except ValueError:
            return None
        if idx > 0:
            return keys[idx - 1]
        return None


class Application(BaseModel):
    id: UUID
    request_id: str
    country: Country
    account_type: AccountType
    device_id: str | None = None
    identifier_hash: str | None = None
    flow_id: str | None = None
    status: ApplicationStatus = ApplicationStatus.DRAFT
    current_step_key: str | None = None
    final_decision: DecisionOutcome | None = None
    created_at: datetime
    updated_at: datetime


class StepSubmission(BaseModel):
    application_id: UUID
    step_key: str
    answers: dict[str, Any]
    completed_at: datetime
    input_hash: str | None = None


class IntegrationResult(BaseModel):
    application_id: UUID
    check_type: IntegrationCheckType
    provider: str
    request_payload_hash: str
    response: dict[str, Any]
    outcome: CheckOutcome
    ran_at: datetime


class AuditEvent(BaseModel):
    id: UUID | None = None
    application_id: UUID
    event_type: str
    actor: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class FlowEvent(BaseModel):
    """A domain event emitted by a flow stage and routed to a trace table."""

    application_id: UUID
    event_type: str
    actor: str = "system"
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class DecisionResult(BaseModel):
    outcome: DecisionOutcome
    reasons: list[str] = Field(default_factory=list)


class ResumeTokenData(BaseModel):
    application_id: UUID
    current_step_key: str | None = None
    identifier_hash: str | None = None
    created_at: datetime | None = None


class ProgressInfo(BaseModel):
    current_step: int
    total_steps: int
    percent: int
    current_step_key: str
    current_step_title: str
