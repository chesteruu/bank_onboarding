from pydantic import BaseModel, EmailStr, Field, field_validator


class ContactStep(BaseModel):
    email: EmailStr
    phone: str = Field(min_length=6, max_length=20)
    address_line: str = Field(min_length=3)
    city: str = Field(min_length=2)
    postal_code: str = Field(min_length=3)


class IdentityStepSE(BaseModel):
    national_id: str = Field(min_length=10, max_length=13)
    full_name: str = Field(min_length=2)
    date_of_birth: str


class IdentityStepES(BaseModel):
    dni: str = Field(min_length=8, max_length=12)
    full_name: str = Field(min_length=2)
    date_of_birth: str

    def to_answers(self) -> dict:
        return {"national_id": self.dni, "full_name": self.full_name, "date_of_birth": self.date_of_birth}


class IdentityStepPL(BaseModel):
    pesel: str = Field(min_length=11, max_length=11)
    full_name: str = Field(min_length=2)
    date_of_birth: str

    def to_answers(self) -> dict:
        return {"national_id": self.pesel, "pesel": self.pesel, "full_name": self.full_name, "date_of_birth": self.date_of_birth}


class ContactStepES(ContactStep):
    province: str = Field(min_length=2)


class ContactStepPL(ContactStep):
    voivodeship: str = Field(min_length=2)


class FinancialStepSE(BaseModel):
    monthly_income: float = Field(gt=0)
    monthly_expenses: float = Field(ge=0)
    employment_status: str


class FinancialStepES(BaseModel):
    monthly_income: float = Field(gt=0)
    monthly_expenses: float = Field(ge=0)
    employment_status: str


class FinancialStepPL(BaseModel):
    monthly_income: float = Field(gt=0)
    monthly_expenses: float = Field(ge=0)
    employment_status: str


class CompanyStepSE(BaseModel):
    company_number: str = Field(min_length=6)
    company_name: str = Field(min_length=2)


class CompanyStepES(BaseModel):
    company_number: str = Field(min_length=6)
    company_name: str = Field(min_length=2)


class CompanyStepPL(BaseModel):
    company_number: str = Field(min_length=6)
    company_name: str = Field(min_length=2)


class SignatoryStepSE(BaseModel):
    signatory_name: str = Field(min_length=2)
    national_id: str = Field(min_length=10)
    role: str


class RepresentativeStepES(BaseModel):
    full_name: str = Field(min_length=2)
    dni: str = Field(min_length=8)
    role: str

    def to_answers(self) -> dict:
        return {"signatory_name": self.full_name, "national_id": self.dni, "full_name": self.full_name, "role": self.role}


class BoardStepPL(BaseModel):
    signatory_name: str = Field(min_length=2)
    board_resolution: str = Field(min_length=3)


class UboStep(BaseModel):
    ubo_count: int = Field(ge=0, le=10)
    ubo_names: str = ""


class FinancialBusinessStepSE(BaseModel):
    annual_revenue: float = Field(gt=0)
    monthly_expenses: float = Field(ge=0)
    employee_count: int = Field(ge=0)


class FinancialBusinessStepES(BaseModel):
    annual_revenue: float = Field(gt=0)
    monthly_expenses: float = Field(ge=0)
    iban: str = Field(min_length=15)
    account_holder: str = Field(min_length=2)


class FinancialBusinessStepPL(BaseModel):
    annual_revenue: float = Field(gt=0)
    monthly_expenses: float = Field(ge=0)
    iban: str = Field(min_length=15)
    account_holder: str = Field(min_length=2)


class ReviewStep(BaseModel):
    confirm: bool

    @field_validator("confirm")
    @classmethod
    def must_confirm(cls, v: bool) -> bool:
        if not v:
            raise ValueError("You must confirm before submitting")
        return v


class ConsentStep(BaseModel):
    consent_terms: bool
    pep_self_declaration: str = Field(min_length=3)
    tax_residency: str = Field(min_length=2)

    @field_validator("consent_terms")
    @classmethod
    def must_consent(cls, v: bool) -> bool:
        if not v:
            raise ValueError("You must accept the terms and privacy notice")
        return v


FORM_SCHEMAS: dict[str, type[BaseModel]] = {
    "IdentityStepSE": IdentityStepSE,
    "IdentityStepES": IdentityStepES,
    "IdentityStepPL": IdentityStepPL,
    "ContactStep": ContactStep,
    "ContactStepES": ContactStepES,
    "ContactStepPL": ContactStepPL,
    "FinancialStepSE": FinancialStepSE,
    "FinancialStepES": FinancialStepES,
    "FinancialStepPL": FinancialStepPL,
    "CompanyStepSE": CompanyStepSE,
    "CompanyStepES": CompanyStepES,
    "CompanyStepPL": CompanyStepPL,
    "SignatoryStepSE": SignatoryStepSE,
    "RepresentativeStepES": RepresentativeStepES,
    "BoardStepPL": BoardStepPL,
    "UboStep": UboStep,
    "FinancialBusinessStepSE": FinancialBusinessStepSE,
    "FinancialBusinessStepES": FinancialBusinessStepES,
    "FinancialBusinessStepPL": FinancialBusinessStepPL,
    "ConsentStep": ConsentStep,
    "ReviewStep": ReviewStep,
}


def parse_form(schema_name: str | None, data: dict) -> tuple[dict | None, list[str]]:
    if schema_name is None:
        return data, []
    schema_cls = FORM_SCHEMAS.get(schema_name)
    if schema_cls is None:
        return None, [f"Unknown form schema: {schema_name}"]
    try:
        if schema_name == "IdentityStepES":
            model = schema_cls.model_validate(data)
            answers = model.to_answers()
        elif schema_name == "IdentityStepPL":
            model = schema_cls.model_validate(data)
            answers = model.to_answers()
        elif schema_name == "RepresentativeStepES":
            model = schema_cls.model_validate(data)
            answers = model.to_answers()
        else:
            model = schema_cls.model_validate(data)
            answers = model.model_dump()
        if schema_name == "ReviewStep":
            answers = {"confirmed": True}
        elif schema_name == "ConsentStep":
            answers = model.model_dump()
            answers["consent_terms"] = True
        return answers, []
    except Exception as exc:
        return None, [str(exc)]
