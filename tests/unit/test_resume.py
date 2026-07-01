import pytest
from fakes import build_event_facade

from onboarding.domain.enums import ApplicationStatus


@pytest.fixture
def service():
    return build_event_facade(
        available_flows={"private": ["SE", "ES"], "business": ["SE", "PL"]},
    )


@pytest.mark.asyncio
async def test_resume_by_device_finds_latest_draft(service):
    device_id = "device-123"
    app1 = await service.start_application("SE", "private", device_id=device_id)
    app2 = await service.start_application("ES", "private", device_id=device_id)

    abandoned = await service._repo.get(app1.id)
    assert abandoned is not None
    assert abandoned.status.value == "abandoned"

    resumed = await service.resume_by_device(device_id)

    assert resumed is not None
    assert resumed.id == app2.id


@pytest.mark.asyncio
async def test_start_over_abandons_draft_and_revokes_tokens(service):
    device_id = "device-start-over"
    app = await service.start_application("SE", "private", device_id=device_id)
    assert len(service._resume_tokens.tokens) == 1

    await service.start_over(device_id)

    abandoned = await service._repo.get(app.id)
    assert abandoned is not None
    assert abandoned.status.value == "abandoned"
    assert abandoned.current_step_key is None
    assert await service.resume_by_device(device_id) is None
    assert all(t in service._resume_tokens.used for t in service._resume_tokens.tokens)


@pytest.mark.asyncio
async def test_start_over_allows_fresh_application(service):
    device_id = "device-fresh"
    await service.start_application("SE", "private", device_id=device_id)
    await service.start_over(device_id)

    app = await service.start_application("ES", "private", device_id=device_id)
    assert app.country.value == "ES"
    resumed = await service.resume_by_device(device_id)
    assert resumed is not None
    assert resumed.id == app.id


@pytest.mark.asyncio
async def test_resume_by_device_ignores_non_draft(service):
    device_id = "device-456"
    app = await service.start_application("SE", "private", device_id=device_id)
    await service._repo.update_status(app.id, ApplicationStatus.SUBMITTED)

    resumed = await service.resume_by_device(device_id)

    assert resumed is None


@pytest.mark.asyncio
async def test_resume_by_device_returns_none_when_no_app(service):
    resumed = await service.resume_by_device("unknown-device")
    assert resumed is None


@pytest.mark.asyncio
async def test_device_id_is_stored_on_application(service):
    device_id = "device-789"
    app = await service.start_application("SE", "private", device_id=device_id)
    assert app.device_id == device_id


@pytest.mark.asyncio
async def test_start_application_validates_allowed_country(service):
    with pytest.raises(ValueError, match="not available"):
        await service.start_application("PL", "private")


@pytest.mark.asyncio
async def test_start_application_validates_existing_flow(service):
    from onboarding.config import FLOWS_DIR
    from onboarding.flow.provider import YamlFlowDefinitionProvider

    provider = YamlFlowDefinitionProvider(FLOWS_DIR)
    with pytest.raises(KeyError, match="No flow defined"):
        provider.get_flow_by_id("nonexistent_flow")


@pytest.mark.asyncio
async def test_resume_by_token_finds_draft(service):
    app = await service.start_application("SE", "private", device_id="device-token")
    token = await service._resume_tokens.get_active_token(app.id)
    assert token is not None

    resumed = await service.resume_by_token(token)
    assert resumed is not None
    assert resumed.id == app.id


@pytest.mark.asyncio
async def test_resume_by_token_rejects_unknown(service):
    assert await service.resume_by_token("not-a-real-token") is None


@pytest.mark.asyncio
async def test_get_resume_link(service):
    app = await service.start_application("SE", "private")
    link = await service.get_resume_link(app.id, "http://localhost:8000")
    assert link is not None
    assert link.startswith("http://localhost:8000/onboarding/resume/")


@pytest.mark.asyncio
async def test_sync_resume_token_updates_step(service):
    app = await service.start_application("SE", "private")
    token_before = await service._resume_tokens.get_active_token(app.id)

    app, _ = await service.submit_step(
        app.id,
        "identity",
        {
            "national_id": "199001011234",
            "full_name": "Anna Andersson",
            "date_of_birth": "1990-01-01",
        },
    )
    token_after = await service._resume_tokens.get_active_token(app.id)
    assert token_before == token_after
    data = await service._resume_tokens.validate_token(token_after)
    assert data is not None
    assert data.current_step_key == "contact"


@pytest.mark.asyncio
async def test_get_status_reports_segments(service):
    app = await service.start_application("SE", "private")
    await service.submit_step(
        app.id,
        "identity",
        {
            "national_id": "199001011234",
            "full_name": "Anna Andersson",
            "date_of_birth": "1990-01-01",
        },
    )
    status = await service.get_status(app.id)
    assert status["ready"] is True
    assert len(status["segments"]) >= 1


def test_allowed_countries(service):
    assert service.allowed_countries("private") == ["SE", "ES"]
    assert service.allowed_countries("business") == ["SE", "PL"]
    assert service.allowed_countries("unknown") == []
