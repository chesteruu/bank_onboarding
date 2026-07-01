import pytest

from onboarding.config import FLOWS_DIR
from onboarding.domain.enums import AccountType, Country
from onboarding.flow.provider import YamlFlowDefinitionProvider


@pytest.mark.parametrize(
    "country,account_type,expected_steps",
    [
        (
            Country.SE,
            AccountType.PRIVATE,
            [
                "identity",
                "contact",
                "consent",
                "financial",
                "credit_decision",
                "review",
                "decision",
            ],
        ),
        (
            Country.SE,
            AccountType.BUSINESS,
            [
                "company",
                "signatory",
                "ubo",
                "financial",
                "kyb_decision",
                "credit_decision",
                "review",
                "decision",
            ],
        ),
        (
            Country.ES,
            AccountType.PRIVATE,
            [
                "identity",
                "contact",
                "consent",
                "financial",
                "credit_decision",
                "review",
                "decision",
            ],
        ),
        (
            Country.PL,
            AccountType.PRIVATE,
            [
                "identity",
                "contact",
                "consent",
                "financial",
                "credit_decision",
                "review",
                "decision",
            ],
        ),
    ],
)
def test_flow_definitions_load(country, account_type, expected_steps):
    provider = YamlFlowDefinitionProvider(FLOWS_DIR)
    flow = provider.get_flow(country, account_type)
    assert [s.key for s in flow.steps] == expected_steps
    assert all(s.orchestrator for s in flow.steps)
    assert all(s.component_flow for s in flow.steps if not s.is_review)
