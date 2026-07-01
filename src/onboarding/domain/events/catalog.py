from enum import Enum


class EventType(str, Enum):
    # Commands (API → bus)
    START_APPLICATION = "onboarding.application.start"
    SUBMIT_STEP = "onboarding.step.submit"
    FINALIZE_APPLICATION = "onboarding.application.finalize"
    ABANDON_APPLICATION = "onboarding.application.abandon"

    # Shell / coordinator
    APPLICATION_STARTED = "onboarding.application.started"
    STEP_SUBMITTED = "onboarding.step.submitted"
    STEP_ADVANCED = "onboarding.step.advanced"
    APPLICATION_ABANDONED = "onboarding.application.abandoned"
    APPLICATION_SUBMITTED = "onboarding.application.submitted"
    MAIN_PROGRESS_UPDATED = "onboarding.coordinator.progress"

    # Sub-flow / segments
    SUB_FLOW_STARTED = "onboarding.subflow.started"
    SUB_FLOW_COMPLETED = "onboarding.subflow.completed"
    SUB_FLOW_FAILED = "onboarding.subflow.failed"
    SEGMENT_PROGRESS_UPDATED = "onboarding.segment.progress"

    # Integrations
    INTEGRATION_REQUESTED = "onboarding.integration.requested"
    INTEGRATION_COMPLETED = "onboarding.integration.completed"
    INTEGRATION_FAILED = "onboarding.integration.failed"

    # Decision
    DECISION_REQUESTED = "onboarding.decision.requested"
    DECISION_COMPLETED = "onboarding.decision.completed"


def routing_key_for(event_type: EventType, flow_id: str, orchestrator_id: str | None = None) -> str:
    if orchestrator_id:
        return f"onboarding.component.{orchestrator_id}.{flow_id}.{event_type.value}"
    return f"onboarding.{flow_id}.{event_type.value}"
