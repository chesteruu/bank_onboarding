import pytest
from fakes import build_event_facade


@pytest.fixture
def service():
    return build_event_facade()


@pytest.mark.asyncio
async def test_list_applications(service):
    app1 = await service.start_application("SE", "private", device_id="d1")
    app2 = await service.start_application("ES", "business", device_id="d2")

    apps = await service.list_applications()

    assert len(apps) == 2
    ids = {a.id for a in apps}
    assert app1.id in ids
    assert app2.id in ids


@pytest.mark.asyncio
async def test_get_admin_detail_includes_segments(service):
    app = await service.start_application("SE", "private", device_id="d1")
    await service.submit_step(
        app.id,
        "identity",
        {
            "national_id": "199001011234",
            "full_name": "Anna Andersson",
            "date_of_birth": "1990-01-01",
        },
    )
    detail = await service.get_admin_application_detail(app.id)
    assert "segments" in detail
    assert len(detail["segments"]) >= 1
