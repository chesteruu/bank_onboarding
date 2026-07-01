from datetime import datetime, timezone
from uuid import uuid4

import pytest

from onboarding.decision.engine import RulesDecisionEngine
from onboarding.domain.enums import (
    AccountType,
    ApplicationStatus,
    CheckOutcome,
    Country,
    DecisionOutcome,
    IntegrationCheckType,
)
from onboarding.domain.models import Application, IntegrationResult
from onboarding.config import PROJECT_ROOT


@pytest.fixture
def decision_engine() -> RulesDecisionEngine:
    rules_dir = PROJECT_ROOT / "src" / "onboarding" / "decision" / "rules"
    return RulesDecisionEngine(rules_dir)


def _app() -> Application:
    now = datetime.now(timezone.utc)
    return Application(
        id=uuid4(),
        request_id="req_dec",
        country=Country.SE,
        account_type=AccountType.PRIVATE,
        status=ApplicationStatus.DRAFT,
        current_step_key="review",
        created_at=now,
        updated_at=now,
    )


def _result(outcome: CheckOutcome, check_type: IntegrationCheckType = IntegrationCheckType.IDENTITY):
    return IntegrationResult(
        application_id=uuid4(),
        check_type=check_type,
        provider="mock",
        request_payload_hash="x",
        response={"score": 750},
        outcome=outcome,
        ran_at=datetime.now(timezone.utc),
    )


def test_decision_approved(decision_engine):
    results = [
        _result(CheckOutcome.VERIFIED, IntegrationCheckType.IDENTITY),
        _result(CheckOutcome.NO_HIT, IntegrationCheckType.SANCTIONS),
        _result(CheckOutcome.PASS, IntegrationCheckType.CREDIT),
    ]
    decision = decision_engine.evaluate(_app(), results)
    assert decision.outcome == DecisionOutcome.APPROVED


def test_decision_rejected_sanctions(decision_engine):
    results = [_result(CheckOutcome.CONFIRMED_HIT, IntegrationCheckType.SANCTIONS)]
    decision = decision_engine.evaluate(_app(), results)
    assert decision.outcome == DecisionOutcome.REJECTED


def test_decision_manual_review(decision_engine):
    results = [_result(CheckOutcome.POSSIBLE_HIT, IntegrationCheckType.SANCTIONS)]
    decision = decision_engine.evaluate(_app(), results)
    assert decision.outcome == DecisionOutcome.MANUAL_REVIEW
