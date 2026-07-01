import pytest
from fakes import build_event_facade

from onboarding.config import FLOWS_DIR
from onboarding.flow.provider import YamlFlowDefinitionProvider


@pytest.fixture
def service():
    return build_event_facade(
        available_flows={"private": ["SE"], "business": []},
    )


@pytest.mark.asyncio
async def test_go_back_from_second_step_updates_resume(service):
    app = await service.start_application("SE", "private", device_id="dev-back")
    await service.submit_step(
        app.id,
        "identity",
        {
            "national_id": "199001011234",
            "full_name": "Anna Andersson",
            "date_of_birth": "1990-01-01",
        },
    )
    token = await service._resume_tokens.get_active_token(app.id)
    data = await service._resume_tokens.validate_token(token)
    assert data is not None
    assert data.current_step_key == "contact"

    redirect = await service.go_back(app.id, "contact")
    assert redirect.endswith("/step/identity")

    updated = await service.get_application(app.id)
    assert updated is not None
    assert updated.current_step_key == "identity"

    data = await service._resume_tokens.validate_token(token)
    assert data is not None
    assert data.current_step_key == "identity"


@pytest.mark.asyncio
async def test_go_back_from_first_step_returns_country_select(service):
    app = await service.start_application("SE", "private", device_id="dev-back-first")
    redirect = await service.go_back(app.id, "identity")
    assert redirect == "/onboarding/select-country?account_type=private"

    unchanged = await service.get_application(app.id)
    assert unchanged is not None
    assert unchanged.current_step_key == "identity"


def test_flow_previous_step_key():
    provider = YamlFlowDefinitionProvider(FLOWS_DIR)
    flow = provider.get_flow_by_id("se_private")
    assert flow.previous_step_key("identity") is None
    assert flow.previous_step_key("contact") == "identity"
    assert flow.previous_step_key("review") == "credit_decision"
