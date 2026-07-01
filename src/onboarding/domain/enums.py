from enum import Enum


class Country(str, Enum):
    SE = "SE"
    ES = "ES"
    PL = "PL"


class AccountType(str, Enum):
    PRIVATE = "private"
    BUSINESS = "business"


class ApplicationStatus(str, Enum):
    DRAFT = "draft"
    PROCESSING = "processing"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    MANUAL_REVIEW = "manual_review"
    REJECTED = "rejected"
    ABANDONED = "abandoned"


class DecisionOutcome(str, Enum):
    APPROVED = "approved"
    MANUAL_REVIEW = "manual_review"
    REJECTED = "rejected"


class IntegrationCheckType(str, Enum):
    IDENTITY = "identity"
    ADDRESS = "address"
    REGISTRY = "registry"
    KYB = "kyb"
    SANCTIONS = "sanctions"
    CREDIT = "credit"
    AFFORDABILITY = "affordability"
    BANK_ACCOUNT = "bank_account"
    SIGNATORY = "signatory"
    UBO = "ubo"


class CheckOutcome(str, Enum):
    VERIFIED = "verified"
    DOCUMENT_MISMATCH = "document_mismatch"
    EXPIRED_ID = "expired_id"
    MANUAL_REVIEW = "manual_review"
    ACTIVE_COMPANY = "active_company"
    DISSOLVED = "dissolved"
    UNKNOWN_REPRESENTATIVE = "unknown_representative"
    MISSING_UBO = "missing_ubo"
    NO_HIT = "no_hit"
    POSSIBLE_HIT = "possible_hit"
    CONFIRMED_HIT = "confirmed_hit"
    PASS = "pass"
    FAIL = "fail"
    BORDERLINE = "borderline"
    IBAN_VERIFIED = "iban_verified"
    NAME_MISMATCH = "name_mismatch"
    UNREACHABLE = "unreachable"
    TIMEOUT = "timeout"
