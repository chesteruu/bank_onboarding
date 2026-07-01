import asyncio
import json
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from fastapi.templating import Jinja2Templates

from onboarding.config import Settings, get_settings
from onboarding.domain.exceptions import DuplicateDraftError
from onboarding.i18n.provider import get_locale_provider
from onboarding.services.facade import OnboardingFacade
from onboarding.web.deps import get_onboarding_service
from onboarding.web.forms import parse_form
from onboarding.web.template_context import localize_progress, merge_i18n

router = APIRouter()
settings = get_settings()
templates = Jinja2Templates(directory=str(settings.templates_dir))


def _country_from_app(app) -> str | None:
    return app.country.value if app is not None else None


def _view_context(view: dict[str, Any], **extra) -> dict[str, Any]:
    app = view.get("application")
    country = _country_from_app(app)
    ctx = {**view, **extra}
    progress = ctx.get("progress")
    if progress is not None:
        tr = get_locale_provider().for_country(country)
        ctx["progress"] = localize_progress(progress, tr)
    step = ctx.get("step")
    if step is not None:
        tr = get_locale_provider().for_country(country)
        ctx["step_title"] = tr.step_title(step.key, step.title)
        if ctx.get("is_first_step"):
            ctx["back_label"] = tr.t("step.back_to_country")
        else:
            prev_key = ctx.get("previous_step_key")
            if prev_key:
                prev_title = tr.step_title(prev_key, prev_key.replace("_", " ").title())
                ctx["back_label"] = tr.t("step.back_to_previous", step=prev_title)
    return merge_i18n(ctx, country)


def _set_device_cookie(response: RedirectResponse, device_id: str, settings: Settings) -> None:
    max_age = settings.device_cookie_max_age_days * 24 * 60 * 60
    response.set_cookie(
        settings.device_cookie_name,
        device_id,
        max_age=max_age,
        httponly=True,
        samesite="lax",
    )


@router.get("/", response_class=HTMLResponse, response_model=None)
async def landing(
    request: Request,
    service: Annotated[OnboardingFacade, Depends(get_onboarding_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    device_id = request.cookies.get(settings.device_cookie_name)
    resume_error = request.query_params.get("resume")
    fresh = request.query_params.get("fresh")
    if device_id and not fresh:
        app = await service.resume_by_device(device_id)
        if app is not None and app.current_step_key is not None:
            resume_link = await service.get_resume_link(app.id, str(request.base_url).rstrip("/"))
            country_tr = get_locale_provider().for_country(app.country.value)
            return templates.TemplateResponse(
                request,
                "resume_prompt.html",
                merge_i18n(
                    {
                        "application": app,
                        "resume_link": resume_link,
                        "country_label": country_tr.t(
                            "market.display_name", default=app.country.value
                        ),
                    },
                    app.country.value,
                ),
            )
    locale = get_locale_provider()
    return templates.TemplateResponse(
        request,
        "landing.html",
        merge_i18n(
            {
                "account_types": locale.account_type_choices(),
                "resume_error": resume_error,
            },
            None,
        ),
    )


@router.post("/onboarding/resume")
async def resume_onboarding(
    request: Request,
    application_id: Annotated[UUID, Form()],
    service: Annotated[OnboardingFacade, Depends(get_onboarding_service)],
) -> RedirectResponse:
    app = await service.get_application(application_id)
    if app is None or app.current_step_key is None:
        return RedirectResponse(url="/", status_code=303)
    return RedirectResponse(
        url=f"/onboarding/{app.id}/step/{app.current_step_key}",
        status_code=303,
    )


@router.get("/onboarding/resume/{token}")
async def resume_by_token_link(
    token: str,
    service: Annotated[OnboardingFacade, Depends(get_onboarding_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RedirectResponse:
    app = await service.resume_by_token(token)
    if app is None:
        return RedirectResponse(url="/?resume=invalid", status_code=303)
    response = RedirectResponse(
        url=f"/onboarding/{app.id}/step/{app.current_step_key}",
        status_code=303,
    )
    if app.device_id:
        _set_device_cookie(response, app.device_id, settings)
    return response


@router.post("/onboarding/start-over")
async def start_over(
    request: Request,
    service: Annotated[OnboardingFacade, Depends(get_onboarding_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RedirectResponse:
    old_device_id = request.cookies.get(settings.device_cookie_name)
    if old_device_id:
        await service.start_over(old_device_id)
    new_device_id = uuid4().hex
    response = RedirectResponse(url="/", status_code=303)
    _set_device_cookie(response, new_device_id, settings)
    return response


@router.post("/onboarding/select-type", response_class=HTMLResponse)
async def select_type(
    request: Request,
    account_type: Annotated[str, Form()],
    service: Annotated[OnboardingFacade, Depends(get_onboarding_service)],
) -> HTMLResponse:
    locale = get_locale_provider()
    return templates.TemplateResponse(
        request,
        "select_country.html",
        merge_i18n(
            {
                "account_type": account_type,
                "country_choices": locale.country_choices(account_type),
                "account_type_label": locale.for_country(None).t(f"account_types.{account_type}"),
            },
            None,
        ),
    )


@router.get("/onboarding/select-country", response_class=HTMLResponse)
async def select_country_get(
    request: Request,
    account_type: Annotated[str, Query()],
    service: Annotated[OnboardingFacade, Depends(get_onboarding_service)],
) -> HTMLResponse:
    locale = get_locale_provider()
    return templates.TemplateResponse(
        request,
        "select_country.html",
        merge_i18n(
            {
                "account_type": account_type,
                "country_choices": locale.country_choices(account_type),
                "account_type_label": locale.for_country(None).t(f"account_types.{account_type}"),
            },
            None,
        ),
    )


@router.post("/onboarding/start")
async def start_onboarding(
    request: Request,
    country: Annotated[str, Form()],
    account_type: Annotated[str, Form()],
    service: Annotated[OnboardingFacade, Depends(get_onboarding_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RedirectResponse:
    device_id = request.cookies.get(settings.device_cookie_name) or uuid4().hex
    app = await service.start_application(country, account_type, device_id=device_id)
    response = RedirectResponse(
        url=f"/onboarding/{app.id}/step/{app.current_step_key}",
        status_code=303,
    )
    _set_device_cookie(response, device_id, settings)
    return response


@router.get("/onboarding/{application_id}/step/{step_key}", response_class=HTMLResponse)
async def show_step(
    request: Request,
    application_id: UUID,
    step_key: str,
    service: Annotated[OnboardingFacade, Depends(get_onboarding_service)],
) -> HTMLResponse:
    base_url = str(request.base_url).rstrip("/")
    view = await service.get_step_view(application_id, step_key, base_url=base_url)
    app = view["application"]
    step = view["step"]

    if app.status.value not in ("draft",) and not step.is_review:
        return templates.TemplateResponse(
            request,
            "result.html",
            merge_i18n(
                {"application": app, "decision": app.final_decision},
                app.country.value,
            ),
        )

    template = "review.html" if step.is_review else "step.html"
    review_data = None
    resume_link = view.get("resume_link")
    if step.is_review:
        review_data = await service.get_review_data(application_id)
        if resume_link is None and app.status.value == "draft":
            resume_link = await service.get_resume_link(application_id, base_url)

    return templates.TemplateResponse(
        request,
        template,
        _view_context(
            view,
            review_data=review_data,
            resume_link=resume_link,
            errors=[],
        ),
    )


@router.post("/onboarding/{application_id}/step/{step_key}/back")
async def go_back_step(
    application_id: UUID,
    step_key: str,
    service: Annotated[OnboardingFacade, Depends(get_onboarding_service)],
) -> RedirectResponse:
    try:
        redirect_url = await service.go_back(application_id, step_key)
    except ValueError:
        redirect_url = "/"
    return RedirectResponse(url=redirect_url, status_code=303)


@router.get("/onboarding/{application_id}/status")
async def application_status(
    application_id: UUID,
    service: Annotated[OnboardingFacade, Depends(get_onboarding_service)],
) -> JSONResponse:
    status = await service.get_status(application_id)
    return JSONResponse(status)


@router.get("/onboarding/{application_id}/events")
async def application_events(
    application_id: UUID,
    service: Annotated[OnboardingFacade, Depends(get_onboarding_service)],
) -> StreamingResponse:
    async def generate():
        for _ in range(60):
            status = await service.get_status(application_id)
            yield f"data: {json.dumps(status)}\n\n"
            if status.get("ready"):
                break
            await asyncio.sleep(1)

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get(
    "/onboarding/{application_id}/processing",
    response_class=HTMLResponse,
    response_model=None,
)
async def processing_page(
    request: Request,
    application_id: UUID,
    service: Annotated[OnboardingFacade, Depends(get_onboarding_service)],
) -> Response:
    app = await service.get_application(application_id)
    if app is None:
        return RedirectResponse(url="/", status_code=303)
    status = await service.get_status(application_id)
    tr = get_locale_provider().for_country(app.country.value)
    return templates.TemplateResponse(
        request,
        "processing.html",
        merge_i18n(
            {
                "application": app,
                "status": status,
                "js_step_of": tr.t(
                    "progress.step_of",
                    current="{current}",
                    total="{total}",
                    title="{title}",
                ),
                "js_segment": tr.t(
                    "progress.segment",
                    orchestrator="{orchestrator}",
                    step="{step}",
                    percent="{percent}",
                ),
            },
            app.country.value,
        ),
    )


@router.post(
    "/onboarding/{application_id}/step/{step_key}", response_class=HTMLResponse, response_model=None
)
async def submit_step(
    request: Request,
    application_id: UUID,
    step_key: str,
    service: Annotated[OnboardingFacade, Depends(get_onboarding_service)],
) -> Response:
    form = await request.form()
    data: dict[str, Any] = {k: v for k, v in form.items() if k not in ("confirm", "consent_terms")}
    if "confirm" in form:
        data["confirm"] = form.get("confirm") == "on" or form.get("confirm") == "true"
    if "consent_terms" in form:
        data["consent_terms"] = (
            form.get("consent_terms") == "on" or form.get("consent_terms") == "true"
        )

    base_url = str(request.base_url).rstrip("/")
    view = await service.get_step_view(application_id, step_key, base_url=base_url)
    step = view["step"]

    if step.is_review:
        answers, errors = parse_form(step.form_schema, data)
        if errors:
            review_data = await service.get_review_data(application_id)
            return templates.TemplateResponse(
                request,
                "review.html",
                _view_context(view, review_data=review_data, errors=errors),
                status_code=422,
            )
        decision = await service.finalize_application(application_id)
        app = await service.get_application(application_id)
        return templates.TemplateResponse(
            request,
            "result.html",
            merge_i18n(
                {"application": app, "decision": decision},
                app.country.value if app else None,
            ),
        )

    answers, errors = parse_form(step.form_schema, data) if step.form_schema else (data, [])
    if errors or (step.form_schema and answers is None):
        return templates.TemplateResponse(
            request,
            "step.html",
            _view_context(view, errors=errors or ["Invalid form data"], existing_answers=data),
            status_code=422,
        )

    try:
        app, integration_results = await service.submit_step(
            application_id, step_key, answers or {}
        )
    except DuplicateDraftError as exc:
        existing = await service.get_application(exc.existing_application_id)
        return templates.TemplateResponse(
            request,
            "duplicate_prompt.html",
            merge_i18n(
                {
                    "application": view["application"],
                    "existing_application": existing,
                    "step_key": step_key,
                    "answers": data,
                },
                view["application"].country.value,
            ),
        )

    if service.event_driven:
        status = await service.get_status(application_id)
        if not status.get("ready"):
            return RedirectResponse(
                url=f"/onboarding/{application_id}/processing",
                status_code=303,
            )

    next_key = app.current_step_key
    if next_key:
        return RedirectResponse(
            url=f"/onboarding/{application_id}/step/{next_key}",
            status_code=303,
        )

    return templates.TemplateResponse(
        request,
        "step.html",
        _view_context(
            view,
            integration_results=integration_results,
            submitted=True,
        ),
    )


@router.post("/onboarding/{application_id}/step/{step_key}/continue")
async def submit_step_continue(
    request: Request,
    application_id: UUID,
    step_key: str,
    service: Annotated[OnboardingFacade, Depends(get_onboarding_service)],
) -> RedirectResponse:
    form = await request.form()
    data: dict[str, Any] = {k: v for k, v in form.items() if k not in ("confirm", "consent_terms")}
    if "confirm" in form:
        data["confirm"] = form.get("confirm") == "on" or form.get("confirm") == "true"
    if "consent_terms" in form:
        data["consent_terms"] = (
            form.get("consent_terms") == "on" or form.get("consent_terms") == "true"
        )

    view = await service.get_step_view(
        application_id, step_key, base_url=str(request.base_url).rstrip("/")
    )
    step = view["step"]
    answers, errors = parse_form(step.form_schema, data) if step.form_schema else (data, [])
    if errors or (step.form_schema and answers is None):
        return RedirectResponse(
            url=f"/onboarding/{application_id}/step/{step_key}",
            status_code=303,
        )

    app, _ = await service.submit_step(
        application_id, step_key, answers or {}, allow_duplicate=True
    )
    return RedirectResponse(
        url=f"/onboarding/{application_id}/step/{app.current_step_key}",
        status_code=303,
    )
