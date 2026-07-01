from pathlib import Path

import yaml

from onboarding.domain.enums import CheckOutcome, DecisionOutcome, IntegrationCheckType
from onboarding.domain.models import Application, DecisionResult, IntegrationResult

REJECT_OUTCOMES = {
    CheckOutcome.CONFIRMED_HIT,
    CheckOutcome.DISSOLVED,
    CheckOutcome.DOCUMENT_MISMATCH,
    CheckOutcome.EXPIRED_ID,
    CheckOutcome.FAIL,
    CheckOutcome.NAME_MISMATCH,
}

REVIEW_OUTCOMES = {
    CheckOutcome.MANUAL_REVIEW,
    CheckOutcome.POSSIBLE_HIT,
    CheckOutcome.BORDERLINE,
    CheckOutcome.UNKNOWN_REPRESENTATIVE,
    CheckOutcome.MISSING_UBO,
    CheckOutcome.UNREACHABLE,
    CheckOutcome.TIMEOUT,
}


class RulesDecisionEngine:
    def __init__(self, rules_dir: Path | None = None) -> None:
        self._rules_dir = rules_dir
        self._flow_rules: dict[str, dict] = {}
        if rules_dir and rules_dir.exists():
            for path in rules_dir.glob("*.yaml"):
                with path.open(encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                self._flow_rules[data["flow_id"]] = data

    def evaluate(
        self,
        application: Application,
        integration_results: list[IntegrationResult],
        *,
        aggregated_answers: dict | None = None,
    ) -> DecisionResult:
        flow_id = f"{application.country.value.lower()}_{application.account_type.value}"
        rules = self._flow_rules.get(flow_id, {})
        critical_checks = set(rules.get("critical_checks", []))

        reasons: list[str] = []
        has_reject = False
        has_review = False

        for result in integration_results:
            check_name = result.check_type.value
            if critical_checks and check_name not in critical_checks:
                continue

            if result.outcome in REJECT_OUTCOMES:
                has_reject = True
                reasons.append(f"{check_name}: {result.outcome.value} → rejected")
            elif result.outcome in REVIEW_OUTCOMES:
                has_review = True
                reasons.append(f"{check_name}: {result.outcome.value} → manual review")

        if not integration_results and not reasons:
            reasons.append("No integration results available")

        if has_reject:
            return DecisionResult(outcome=DecisionOutcome.REJECTED, reasons=reasons)
        if has_review:
            return DecisionResult(outcome=DecisionOutcome.MANUAL_REVIEW, reasons=reasons)

        credit_results = [
            r for r in integration_results if r.check_type == IntegrationCheckType.CREDIT
        ]
        for cr in credit_results:
            score = cr.response.get("score", 0)
            min_score = rules.get("min_credit_score", 500)
            if score < min_score:
                return DecisionResult(
                    outcome=DecisionOutcome.MANUAL_REVIEW,
                    reasons=[f"credit score {score} below threshold {min_score}"],
                )

        return DecisionResult(
            outcome=DecisionOutcome.APPROVED,
            reasons=reasons or ["All critical checks passed"],
        )
