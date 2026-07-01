"""Deterministic outcome resolution based on magic identifier suffixes."""

from onboarding.domain.enums import CheckOutcome


def suffix(value: str, length: int = 4) -> str:
    cleaned = value.replace("-", "").replace(" ", "")
    return cleaned[-length:] if len(cleaned) >= length else cleaned


def identity_outcome(national_id: str) -> CheckOutcome:
    s = suffix(national_id)
    if s.endswith("9999"):
        return CheckOutcome.DOCUMENT_MISMATCH
    if s.endswith("8888"):
        return CheckOutcome.EXPIRED_ID
    if s.endswith("0000"):
        return CheckOutcome.MANUAL_REVIEW
    return CheckOutcome.VERIFIED


def registry_outcome(company_number: str) -> CheckOutcome:
    s = suffix(company_number)
    if s.endswith("9999"):
        return CheckOutcome.DISSOLVED
    if s.endswith("0000"):
        return CheckOutcome.UNKNOWN_REPRESENTATIVE
    if s.endswith("8888"):
        return CheckOutcome.MISSING_UBO
    return CheckOutcome.ACTIVE_COMPANY


def sanctions_outcome(name: str) -> CheckOutcome:
    lower = name.lower()
    if "sanction" in lower or suffix(name) == "6666":
        return CheckOutcome.CONFIRMED_HIT
    if "pep" in lower or suffix(name) == "0000":
        return CheckOutcome.POSSIBLE_HIT
    return CheckOutcome.NO_HIT


def credit_outcome(identifier: str, monthly_income: float | None, monthly_expenses: float | None) -> CheckOutcome:
    s = suffix(identifier)
    if s.endswith("9999"):
        return CheckOutcome.FAIL
    if s.endswith("0000"):
        return CheckOutcome.BORDERLINE
    if monthly_income is not None and monthly_expenses is not None:
        if monthly_expenses >= monthly_income:
            return CheckOutcome.FAIL
    return CheckOutcome.PASS


def credit_score(identifier: str) -> int:
    s = suffix(identifier)
    if s.endswith("9999"):
        return 420
    if s.endswith("0000"):
        return 620
    return 750


def bank_outcome(iban: str) -> CheckOutcome:
    s = suffix(iban.replace(" ", ""))
    if s.endswith("9999"):
        return CheckOutcome.NAME_MISMATCH
    if s.endswith("8888"):
        return CheckOutcome.UNREACHABLE
    if s.endswith("7777"):
        return CheckOutcome.TIMEOUT
    return CheckOutcome.IBAN_VERIFIED


def kyb_outcome(company_number: str, ubo_count: int) -> CheckOutcome:
    reg = registry_outcome(company_number)
    if reg != CheckOutcome.ACTIVE_COMPANY:
        return CheckOutcome.FAIL
    if ubo_count == 0:
        return CheckOutcome.MANUAL_REVIEW
    return CheckOutcome.PASS
