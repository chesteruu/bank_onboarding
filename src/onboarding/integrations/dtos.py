from __future__ import annotations

from pydantic import BaseModel, Field

from onboarding.domain.enums import CheckOutcome, Country


class IdentityCheckRequest(BaseModel):
    country: Country
    national_id: str
    full_name: str
    date_of_birth: str | None = None


class IdentityCheckResponse(BaseModel):
    outcome: CheckOutcome
    provider: str
    reference: str
    details: dict = Field(default_factory=dict)


class AddressCheckRequest(BaseModel):
    country: Country
    address_line: str
    city: str
    postal_code: str


class AddressCheckResponse(BaseModel):
    outcome: CheckOutcome
    provider: str
    normalized_address: str | None = None
    details: dict = Field(default_factory=dict)


class RegistryCheckRequest(BaseModel):
    country: Country
    company_number: str
    company_name: str


class RegistryCheckResponse(BaseModel):
    outcome: CheckOutcome
    provider: str
    company_status: str
    details: dict = Field(default_factory=dict)


class KybCheckRequest(BaseModel):
    country: Country
    company_number: str
    ubo_count: int = 0


class KybCheckResponse(BaseModel):
    outcome: CheckOutcome
    provider: str
    risk_level: str
    details: dict = Field(default_factory=dict)


class SanctionsCheckRequest(BaseModel):
    country: Country
    name: str
    entity_type: str = "individual"


class SanctionsCheckResponse(BaseModel):
    outcome: CheckOutcome
    provider: str
    match_score: float = 0.0
    details: dict = Field(default_factory=dict)


class CreditCheckRequest(BaseModel):
    country: Country
    national_id: str | None = None
    company_number: str | None = None
    monthly_income: float | None = None
    monthly_expenses: float | None = None


class CreditCheckResponse(BaseModel):
    outcome: CheckOutcome
    provider: str
    score: int
    debt_flag: bool = False
    disposable_income: float | None = None
    details: dict = Field(default_factory=dict)


class BankAccountCheckRequest(BaseModel):
    country: Country
    iban: str
    account_holder: str


class BankAccountCheckResponse(BaseModel):
    outcome: CheckOutcome
    provider: str
    bank_name: str | None = None
    details: dict = Field(default_factory=dict)
