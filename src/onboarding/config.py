from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


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


PROJECT_ROOT = _resolve_project_root()
FLOWS_DIR = PROJECT_ROOT / "flows"
TEMPLATES_DIR = PROJECT_ROOT / "templates"
PUBLIC_DIR = PROJECT_ROOT / "public"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/onboarding"
    debug: bool = False
    flows_dir: Path = FLOWS_DIR
    templates_dir: Path = TEMPLATES_DIR
    public_dir: Path = PUBLIC_DIR
    available_flows: dict[str, list[str]] = {
        "private": ["SE", "ES", "PL"],
        "business": ["SE", "ES", "PL"],
    }
    device_cookie_name: str = "onboarding_device_id"
    device_cookie_max_age_days: int = 90
    event_driven_enabled: bool = True

    @property
    def sync_database_url(self) -> str:
        return self.database_url.replace("+asyncpg", "")


@lru_cache
def get_settings() -> Settings:
    return Settings()
