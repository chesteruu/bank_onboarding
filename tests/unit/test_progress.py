from datetime import datetime, timezone
from uuid import uuid4

import pytest

from onboarding.config import FLOWS_DIR
from onboarding.domain.enums import AccountType, ApplicationStatus, Country
from onboarding.domain.events.segment import FlowSegment, SegmentStatus
from onboarding.domain.models import Application
from onboarding.flow.progress import compute_aggregate_progress
from onboarding.flow.provider import YamlFlowDefinitionProvider


@pytest.fixture
def sample_application() -> Application:
    now = datetime.now(timezone.utc)
    return Application(
        id=uuid4(),
        request_id="req_test123",
        country=Country.SE,
        account_type=AccountType.PRIVATE,
        status=ApplicationStatus.DRAFT,
        current_step_key="identity",
        created_at=now,
        updated_at=now,
    )


def test_aggregate_progress_with_active_segment(sample_application):
    provider = YamlFlowDefinitionProvider(FLOWS_DIR)
    flow = provider.get_flow(Country.SE, AccountType.PRIVATE)
    segments = [
        FlowSegment(
            application_id=sample_application.id,
            segment_key="identity",
            orchestrator_id="identity",
            component_flow_id="components/identity/se_private.yaml",
            status=SegmentStatus.PROCESSING,
            internal_step_key="bankid_verify",
            internal_total_steps=2,
            percent=50,
        )
    ]
    progress = compute_aggregate_progress(sample_application, flow, segments)
    assert progress.total_steps == 7
    assert progress.active_segment is not None
    assert progress.percent > 0
    assert progress.ready is False
