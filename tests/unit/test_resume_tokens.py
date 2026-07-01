from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fakes import FakeResumeTokenService

from onboarding.domain.models import ResumeTokenData


class _ExpiredFakeResumeTokenService(FakeResumeTokenService):
    async def create_token(self, application_id, resumption_data):
        token = await super().create_token(application_id, resumption_data)

        self.expires_at[token] = datetime.now(timezone.utc) - timedelta(hours=1)
        return token


@pytest.fixture
def service():
    return FakeResumeTokenService()


@pytest.mark.asyncio
async def test_create_and_validate_token(service):
    app_id = uuid4()
    data = ResumeTokenData(application_id=app_id, current_step_key="identity")

    token = await service.create_token(app_id, data)
    validated = await service.validate_token(token)

    assert validated is not None
    assert validated.application_id == app_id
    assert validated.current_step_key == "identity"


@pytest.mark.asyncio
async def test_used_token_is_invalid(service):
    app_id = uuid4()
    data = ResumeTokenData(application_id=app_id)

    token = await service.create_token(app_id, data)
    await service.mark_used(token)

    assert await service.validate_token(token) is None


@pytest.mark.asyncio
async def test_unknown_token_is_invalid(service):
    assert await service.validate_token("not-a-token") is None


@pytest.mark.asyncio
async def test_expired_token_is_invalid():
    expired_service = _ExpiredFakeResumeTokenService()
    app_id = uuid4()
    data = ResumeTokenData(application_id=app_id)

    token = await expired_service.create_token(app_id, data)
    assert await expired_service.validate_token(token) is None


@pytest.mark.asyncio
async def test_get_active_token(service):
    app_id = uuid4()
    token = await service.create_token(app_id, ResumeTokenData(application_id=app_id))
    assert await service.get_active_token(app_id) == token


@pytest.mark.asyncio
async def test_sync_resumption_updates_existing_token(service):
    app_id = uuid4()
    token = await service.create_token(
        app_id, ResumeTokenData(application_id=app_id, current_step_key="identity")
    )

    await service.sync_resumption(
        app_id, ResumeTokenData(application_id=app_id, current_step_key="contact")
    )

    assert await service.get_active_token(app_id) == token
    data = await service.validate_token(token)
    assert data is not None
    assert data.current_step_key == "contact"


@pytest.mark.asyncio
async def test_revoke_for_application_invalidates_tokens(service):
    app_id = uuid4()
    data = ResumeTokenData(application_id=app_id)

    token = await service.create_token(app_id, data)
    assert await service.validate_token(token) is not None

    revoked = await service.revoke_for_application(app_id)
    assert revoked == 1
    assert await service.validate_token(token) is None


@pytest.mark.asyncio
async def test_cleanup_expired_deletes_tokens(service):
    app_id = uuid4()
    token = await service.create_token(app_id, ResumeTokenData(application_id=app_id))
    service.expires_at[token] = datetime.now(timezone.utc) - timedelta(hours=1)

    deleted = await service.cleanup_expired()
    assert deleted == 1
    assert await service.validate_token(token) is None
