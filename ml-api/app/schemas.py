"""Typed API request, response, and error schemas."""

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictStr,
    field_validator,
    model_validator,
)

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

ActionId = Annotated[
    StrictStr, Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
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
    action_id: ActionId = Field(alias="actionId")

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
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    ticket_id: str = Field(alias="ticketId")
    customer_id: str = Field(alias="customerId")
    complaint_text: str = Field(alias="complaintText")
    input_locale: Literal["en", "my"] = Field(alias="inputLocale")
    department_id: DepartmentId | None = Field(default=None, alias="departmentId")
    status: TicketStatus
    priority: TicketPriority
    assigned_staff_id: str | None = Field(default=None, alias="assignedStaffId")
    predicted_department_id: DepartmentId | None = Field(
        default=None, alias="predictedDepartmentId"
    )
    prediction_confidence: float | None = Field(
        default=None, alias="predictionConfidence", ge=0.0, le=1.0
    )
    routing_source: Literal["model", "manual_review", "manager_override", "pending"] = (
        Field(default="pending", alias="routingSource")
    )
    escalated: bool = False
    resolution_summary: str | None = Field(default=None, alias="resolutionSummary")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    resolved_at: datetime | None = Field(default=None, alias="resolvedAt")

    @model_validator(mode="before")
    @classmethod
    def pre_normalize(cls, values: Any) -> Any:
        if isinstance(values, dict):
            tid = values.get("ticketId") or values.get("id")
            if tid:
                values["ticketId"] = tid
                values["id"] = tid
            values["departmentId"] = values.get("departmentId")
        return values


class StaffMessage(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    message_id: str = Field(alias="messageId")
    author_id: str = Field(alias="authorId")
    author_role: Literal["customer", "staff", "manager"] = Field(alias="authorRole")
    body: str
    visibility: Literal["participants"]
    created_at: datetime = Field(alias="createdAt")


class StaffEvent(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

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


class CustomerTicketSummary(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str
    status: TicketStatus
    complaint_text: str = Field(default="", alias="complaintText")
    summary_text: str = Field(default="", alias="summaryText")
    predicted_department_id: str | None = Field(
        default=None, alias="predictedDepartmentId"
    )
    prediction_confidence: float | None = Field(
        default=None, alias="predictionConfidence", ge=0.0, le=1.0
    )
    routing_source: Literal["model", "manual_review", "manager_override", "pending"] = (
        Field(default="pending", alias="routingSource")
    )
    assigned_department_id: str | None = Field(
        default=None, alias="assignedDepartmentId"
    )
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")


class CustomerTicketListResponse(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    tickets: list[CustomerTicketSummary]


class CustomerMessageItem(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str | None = None
    message_id: str = Field(default="", alias="messageId")
    sender_id: str = Field(alias="senderId")
    sender_role: Literal["customer", "staff"] = Field(alias="senderRole")
    text: str
    created_at: str = Field(alias="createdAt")

    @model_validator(mode="before")
    @classmethod
    def set_msg_id(cls, data: Any) -> Any:
        if isinstance(data, dict):
            msg_id = data.get("messageId") or data.get("id") or ""
            data["messageId"] = msg_id
            data["id"] = msg_id
        return data


class CustomerTicketDetail(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str
    status: TicketStatus
    complaint_text: str = Field(alias="complaintText")
    input_locale: Literal["en", "my"] = Field(alias="inputLocale")
    predicted_department_id: DepartmentId | None = Field(
        default=None, alias="predictedDepartmentId"
    )
    prediction_confidence: float | None = Field(
        default=None, alias="predictionConfidence", ge=0.0, le=1.0
    )
    routing_source: Literal["model", "manual_review", "manager_override", "pending"] = (
        Field(default="pending", alias="routingSource")
    )
    assigned_department_id: DepartmentId | None = Field(
        default=None, alias="assignedDepartmentId"
    )
    priority: str
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")
    resolved_at: str | None = Field(default=None, alias="resolvedAt")
    messages: list[CustomerMessageItem] = Field(default_factory=list)
    rating: int | None = None
    feedback_comments: str | None = Field(default=None, alias="feedbackComments")


class CustomerMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    text: Annotated[StrictStr, Field(default="", max_length=MAX_COMPLAINT_LENGTH)]
    action_id: ActionId = Field(alias="actionId")

    @model_validator(mode="before")
    @classmethod
    def pre_normalize(cls, values: Any) -> Any:
        if (
            isinstance(values, dict)
            and "messageText" in values
            and ("text" not in values or not values["text"])
        ):
            values["text"] = values.pop("messageText")
        return values

    @field_validator("text")
    @classmethod
    def normalize_message_text(cls, value: str) -> str:
        normalized = normalize_input(value)
        if not normalized:
            raise ValueError("message text must not be empty")
        return normalized


class CustomerFeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    rating: Annotated[int, Field(ge=1, le=5)]
    comments: Annotated[StrictStr | None, Field(max_length=MAX_COMPLAINT_LENGTH)] = None
    action_id: ActionId = Field(alias="actionId")


class CustomerFeedbackResponse(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    ticket_id: str = Field(alias="ticketId")
    feedback_id: str | None = Field(default=None, alias="feedbackId")
    rating: int | None = None
    submitted_at: str | None = Field(default=None, alias="submittedAt")
    status: str = "feedback_submitted"


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


class DepartmentMetricItem(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    department_id: DepartmentId = Field(alias="departmentId")
    label: str
    total: int
    in_progress: int = Field(alias="inProgress")
    resolved: int
    avg_resolution_hours: float = Field(alias="avgResolutionHours")


class ManagerAnalyticsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    total_tickets: int = Field(alias="totalTickets")
    active_tickets: int = Field(alias="activeTickets")
    resolved_tickets: int = Field(alias="resolvedTickets")
    low_confidence_count: int = Field(alias="lowConfidenceCount")
    avg_resolution_hours: float = Field(alias="avgResolutionHours")
    department_metrics: list[DepartmentMetricItem] = Field(alias="departmentMetrics")


class LowConfidenceTicketItem(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str
    customer_id: str = Field(alias="customerId")
    complaint_text: str = Field(alias="complaintText")
    input_locale: Literal["en", "my"] = Field(alias="inputLocale")
    predicted_department_id: DepartmentId | None = Field(
        default=None, alias="predictedDepartmentId"
    )
    prediction_confidence: float | None = Field(
        default=None, alias="predictionConfidence"
    )
    department_id: DepartmentId | None = Field(default=None, alias="departmentId")
    status: str
    priority: str
    routing_source: str = Field(alias="routingSource")
    created_at: datetime = Field(alias="createdAt")


class ManagerOverrideRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    new_department_id: DepartmentId = Field(alias="newDepartmentId")
    reason: str | None = Field(default=None, max_length=1000)
    action_id: ActionId = Field(alias="actionId")


class ManagerOverrideResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    ticket_id: str = Field(alias="ticketId")
    department_id: DepartmentId = Field(alias="departmentId")
    routing_source: Literal["manager_override"] = Field(alias="routingSource")
    updated_at: str = Field(alias="updatedAt")


assert set(DepartmentId.__args__) == set(LABELS)
