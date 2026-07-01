from datetime import datetime, timezone
from uuid import uuid4

import pytest

from onboarding.config import FLOWS_DIR
from onboarding.domain.enums import AccountType, ApplicationStatus, Country
from onboarding.domain.models import Application
from onboarding.flow.engine import FlowEngine
from onboarding.flow.provider import YamlFlowDefinitionProvider


@pytest.fixture
def flow_provider() -> YamlFlowDefinitionProvider:
    return YamlFlowDefinitionProvider(FLOWS_DIR)


@pytest.fixture
def flow_engine(flow_provider: YamlFlowDefinitionProvider) -> FlowEngine:
    return FlowEngine(flow_provider)


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
