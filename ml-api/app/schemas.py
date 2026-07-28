"""Typed API request, response, and error schemas."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator

from app.config import MAX_COMPLAINT_LENGTH
from app.language import normalize_input
from app.model import LABELS

DepartmentId = Literal[
    "transfer_payment",
    "account_support",
    "card_atm",
    "fraud_security",
    "loan_credit",
    "general_support",
]


class PredictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: Annotated[StrictStr, Field(max_length=MAX_COMPLAINT_LENGTH)]

    @field_validator("text")
    @classmethod
    def normalize_and_validate_text(cls, value: str) -> str:
        normalized = normalize_input(value)
        if not normalized:
            raise ValueError("complaint text must not be empty")
        return normalized


class PredictResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    department_id: DepartmentId
    confidence: float = Field(ge=0.0, le=1.0)
    detected_language: Literal["en"]
    model_version: Literal["v1"]
    fallback: bool
    fallback_reason: Literal["low_classifier_confidence"] | None


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "degraded"]
    service: Literal["complaintguard-ml-api"]
    model_loaded: bool
    model_version: Literal["v1"] | None
    supported_prediction_languages: list[Literal["en"]]
    myanmar_readiness: Literal["development_baseline_not_approved"]


class ErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str | None = None
    type: str | None = None
    detected_language: Literal["my", "mixed", "unsupported"] | None = None


class ErrorBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    details: list[ErrorDetail] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: ErrorBody


assert set(DepartmentId.__args__) == set(LABELS)
