import hashlib
import json
from typing import Any


def hash_payload(data: dict[str, Any]) -> str:
    normalized = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(normalized.encode()).hexdigest()


def hash_identifier(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def redact_pii(data: dict[str, Any]) -> dict[str, Any]:
    """Remove or mask PII fields for audit metadata."""
    sensitive_keys = {
        "national_id",
        "pesel",
        "dni",
        "nie",
        "personal_number",
        "full_name",
        "first_name",
        "last_name",
        "email",
        "phone",
        "monthly_income",
        "monthly_expenses",
        "iban",
        "account_holder",
        "company_name",
    }
    result: dict[str, Any] = {}
    for key, value in data.items():
        if key in sensitive_keys and value:
            result[key] = hash_identifier(str(value))
        elif isinstance(value, dict):
            result[key] = redact_pii(value)
        else:
            result[key] = value
    return result
