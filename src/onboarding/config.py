from __future__ import annotations

import os
import ssl
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Neon/Vercel URLs often include these; asyncpg rejects them as connect() kwargs.
_ASYNCPG_STRIP_QUERY_KEYS = frozenset({"channel_binding", "sslmode"})


def _resolve_project_root() -> Path:
    """Locate repo root containing flows/, templates/, and public/."""
    candidates = [
        Path.cwd(),
        Path(__file__).resolve().parents[2],  # editable install: repo root
        Path(__file__).resolve().parents[1],  # flat layout fallback
    ]
    for root in candidates:
        if (root / "flows").is_dir() and (root / "templates").is_dir():
            return root
    return Path.cwd()


def normalize_asyncpg_url(url: str) -> str:
    """Convert standard Postgres URLs (Neon/Vercel) to SQLAlchemy asyncpg form."""
    if url.startswith("postgres://"):
        url = "postgresql+asyncpg://" + url.removeprefix("postgres://")
    elif url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url.removeprefix("postgresql://")

    parsed = urlparse(url)
    if not parsed.query:
        return url
    filtered = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key not in _ASYNCPG_STRIP_QUERY_KEYS
    ]
    return urlunparse(parsed._replace(query=urlencode(filtered)))


def ensure_ssl_query_param(url: str) -> str:
    """Neon requires TLS; Alembic uses the sync psycopg driver."""
    if any(host in url for host in ("localhost", "127.0.0.1", "@postgres:")):
        return url
    if "sslmode=" in url:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}sslmode=require"


def migration_database_url() -> str:
    """Direct (non-pooled) URL for Alembic migrations — required by Neon."""
    for key in (
        "DATABASE_URL_UNPOOLED",
        "POSTGRES_URL_NON_POOLING",
        "POSTGRES_URL_NO_POOLING",
    ):
        value = os.environ.get(key)
        if value:
            url = normalize_asyncpg_url(value).replace("+asyncpg", "")
            return ensure_ssl_query_param(url)
    settings = get_settings()
    return ensure_ssl_query_param(settings.sync_database_url)


PROJECT_ROOT = _resolve_project_root()
FLOWS_DIR = PROJECT_ROOT / "flows"
TEMPLATES_DIR = PROJECT_ROOT / "templates"
PUBLIC_DIR = PROJECT_ROOT / "public"
I18N_DIR = PROJECT_ROOT / "i18n"

_LOCAL_DEFAULT_DB = "postgresql+asyncpg://postgres:postgres@localhost:5432/onboarding"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = _LOCAL_DEFAULT_DB
    debug: bool = False
    flows_dir: Path = FLOWS_DIR
    templates_dir: Path = TEMPLATES_DIR
    public_dir: Path = PUBLIC_DIR
    i18n_dir: Path = I18N_DIR
    device_cookie_name: str = "onboarding_device_id"
    device_cookie_max_age_days: int = 90
    event_driven_enabled: bool = True
    integration_timeout_seconds: float = 5.0
    integration_max_attempts: int = 3
    integration_retry_backoff_seconds: float = 0.25
    integration_retry_backoff_multiplier: float = 2.0
    integration_max_backoff_seconds: float = 2.0

    @model_validator(mode="before")
    @classmethod
    def resolve_database_url_from_neon(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        current = data.get("database_url")
        if current and current != _LOCAL_DEFAULT_DB:
            return data
        for env_key in ("DATABASE_URL", "POSTGRES_URL", "POSTGRES_PRISMA_URL"):
            env_val = os.environ.get(env_key)
            if env_val:
                data["database_url"] = env_val
                break
        return data

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, url: str) -> str:
        return normalize_asyncpg_url(url)

    @property
    def available_flows(self) -> dict[str, list[str]]:
        from onboarding.i18n.provider import get_locale_provider

        return get_locale_provider().available_flows()

    @property
    def sync_database_url(self) -> str:
        return self.database_url.replace("+asyncpg", "")

    @property
    def database_ssl_required(self) -> bool:
        host = self.database_url.split("@")[-1].split("/")[0].split(":")[0].lower()
        return host not in {"localhost", "127.0.0.1", "postgres"}


def database_connect_args(settings: Settings) -> dict[str, Any]:
    if not settings.database_ssl_required:
        return {}
    return {"ssl": ssl.create_default_context()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
