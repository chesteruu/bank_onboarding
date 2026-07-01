from __future__ import annotations

from typing import Any

from onboarding.domain.events.segment import AggregateProgress
from onboarding.i18n.provider import LocaleProvider, Translator, get_locale_provider


def _status_label(translator: Translator, status: str) -> str:
    return translator.t(f"decisions.{status}", default=status.replace("_", " ").title())


def localize_progress(progress: AggregateProgress, translator: Translator) -> AggregateProgress:
    title = translator.step_title(
        progress.current_step_key or "",
        progress.current_step_title,
    )
    active = progress.active_segment
    if active is not None and active.internal_step_key:
        internal_title = translator.t(
            f"steps.{active.internal_step_key}",
            default=active.internal_step_title or active.internal_step_key.replace("_", " ").title(),
        )
        active = active.model_copy(update={"internal_step_title": internal_title})
    return progress.model_copy(
        update={
            "current_step_title": title,
            "active_segment": active,
        }
    )


def i18n_context(
    country: str | None = None,
    *,
    locale_provider: LocaleProvider | None = None,
) -> dict[str, Any]:
    provider = locale_provider or get_locale_provider()
    translator = provider.for_country(country)
    return {
        "t": translator.t,
        "lang": translator.locale,
        "translator": translator,
        "locale_provider": provider,
        "status_label": lambda s: _status_label(translator, s),
    }


def merge_i18n(
    context: dict[str, Any],
    country: str | None = None,
    *,
    locale_provider: LocaleProvider | None = None,
) -> dict[str, Any]:
    return {**context, **i18n_context(country, locale_provider=locale_provider)}
