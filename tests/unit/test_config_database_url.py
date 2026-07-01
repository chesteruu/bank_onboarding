from onboarding.config import normalize_asyncpg_url


def test_normalize_asyncpg_url_strips_neon_channel_binding() -> None:
    raw = (
        "postgresql://user:pass@ep-test-pooler.us-east-2.aws.neon.tech/neondb"
        "?sslmode=require&channel_binding=require"
    )
    normalized = normalize_asyncpg_url(raw)
    assert normalized.startswith("postgresql+asyncpg://")
    assert "channel_binding" not in normalized
    assert "sslmode" not in normalized


def test_normalize_asyncpg_url_preserves_other_params() -> None:
    raw = "postgresql://user:pass@host/db?connect_timeout=10"
    normalized = normalize_asyncpg_url(raw)
    assert "connect_timeout=10" in normalized
