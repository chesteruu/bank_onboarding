from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from onboarding.config import PROJECT_ROOT


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _get_nested(data: dict[str, Any], parts: list[str]) -> Any:
    current: Any = data
    for part in parts:
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


class Translator:
    """Dot-key translator backed by a merged YAML bundle."""

    def __init__(self, locale: str, bundle: dict[str, Any]) -> None:
        self.locale = locale
        self._bundle = bundle

    def t(self, key: str, default: str | None = None, **kwargs: Any) -> str:
        value = _get_nested(self._bundle, key.split("."))
        if value is None:
            text = default if default is not None else key
        else:
            text = str(value)
        if kwargs:
            try:
                return text.format(**kwargs)
            except KeyError:
                return text
        return text

    def step_title(self, step_key: str, fallback: str) -> str:
        translated = _get_nested(self._bundle, ["steps", step_key])
        return str(translated) if translated is not None else fallback


class LocaleProvider:
    """Loads market config and per-country translation bundles."""

    def __init__(self, i18n_dir: Path) -> None:
        self._i18n_dir = i18n_dir
        self._bundle_cache: dict[str, dict[str, Any]] = {}
        self._markets_config = self._load_yaml(i18n_dir / "markets.yaml")
        self._default_bundle_name = self._markets_config.get("default", {}).get("bundle", "en")
        self._default_locale = self._markets_config.get("default", {}).get("locale", "en")
        self._default_bundle = self._load_bundle(self._default_bundle_name)
        self._bundle_cache[self._default_bundle_name] = self._default_bundle

    @staticmethod
    def _load_yaml(path: Path) -> dict[str, Any]:
        with path.open(encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}

    def _load_bundle(self, bundle_name: str) -> dict[str, Any]:
        if bundle_name in self._bundle_cache:
            return self._bundle_cache[bundle_name]
        path = self._i18n_dir / "bundles" / f"{bundle_name}.yaml"
        bundle = self._load_yaml(path) if path.is_file() else {}
        self._bundle_cache[bundle_name] = bundle
        return bundle

    def _merged_bundle(self, bundle_name: str) -> dict[str, Any]:
        override = self._load_bundle(bundle_name)
        if bundle_name == self._default_bundle_name:
            return override
        return _deep_merge(self._default_bundle, override)

    def available_flows(self) -> dict[str, list[str]]:
        flows: dict[str, list[str]] = {"private": [], "business": []}
        for code, market in (self._markets_config.get("markets") or {}).items():
            enabled = market.get("enabled") or {}
            for account_type, is_enabled in enabled.items():
                if is_enabled and code not in flows.setdefault(account_type, []):
                    flows[account_type].append(code)
        for account_type in flows:
            flows[account_type].sort()
        return flows

    def is_market_enabled(self, country: str, account_type: str) -> bool:
        market = (self._markets_config.get("markets") or {}).get(country)
        if market is None:
            return False
        return bool((market.get("enabled") or {}).get(account_type))

    def for_country(self, country: str | None) -> Translator:
        if country is None:
            return Translator(self._default_locale, self._default_bundle)
        market = (self._markets_config.get("markets") or {}).get(country)
        if market is None:
            return Translator(self._default_locale, self._default_bundle)
        locale = market.get("locale", self._default_locale)
        bundle_name = market.get("bundle", country)
        return Translator(locale, self._merged_bundle(bundle_name))

    def account_type_choices(self, translator: Translator | None = None) -> list[tuple[str, str]]:
        tr = translator or self.for_country(None)
        return [
            ("private", tr.t("account_types.private")),
            ("business", tr.t("account_types.business")),
        ]

    def country_choices(self, account_type: str) -> list[tuple[str, str]]:
        choices: list[tuple[str, str]] = []
        for code in self.available_flows().get(account_type, []):
            tr = self.for_country(code)
            name = tr.t("market.display_name", default=code)
            choices.append((code, name))
        return choices


@lru_cache
def get_locale_provider() -> LocaleProvider:
    i18n_dir = PROJECT_ROOT / "i18n"
    return LocaleProvider(i18n_dir)
