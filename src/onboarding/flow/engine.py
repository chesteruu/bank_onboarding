from typing import Any

from onboarding.domain.models import Application, FlowDefinition, ProgressInfo
from onboarding.interfaces.flow import IFlowDefinitionProvider


class FlowEngine:
    def __init__(self, provider: IFlowDefinitionProvider) -> None:
        self._provider = provider

    def get_flow(self, application: Application) -> FlowDefinition:
        return self._provider.get_flow(application.country, application.account_type)

    def get_flow_for(self, country: str, account_type: str) -> FlowDefinition:
        from onboarding.domain.enums import AccountType, Country

        return self._provider.get_flow(Country(country), AccountType(account_type))

    def get_current_step(self, application: Application) -> str:
        flow = self.get_flow(application)
        if application.current_step_key:
            return application.current_step_key
        return flow.steps[0].key

    def validate_transition(
        self, application: Application, from_step: str, to_step: str
    ) -> bool:
        flow = self.get_flow(application)
        expected = flow.next_step_key(from_step)
        if expected is None:
            return False
        return expected == to_step

    def get_progress(self, application: Application) -> ProgressInfo:
        flow = self.get_flow(application)
        current_key = self.get_current_step(application)
        keys = flow.step_keys()
        try:
            idx = keys.index(current_key)
        except ValueError:
            idx = 0
        total = len(keys)
        percent = int(((idx + 1) / total) * 100) if total else 0
        step = flow.get_step(current_key)
        return ProgressInfo(
            current_step=idx + 1,
            total_steps=total,
            percent=percent,
            current_step_key=current_key,
            current_step_title=step.title if step else current_key,
        )

    def get_step_context(
        self, application: Application, step_key: str
    ) -> dict[str, Any]:
        flow = self.get_flow(application)
        step = flow.get_step(step_key)
        if step is None:
            raise ValueError(f"Unknown step {step_key}")
        return {
            "step": step,
            "flow_id": flow.flow_id,
            "country": application.country.value,
            "account_type": application.account_type.value,
        }
