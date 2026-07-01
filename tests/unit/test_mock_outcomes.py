import pytest

from onboarding.domain.enums import CheckOutcome
from onboarding.integrations.mocks.outcomes import (
    bank_outcome,
    credit_outcome,
    identity_outcome,
    registry_outcome,
    sanctions_outcome,
)


@pytest.mark.parametrize(
    "national_id,expected",
    [
        ("199001011234", CheckOutcome.VERIFIED),
        ("199001010000", CheckOutcome.MANUAL_REVIEW),
        ("199001019999", CheckOutcome.DOCUMENT_MISMATCH),
        ("199001018888", CheckOutcome.EXPIRED_ID),
    ],
)
def test_identity_outcome(national_id, expected):
    assert identity_outcome(national_id) == expected


def test_sanctions_confirmed_hit():
    assert sanctions_outcome("John Sanction Smith") == CheckOutcome.CONFIRMED_HIT


def test_sanctions_possible_hit():
    assert sanctions_outcome("Jane Pep Candidate") == CheckOutcome.POSSIBLE_HIT


def test_credit_fail_on_expenses():
    assert credit_outcome("12349999", 3000, 3500) == CheckOutcome.FAIL


def test_registry_dissolved():
    assert registry_outcome("5560009999") == CheckOutcome.DISSOLVED


def test_bank_timeout():
    assert bank_outcome("PL61109010140000007777") == CheckOutcome.TIMEOUT
