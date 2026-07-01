from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from onboarding.config import get_settings
from onboarding.services.facade import OnboardingFacade
from onboarding.web.deps import get_onboarding_service
from onboarding.web.template_context import merge_i18n

router = APIRouter(prefix="/admin")
settings = get_settings()
templates = Jinja2Templates(directory=str(settings.templates_dir))


def _admin_context(context: dict | None = None) -> dict:
    """Admin UI uses English default strings from base.html."""
    return merge_i18n(context or {}, None)


@router.get("/", response_class=HTMLResponse)
async def admin_index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "admin/index.html",
        _admin_context(),
    )


@router.get("/applications", response_class=HTMLResponse)
async def admin_applications(
    request: Request,
    service: Annotated[OnboardingFacade, Depends(get_onboarding_service)],
) -> HTMLResponse:
    applications = await service.list_applications()
    return templates.TemplateResponse(
        request,
        "admin/applications.html",
        _admin_context({"applications": applications}),
    )


@router.get("/applications/{application_id}", response_class=HTMLResponse)
async def admin_application_detail(
    request: Request,
    application_id: UUID,
    service: Annotated[OnboardingFacade, Depends(get_onboarding_service)],
) -> HTMLResponse:
    detail = await service.get_admin_application_detail(application_id)
    return templates.TemplateResponse(
        request,
        "admin/application_detail.html",
        _admin_context(detail),
    )


@router.get("/traces", response_class=HTMLResponse)
async def admin_traces(
    request: Request,
    service: Annotated[OnboardingFacade, Depends(get_onboarding_service)],
) -> HTMLResponse:
    events = await service.list_trace_events(limit=200)
    return templates.TemplateResponse(
        request,
        "admin/traces.html",
        _admin_context({"events": events}),
    )


@router.get("/decisions", response_class=HTMLResponse)
async def admin_decisions(
    request: Request,
    service: Annotated[OnboardingFacade, Depends(get_onboarding_service)],
) -> HTMLResponse:
    applications = await service.list_applications()
    decisions = [a for a in applications if a.final_decision is not None]
    return templates.TemplateResponse(
        request,
        "admin/decisions.html",
        _admin_context({"applications": decisions}),
    )
