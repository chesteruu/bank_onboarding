from onboarding.web.forms import parse_form


def test_parse_identity_se():
    answers, errors = parse_form(
        "IdentityStepSE",
        {"national_id": "199001011234", "full_name": "Anna Test", "date_of_birth": "1990-01-01"},
    )
    assert not errors
    assert answers["national_id"] == "199001011234"


def test_parse_review_requires_confirm():
    answers, errors = parse_form("ReviewStep", {"confirm": False})
    assert errors
