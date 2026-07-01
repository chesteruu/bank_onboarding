from typing import Any, Protocol

from onboarding.domain.models import Application, FlowStep, IntegrationResult
from onboarding.integrations.dtos import (
    AddressCheckRequest,
    AddressCheckResponse,
    BankAccountCheckRequest,
    BankAccountCheckResponse,
    CreditCheckRequest,
    CreditCheckResponse,
    IdentityCheckRequest,
    IdentityCheckResponse,
    KybCheckRequest,
    KybCheckResponse,
    RegistryCheckRequest,
    RegistryCheckResponse,
    SanctionsCheckRequest,
    SanctionsCheckResponse,
)


class IIdentityClient(Protocol):
    async def verify(self, request: IdentityCheckRequest) -> IdentityCheckResponse: ...


class IRegistryClient(Protocol):
    async def lookup(self, request: RegistryCheckRequest) -> RegistryCheckResponse: ...


class IKybClient(Protocol):
    async def verify(self, request: KybCheckRequest) -> KybCheckResponse: ...


class ISanctionsClient(Protocol):
    async def screen(self, request: SanctionsCheckRequest) -> SanctionsCheckResponse: ...


class ICreditClient(Protocol):
    async def check(self, request: CreditCheckRequest) -> CreditCheckResponse: ...


class IBankAccountClient(Protocol):
    async def verify(self, request: BankAccountCheckRequest) -> BankAccountCheckResponse: ...


class IAddressClient(Protocol):
    async def verify(self, request: AddressCheckRequest) -> AddressCheckResponse: ...


class IIntegrationGateway(Protocol):
    async def run_checks(
        self,
        application: Application,
        step: FlowStep,
        answers: dict[str, Any],
        *,
        prior_results: list[IntegrationResult] | None = None,
    ) -> list[IntegrationResult]: ...
