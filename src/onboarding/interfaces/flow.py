from typing import Any, Protocol
from uuid import UUID

from onboarding.domain.enums import AccountType, Country
from onboarding.domain.models import Application, FlowDefinition, ProgressInfo


class IFlowDefinitionProvider(Protocol):
    def get_flow(self, country: Country, account_type: AccountType) -> FlowDefinition: ...

    def list_flows(self) -> list[FlowDefinition]: ...


class IFlowEngine(Protocol):
    def get_flow(self, application: Application) -> FlowDefinition: ...

    def get_current_step(self, application: Application) -> str: ...

    def validate_transition(
        self, application: Application, from_step: str, to_step: str
    ) -> bool: ...

    def get_progress(self, application: Application) -> ProgressInfo: ...

    def get_step_context(
        self, application: Application, step_key: str
    ) -> dict[str, Any]: ...
