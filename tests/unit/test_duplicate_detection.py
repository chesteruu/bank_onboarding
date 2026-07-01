import pytest
from fakes import build_event_facade

from onboarding.domain.exceptions import DuplicateDraftError


@pytest.fixture
def service():
    return build_event_facade()


@pytest.mark.asyncio
async def test_submit_same_identifier_raises_duplicate(service):
    app1 = await service.start_application("SE", "private", device_id="d1")
    await service.submit_step(
        app1.id,
        "identity",
        {"national_id": "199001011234", "full_name": "Anna", "date_of_birth": "1990-01-01"},
    )

    app2 = await service.start_application("SE", "private", device_id="d2")
    with pytest.raises(DuplicateDraftError):
        await service.submit_step(
            app2.id,
            "identity",
            {"national_id": "199001011234", "full_name": "Anna", "date_of_birth": "1990-01-01"},
        )


@pytest.mark.asyncio
async def test_continue_duplicate_allowed(service):
    app1 = await service.start_application("SE", "private", device_id="d1")
    await service.submit_step(
        app1.id,
        "identity",
        {"national_id": "199001011234", "full_name": "Anna", "date_of_birth": "1990-01-01"},
    )

    app2 = await service.start_application("SE", "private", device_id="d2")
    app2, _ = await service.submit_step(
        app2.id,
        "identity",
        {"national_id": "199001011234", "full_name": "Anna", "date_of_birth": "1990-01-01"},
        allow_duplicate=True,
    )
    assert app2.current_step_key == "contact"
