from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from onboarding.config import get_settings
from onboarding.events.bootstrap import build_orchestrator_registry
from onboarding.web.admin_routes import router as admin_router
from onboarding.web.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.orchestrator_registry = build_orchestrator_registry(settings.flows_dir)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Ikano Onboarding", lifespan=lifespan)
    app.include_router(router)
    app.include_router(admin_router)

    public_dir = Path(settings.public_dir)
    if public_dir.exists():
        app.mount("/static", StaticFiles(directory=str(public_dir)), name="static")

    return app


app = create_app()
