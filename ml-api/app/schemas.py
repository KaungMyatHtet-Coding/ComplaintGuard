"""Typed API request, response, and error schemas."""

import re
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
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

AdminProvisioningRole = Literal["staff", "manager"]
AdminDirectoryRole = Literal["customer", "staff", "manager", "admin"]
AdminProvisioningStatus = Literal["pending_setup"]
AdminDirectoryAccountState = Literal["active", "pending_setup", "disabled", "inactive_unverified"]
LifecycleProfileState = Literal["active", "inactive"]
LifecycleRecoveryState = Literal["none", "recoverable", "completed", "operator_required"]
LifecycleRecoveryOperation = Literal["disable", "reactivate", "reassign_department"]
LifecycleEligibilityReason = Literal[
    "already_active",
    "already_inactive",
    "self_target_forbidden",
    "last_active_admin",
    "role_not_reassignable",
    "assigned_unresolved_work",
    "pending_setup_activation_forbidden",
    "lifecycle_conflict",
]


class AdminDisableRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: Annotated[
        StrictStr,
        Field(alias="idempotencyKey", min_length=8, max_length=64),
    ]

    @field_validator("idempotency_key")
    @classmethod
    def normalize_disable_idempotency_key(cls, value: str) -> str:
        normalized = normalize_input(value)
        if not normalized or not re.fullmatch(r"[A-Za-z0-9_-]+", normalized):
            raise ValueError("idempotency key must be safe")
        return normalized


class AdminDisableResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    account_ref: Annotated[StrictStr, Field(pattern=r"^acct_v1_[0-9a-f]{64}$")] = Field(alias="accountRef")
    operation: Literal["disable"]
    status: Literal["completed"]
    profile_state: Literal["inactive"] = Field(alias="profileState")


class AdminReactivateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: Annotated[
        StrictStr,
        Field(alias="idempotencyKey", min_length=8, max_length=64),
    ]

    @field_validator("idempotency_key")
    @classmethod
    def normalize_reactivate_idempotency_key(cls, value: str) -> str:
        normalized = normalize_input(value)
        if not normalized or not re.fullmatch(r"[A-Za-z0-9_-]+", normalized):
            raise ValueError("idempotency key must be safe")
        return normalized


class AdminReactivateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    account_ref: Annotated[StrictStr, Field(pattern=r"^acct_v1_[0-9a-f]{64}$")] = Field(alias="accountRef")
    operation: Literal["reactivate"]
    status: Literal["completed"]
    profile_state: Literal["active"] = Field(alias="profileState")


class AdminReassignDepartmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: Annotated[
        StrictStr,
        Field(alias="idempotencyKey", min_length=8, max_length=64),
    ]
    department_id: DepartmentId = Field(alias="departmentId")

    @field_validator("idempotency_key")
    @classmethod
    def normalize_reassignment_idempotency_key(cls, value: str) -> str:
        if not value.isascii() or not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", value):
            raise ValueError("idempotency key must be safe")
        return value


class AdminReassignDepartmentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    account_ref: Annotated[StrictStr, Field(pattern=r"^acct_v1_[0-9a-f]{64}$")] = Field(alias="accountRef")
    operation: Literal["reassign_department"]
    status: Literal["completed"]
    department_id: DepartmentId = Field(alias="departmentId")


class AdminDisableRecoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: Literal["disable"]


class AdminReactivateRecoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: Literal["reactivate"]


class AdminReassignRecoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: Literal["reassign_department"]
    department_id: DepartmentId = Field(alias="departmentId")


AdminLifecycleRecoveryRequest = Annotated[
    AdminDisableRecoveryRequest | AdminReactivateRecoveryRequest | AdminReassignRecoveryRequest,
    Field(discriminator="operation"),
]

AdminLifecycleRecoveryResponse = AdminDisableResponse | AdminReactivateResponse | AdminReassignDepartmentResponse


class AdminProvisioningRequest(BaseModel):
    """Strict future Admin input; it deliberately has no credential fields."""

    model_config = ConfigDict(extra="forbid")

    email: Annotated[StrictStr, Field(min_length=3, max_length=254)]
    display_name: Annotated[
        StrictStr, Field(alias="displayName", min_length=1, max_length=100)
    ]
    locale: Literal["en", "my"]
    role: AdminProvisioningRole
    department_id: DepartmentId | None = Field(default=None, alias="departmentId")
    idempotency_key: Annotated[
        StrictStr,
        Field(alias="idempotencyKey", min_length=8, max_length=64),
    ]

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise ValueError("email must be valid")
        return normalized

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str) -> str:
        normalized = normalize_input(value)
        if not normalized:
            raise ValueError("display name must not be empty")
        return normalized

    @field_validator("idempotency_key")
    @classmethod
    def normalize_idempotency_key(cls, value: str) -> str:
        normalized = normalize_input(value)
        if not normalized or not re.fullmatch(r"[A-Za-z0-9_-]+", normalized):
            raise ValueError("idempotency key must be safe")
        return normalized

    @model_validator(mode="after")
    def validate_role_department(self) -> "AdminProvisioningRequest":
        if self.role == "staff" and self.department_id is None:
            raise ValueError("staff requires a department")
        if self.role == "manager" and self.department_id is not None:
            raise ValueError("manager cannot have a department")
        return self


class AdminProvisioningResponse(BaseModel):
    """Safe future result; credentials, tokens, claims, and timestamps are absent."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    status: AdminProvisioningStatus
    uid: str | None = None
    email: str
    display_name: str = Field(alias="displayName")
    locale: Literal["en", "my"]
    role: AdminProvisioningRole
    department_id: DepartmentId | None = Field(alias="departmentId")
    active: bool
    setup_required: bool = Field(alias="setupRequired")


class AdminDirectoryRequest(BaseModel):
    """Strict bounded filters for the read-only Admin directory."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    role: AdminDirectoryRole | None = None
    department_id: DepartmentId | None = Field(default=None, alias="departmentId")
    active: bool | None = None
    search: Annotated[StrictStr, Field(min_length=1, max_length=80)] | None = None
    page_size: Annotated[int, Field(ge=1, le=50)] = Field(default=25, alias="pageSize")
    cursor: Annotated[StrictStr, Field(max_length=128)] | None = None

    @field_validator("search")
    @classmethod
    def normalize_search(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = normalize_input(value)
        return normalized or None


class AdminDirectoryRow(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    email: str
    display_name: str = Field(alias="displayName")
    locale: Literal["en", "my"]
    role: AdminDirectoryRole
    department_id: DepartmentId | None = Field(alias="departmentId")
    active: StrictBool
    account_state: AdminDirectoryAccountState = Field(alias="accountState")
    account_ref: Annotated[StrictStr, Field(pattern=r"^acct_v1_[0-9a-f]{64}$")] = Field(alias="accountRef")


class AdminDirectoryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    rows: list[AdminDirectoryRow]
    next_cursor: str | None = Field(alias="nextCursor")
    has_more: StrictBool = Field(alias="hasMore")


class LifecycleEligibilityOperation(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    eligible: StrictBool
    reason: LifecycleEligibilityReason | None = None


class LifecycleEligibilityOperations(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    disable: LifecycleEligibilityOperation
    reactivate: LifecycleEligibilityOperation
    reassign_department: LifecycleEligibilityOperation = Field(alias="reassignDepartment")


class AdminLifecycleEligibilityResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    account_ref: Annotated[StrictStr, Field(pattern=r"^acct_v1_[0-9a-f]{64}$")] = Field(alias="accountRef")
    profile_state: LifecycleProfileState = Field(alias="profileState")
    operations: LifecycleEligibilityOperations


class AdminLifecycleRecoveryStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    account_ref: Annotated[StrictStr, Field(pattern=r"^acct_v1_[0-9a-f]{64}$")] = Field(alias="accountRef")
    recovery_state: LifecycleRecoveryState = Field(alias="recoveryState")
    operation: LifecycleRecoveryOperation | None
    department_id: DepartmentId | None = Field(alias="departmentId")

    @model_validator(mode="after")
    def validate_projection(self) -> "AdminLifecycleRecoveryStatusResponse":
        if self.recovery_state in {"none", "operator_required"}:
            if self.operation is not None or self.department_id is not None:
                raise ValueError("recovery details are not valid for this state")
        elif self.operation is None:
            raise ValueError("recoverable or completed state requires an operation")
        elif self.operation == "reassign_department":
            if self.department_id is None:
                raise ValueError("reassignment state requires a department")
        elif self.department_id is not None:
            raise ValueError("department is only valid for reassignment")
        return self


class CustomerProfileRequest(BaseModel):
    """Public profile-completion fields; credentials and authority stay elsewhere."""

    model_config = ConfigDict(extra="forbid")

    display_name: Annotated[
        StrictStr, Field(alias="displayName", min_length=1, max_length=100)
    ]
    locale: Literal["en", "my"]
    terms_accepted: StrictBool | None = Field(
        default=None,
        alias="termsAccepted",
        description="Validated for this request only; not persisted in this slice.",
    )

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str) -> str:
        normalized = normalize_input(value)
        if not normalized:
            raise ValueError("display name must not be empty")
        return normalized


class CustomerProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    uid: str
    email: str
    display_name: str = Field(alias="displayName")
    locale: Literal["en", "my"]
    role: Literal["customer"]
    department_id: None = Field(default=None, alias="departmentId")
    active: Literal[True]


class CustomerProfileResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    status: Literal["created", "existing"]
    profile: CustomerProfile


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
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    status: TicketStatus
    priority: str = "normal"
    department_id: DepartmentId | None = Field(default=None, alias="departmentId")
    summary_text: str = Field(default="", alias="summaryText")
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")
    resolved_at: str | None = Field(default=None, alias="resolvedAt")


class CustomerTicketListResponse(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    tickets: list[CustomerTicketSummary]


class CustomerMessageItem(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    sender_role: Literal["customer", "support_team"] = Field(alias="senderRole")
    body: str
    created_at: str = Field(alias="createdAt")


CustomerTimelineType = Literal[
    "complaint_received",
    "assigned_to_team",
    "review_started",
    "information_requested",
    "team_replied",
    "customer_replied",
    "complaint_resolved",
    "complaint_closed",
]


class CustomerTimelineItem(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    type: CustomerTimelineType
    occurred_at: str = Field(alias="occurredAt")
    department_id: DepartmentId | None = Field(default=None, alias="departmentId")


class CustomerTicketFeedback(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    rating: Annotated[int, Field(ge=1, le=5)]
    comments: str | None = None
    submitted_at: str = Field(alias="submittedAt")


class CustomerTicketDetail(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    status: TicketStatus
    complaint_text: str = Field(alias="complaintText")
    input_locale: Literal["en", "my"] = Field(alias="inputLocale")
    priority: str
    department_id: DepartmentId | None = Field(default=None, alias="departmentId")
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")
    resolved_at: str | None = Field(default=None, alias="resolvedAt")
    messages: list[CustomerMessageItem] = Field(default_factory=list)
    timeline: list[CustomerTimelineItem] = Field(default_factory=list)
    feedback: CustomerTicketFeedback | None = None


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


NotificationType = Literal[
    "complaint_received", "department_assigned", "staff_reply", "information_requested",
    "status_changed", "complaint_resolved", "response_target_approaching", "response_target_overdue",
    "department_complaint_available", "ticket_assigned", "customer_reply", "high_priority_ticket",
    "manager_reassigned", "escalation_updated", "manual_review_required", "unassigned_ticket",
    "overdue_ticket", "escalation_requested", "workload_imbalance_observed", "pending_account_setup",
    "account_operation_issue", "department_workload_observation", "system_operational_alert",
]
NotificationSeverity = Literal["info", "attention", "urgent"]
NotificationCategory = Literal[
    "complaint", "assignment", "response", "sla", "account", "workload", "system"
]
NotificationNavigationTarget = Literal[
    "notifications", "customer_ticket", "staff_queue", "staff_ticket",
    "manager_operations", "manager_manual_review", "admin_accounts", "admin_overview",
]


class NotificationItem(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    notification_ref: str = Field(alias="notificationRef", pattern=r"^[0-9a-f]{64}$")
    type: NotificationType
    severity: NotificationSeverity
    category: NotificationCategory
    related_ticket_ref: str | None = Field(default=None, alias="relatedTicketRef")
    title_key: str = Field(alias="titleKey")
    body_key: str = Field(alias="bodyKey")
    params: dict[str, str | int | bool] = Field(default_factory=dict)
    navigation_target: NotificationNavigationTarget = Field(alias="navigationTarget")
    created_at: datetime = Field(alias="createdAt")
    read_at: datetime | None = Field(default=None, alias="readAt")
    unread: StrictBool


class NotificationListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    notifications: list[NotificationItem]
    next_cursor: str | None = Field(default=None, alias="nextCursor")


class NotificationUnreadCountResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    unread_count: Annotated[int, Field(ge=0)] = Field(alias="unreadCount")


class NotificationReadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    notification_ref: str = Field(alias="notificationRef", pattern=r"^[0-9a-f]{64}$")
    read_at: datetime = Field(alias="readAt")
    unread: Literal[False] = False


class NotificationReadAllResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    updated_count: Annotated[int, Field(ge=0, le=150)] = Field(alias="updatedCount")


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
