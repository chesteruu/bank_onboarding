from onboarding.audit.redaction import hash_identifier, redact_pii


def test_redact_pii_masks_sensitive_fields():
    data = {
        "national_id": "199001011234",
        "full_name": "Anna Andersson",
        "city": "Stockholm",
    }
    redacted = redact_pii(data)
    assert redacted["city"] == "Stockholm"
    assert redacted["national_id"] != "199001011234"
    assert redacted["full_name"] != "Anna Andersson"


def test_hash_identifier_is_deterministic():
    assert hash_identifier("test") == hash_identifier("test")
    assert hash_identifier("test") != hash_identifier("other")
