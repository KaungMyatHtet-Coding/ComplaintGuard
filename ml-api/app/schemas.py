"""Typed API request, response, and error schemas."""

from datetime import datetime
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


class SubmitComplaintRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    complaint_text: Annotated[
        StrictStr, Field(alias="complaintText", max_length=MAX_COMPLAINT_LENGTH)
    ]
    input_locale: Literal["en", "my"] = Field(alias="inputLocale")

    @field_validator("complaint_text")
    @classmethod
    def normalize_and_validate_complaint(cls, value: str) -> str:
        normalized = normalize_input(value)
        if not normalized:
            raise ValueError("complaint text must not be empty")
        return normalized


class SubmitComplaintResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    complaint_id: str = Field(alias="complaintId")
    status: Literal["submitted"]


TicketStatus = Literal[
    "submitted", "triaged", "in_progress", "awaiting_customer", "resolved", "closed"
]
TicketPriority = Literal["normal", "high", "urgent"]


class StaffTicketSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    ticket_id: str = Field(alias="ticketId")
    customer_id: str = Field(alias="customerId")
    complaint_text: str = Field(alias="complaintText")
    input_locale: Literal["en", "my"] = Field(alias="inputLocale")
    department_id: DepartmentId = Field(alias="departmentId")
    status: TicketStatus
    priority: TicketPriority
    assigned_staff_id: str | None = Field(alias="assignedStaffId")
    predicted_department_id: DepartmentId | None = Field(alias="predictedDepartmentId")
    prediction_confidence: float | None = Field(
        alias="predictionConfidence", ge=0.0, le=1.0
    )
    routing_source: Literal["model", "manual_review", "manager_override"] = Field(
        alias="routingSource"
    )
    escalated: bool
    resolution_summary: str | None = Field(alias="resolutionSummary")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    resolved_at: datetime | None = Field(alias="resolvedAt")


class StaffMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    message_id: str = Field(alias="messageId")
    author_id: str = Field(alias="authorId")
    author_role: Literal["customer", "staff", "manager"] = Field(alias="authorRole")
    body: str
    visibility: Literal["participants"]
    created_at: datetime = Field(alias="createdAt")


class StaffEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    event_id: str = Field(alias="eventId")
    type: str
    actor_id: str = Field(alias="actorId")
    actor_role: Literal["staff", "manager", "system"] = Field(alias="actorRole")
    from_value: str | None = Field(alias="fromValue")
    to_value: str | None = Field(alias="toValue")
    created_at: datetime = Field(alias="createdAt")


class StaffTicketDetail(StaffTicketSummary):
    messages: list[StaffMessage]
    events: list[StaffEvent]


class StaffTicketListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tickets: list[StaffTicketSummary]


ActionId = Annotated[
    StrictStr, Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
]


class StaffReplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    body: Annotated[StrictStr, Field(max_length=MAX_COMPLAINT_LENGTH)]
    action_id: ActionId = Field(alias="actionId")

    @field_validator("body")
    @classmethod
    def normalize_reply(cls, value: str) -> str:
        normalized = normalize_input(value)
        if not normalized:
            raise ValueError("reply must not be empty")
        return normalized


class StaffTransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    status: Literal["in_progress", "awaiting_customer", "resolved"]
    resolution_summary: Annotated[
        StrictStr | None,
        Field(alias="resolutionSummary", max_length=MAX_COMPLAINT_LENGTH),
    ] = None
    action_id: ActionId = Field(alias="actionId")

    @field_validator("resolution_summary")
    @classmethod
    def normalize_resolution(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = normalize_input(value)
        return normalized or None


class StaffRequestAction(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    type: Literal["request_reassignment", "request_escalation"]
    reason: Annotated[StrictStr, Field(max_length=MAX_COMPLAINT_LENGTH)]
    action_id: ActionId = Field(alias="actionId")

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        normalized = normalize_input(value)
        if not normalized:
            raise ValueError("request reason must not be empty")
        return normalized


class StaffMutationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    ticket_id: str = Field(alias="ticketId")
    action_id: str = Field(alias="actionId")
    status: TicketStatus
    duplicate: bool


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
