from onboarding.i18n.provider import get_locale_provider


def test_available_flows_from_markets_config():
    provider = get_locale_provider()
    flows = provider.available_flows()
    assert flows["private"] == ["ES", "PL", "SE"]
    assert flows["business"] == ["ES", "PL", "SE"]


def test_swedish_translations():
    tr = get_locale_provider().for_country("SE")
    assert tr.locale == "sv"
    assert tr.t("landing.title") == "Öppna konto"
    assert tr.t("common.continue") == "Fortsätt"
    assert tr.step_title("identity", "Verify identity") == "Verifiera identitet"


def test_spanish_translations():
    tr = get_locale_provider().for_country("ES")
    assert tr.locale == "es"
    assert tr.t("market.display_name") == "España"


def test_country_choices_use_localized_names():
    provider = get_locale_provider()
    choices = dict(provider.country_choices("private"))
    assert choices["SE"] == "Sverige"
    assert choices["ES"] == "España"
    assert choices["PL"] == "Polska"


def test_default_bundle_for_landing():
    tr = get_locale_provider().for_country(None)
    assert tr.locale == "en"
    assert tr.t("landing.title") == "Open an account"


def test_missing_key_falls_back_to_default():
    tr = get_locale_provider().for_country("SE")
    assert tr.t("nonexistent.key", default="Fallback") == "Fallback"
