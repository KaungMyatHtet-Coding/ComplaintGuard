"""Trusted durable in-app notification contracts and persistence boundaries.

This module deliberately has no workflow trigger integration.  Notification
creation is available only as an internal service method; browser callers can
list and acknowledge notifications belonging to their verified profile.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from app.ticketing import (
    DEPARTMENT_IDS,
    PersistenceError,
    firebase_admin_clients,
    run_firestore_transaction,
)

logger = logging.getLogger(__name__)

NOTIFICATION_POLICY_VERSION = "r0.2b"
NOTIFICATION_HASH_DOMAIN = "complaintguard.notifications"
NOTIFICATION_HASH_VERSION = 1
NOTIFICATION_RETENTION = timedelta(days=90)
MAX_NOTIFICATION_PAGE_SIZE = 50
MAX_READ_ALL_BATCH = 150
MAX_PARAMS_PAYLOAD_LENGTH = 512
NOTIFICATION_REF_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_SAFE_KEY_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,39}$")
_CREDENTIAL_CONTENT_PATTERN = re.compile(
    r"(?i)(password|passcode|credential|secret|token|api[_ -]?key|private[_ -]?key|bearer)"
)
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

NOTIFICATION_TYPES = frozenset(
    {
        "complaint_received",
        "department_assigned",
        "staff_reply",
        "information_requested",
        "status_changed",
        "complaint_resolved",
        "response_target_approaching",
        "response_target_overdue",
        "department_complaint_available",
        "ticket_assigned",
        "customer_reply",
        "high_priority_ticket",
        "manager_reassigned",
        "escalation_updated",
        "manual_review_required",
        "unassigned_ticket",
        "overdue_ticket",
        "escalation_requested",
        "workload_imbalance_observed",
        "pending_account_setup",
        "account_operation_issue",
        "department_workload_observation",
        "system_operational_alert",
    }
)
NOTIFICATION_SEVERITIES = frozenset({"info", "attention", "urgent"})
NOTIFICATION_CATEGORIES = frozenset(
    {"complaint", "assignment", "response", "sla", "account", "workload", "system"}
)
NOTIFICATION_NAVIGATION_TARGETS = frozenset(
    {
        "notifications",
        "customer_ticket",
        "staff_queue",
        "staff_ticket",
        "manager_operations",
        "manager_manual_review",
        "admin_accounts",
        "admin_overview",
    }
)
_ROLE_TYPES = {
    "customer": frozenset(
        {
            "complaint_received",
            "department_assigned",
            "staff_reply",
            "information_requested",
            "status_changed",
            "complaint_resolved",
            "response_target_approaching",
            "response_target_overdue",
        }
    ),
    "staff": frozenset(
        {
            "department_complaint_available",
            "ticket_assigned",
            "customer_reply",
            "high_priority_ticket",
            "response_target_approaching",
            "response_target_overdue",
            "manager_reassigned",
            "escalation_updated",
        }
    ),
    "manager": frozenset(
        {
            "manual_review_required",
            "unassigned_ticket",
            "high_priority_ticket",
            "overdue_ticket",
            "escalation_requested",
            "workload_imbalance_observed",
        }
    ),
    "admin": frozenset(
        {
            "pending_account_setup",
            "account_operation_issue",
            "department_workload_observation",
            "system_operational_alert",
        }
    ),
}

_TYPE_PARAMS = {
    "complaint_received": {"ticketRef"},
    "department_assigned": {"ticketRef", "departmentKey"},
    "staff_reply": {"ticketRef"},
    "information_requested": {"ticketRef"},
    "status_changed": {"ticketRef", "status"},
    "complaint_resolved": {"ticketRef"},
    "response_target_approaching": {"ticketRef"},
    "response_target_overdue": {"ticketRef"},
    "department_complaint_available": {"ticketRef", "departmentKey"},
    "ticket_assigned": {"ticketRef"},
    "customer_reply": {"ticketRef"},
    "high_priority_ticket": {"ticketRef", "priority"},
    "manager_reassigned": {"ticketRef"},
    "escalation_updated": {"ticketRef", "status"},
    "manual_review_required": {"ticketRef"},
    "unassigned_ticket": {"ticketRef", "departmentKey"},
    "overdue_ticket": {"ticketRef"},
    "escalation_requested": {"ticketRef"},
    "workload_imbalance_observed": {"departmentKey", "count"},
    "pending_account_setup": {"count"},
    "account_operation_issue": {"operation"},
    "department_workload_observation": {"departmentKey", "count"},
    "system_operational_alert": {"status"},
}
_SAFE_PARAM_VALUES = {
    "status": frozenset(
        {"submitted", "triaged", "in_progress", "awaiting_customer", "resolved", "closed"}
    ),
    "priority": frozenset({"normal", "high", "urgent"}),
    "departmentKey": DEPARTMENT_IDS,
    "operation": frozenset({"provision", "disable", "reactivate", "department_reassignment"}),
    "ticketRef": None,
}


class NotificationValidationError(ValueError):
    """The trusted caller supplied a value outside the notification contract."""


class NotificationConflictError(RuntimeError):
    """A deterministic notification reference already has different content."""


class NotificationNotFoundError(RuntimeError):
    """The requested notification is absent, expired, or belongs to another user."""


class NotificationProfileError(RuntimeError):
    """The verified identity has no valid active application profile."""


@dataclass(frozen=True)
class NotificationPrincipal:
    uid: str
    role: str


@dataclass(frozen=True)
class NotificationCreateRequest:
    recipient_uid: str
    recipient_role: str
    type: str
    severity: str
    category: str
    title_key: str
    body_key: str
    source_key: str
    navigation_target: str = "notifications"
    related_ticket_ref: str | None = None
    params: dict[str, str | int | bool] = field(default_factory=dict)
    policy_version: str = NOTIFICATION_POLICY_VERSION


@dataclass(frozen=True)
class NotificationRecord:
    notification_ref: str
    recipient_uid: str
    type: str
    severity: str
    category: str
    title_key: str
    body_key: str
    params: dict[str, str | int | bool]
    navigation_target: str
    related_ticket_ref: str | None
    created_at: datetime
    read_at: datetime | None
    policy_version: str
    expires_at: datetime
    dedupe_key_hash: str


@dataclass(frozen=True)
class NotificationPage:
    records: list[NotificationRecord]
    next_cursor: str | None


class NotificationBackend(Protocol):
    def create(self, record: NotificationRecord) -> NotificationRecord: ...

    def list_for_recipient(
        self,
        recipient_uid: str,
        *,
        unread_only: bool,
        cursor: tuple[datetime, datetime, str] | None,
        page_size: int,
        now: datetime,
    ) -> NotificationPage: ...

    def get_for_recipient(
        self, recipient_uid: str, notification_ref: str, *, now: datetime
    ) -> NotificationRecord | None: ...

    def mark_read(
        self, recipient_uid: str, notification_ref: str, *, now: datetime
    ) -> NotificationRecord | None: ...

    def mark_all_read(self, recipient_uid: str, *, now: datetime, limit: int) -> int: ...

    def unread_count(self, recipient_uid: str, *, now: datetime) -> int: ...


class NotificationWriter(Protocol):
    """Trusted transaction participant for workflow-triggered notifications."""

    def stage_create(
        self, transaction: Any, request: NotificationCreateRequest
    ) -> NotificationRecord: ...


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalise_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise NotificationValidationError("notification timestamps must include a timezone")
    return value.astimezone(timezone.utc)


def _strip_text(value: Any) -> Any:
    return value.strip() if isinstance(value, str) else value


def _canonical_hash_input(request: NotificationCreateRequest) -> bytes:
    recipient_uid = request.recipient_uid.strip()
    notification_type = request.type.strip()
    source_key = request.source_key.strip()
    policy_version = request.policy_version.strip()
    payload = {
        "domain": NOTIFICATION_HASH_DOMAIN,
        "version": NOTIFICATION_HASH_VERSION,
        "recipientUid": recipient_uid,
        "type": notification_type,
        "source": source_key,
        "policyVersion": policy_version,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def notification_reference(request: NotificationCreateRequest) -> str:
    """Return the opaque domain-separated reference used for idempotency."""

    return hashlib.sha256(_canonical_hash_input(request)).hexdigest()


def encode_cursor(value: tuple[datetime, datetime, str], *, unread_only: bool) -> str:
    """Encode an unsigned, unencrypted, URL-safe Base64 cursor payload."""

    expires_at, created_at, notification_ref = value
    if not NOTIFICATION_REF_PATTERN.fullmatch(notification_ref):
        raise NotificationValidationError("invalid notification cursor reference")
    payload = {
        "v": 1,
        "unreadOnly": unread_only,
        "expiresAt": _normalise_datetime(expires_at).isoformat(),
        "createdAt": _normalise_datetime(created_at).isoformat(),
        "ref": notification_ref,
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")
    if len(encoded) > 512:
        raise NotificationValidationError("notification cursor is too long")
    return encoded


def decode_cursor(value: str | None, *, unread_only: bool) -> tuple[datetime, str] | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value or len(value) > 512 or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise NotificationValidationError("invalid notification cursor")
    try:
        padding = "=" * (-len(value) % 4)
        payload = json.loads(base64.urlsafe_b64decode(value + padding).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NotificationValidationError("invalid notification cursor") from exc
    if (
        not isinstance(payload, dict)
        or set(payload) != {"v", "unreadOnly", "expiresAt", "createdAt", "ref"}
        or payload.get("v") != 1
        or not isinstance(payload.get("unreadOnly"), bool)
        or payload.get("unreadOnly") is not unread_only
    ):
        raise NotificationValidationError("unsupported notification cursor")
    ref = payload.get("ref")
    created_at = payload.get("createdAt")
    expires_at = payload.get("expiresAt")
    if (
        not isinstance(ref, str)
        or not NOTIFICATION_REF_PATTERN.fullmatch(ref)
        or not isinstance(created_at, str)
        or not isinstance(expires_at, str)
    ):
        raise NotificationValidationError("invalid notification cursor")
    try:
        parsed_expires = _normalise_datetime(datetime.fromisoformat(expires_at))
        parsed_created = _normalise_datetime(datetime.fromisoformat(created_at))
        if parsed_expires != parsed_created + NOTIFICATION_RETENTION:
            raise NotificationValidationError("invalid notification cursor")
        return parsed_expires, parsed_created, ref
    except ValueError as exc:
        raise NotificationValidationError("invalid notification cursor") from exc


def _validate_key(value: Any, *, name: str, max_length: int = 160) -> str:
    if not isinstance(value, str) or not value or len(value) > max_length or not _SAFE_KEY_PATTERN.fullmatch(value):
        raise NotificationValidationError(f"invalid {name}")
    return value


def _validate_localization_key(value: Any) -> str:
    if not isinstance(value, str) or len(value) > 100 or not re.fullmatch(
        r"notifications\.[a-z0-9_]+\.(title|body)", value
    ):
        raise NotificationValidationError("invalid localization key")
    key = value
    if not key.startswith("notifications.") or key.count(".") != 2 or not key.endswith((".title", ".body")):
        raise NotificationValidationError("localization key is not approved")
    notification_type = key.split(".")[1]
    if notification_type not in NOTIFICATION_TYPES:
        raise NotificationValidationError("localization key is not approved")
    return key


def _validate_params(notification_type: str, params: Any) -> dict[str, str | int | bool]:
    if params is None:
        return {}
    if not isinstance(params, dict) or len(params) > 4:
        raise NotificationValidationError("notification params are invalid")
    allowed = _TYPE_PARAMS[notification_type]
    result: dict[str, str | int | bool] = {}
    total_length = 0
    for key, value in params.items():
        if not isinstance(key, str) or not _SAFE_KEY_PATTERN.fullmatch(key) or key not in allowed:
            raise NotificationValidationError("notification param is not approved")
        if isinstance(value, str):
            value = value.strip()
        total_length += len(key) + len(str(value))
        if total_length > MAX_PARAMS_PAYLOAD_LENGTH:
            raise NotificationValidationError("notification params are too large")
        scalar_number = isinstance(value, int) and not isinstance(value, bool)
        safe_scalar = isinstance(value, bool) or (
            scalar_number and -1_000_000 <= value <= 1_000_000
        )
        safe_text = (
            isinstance(value, str)
            and 0 < len(value) <= 120
            and "\n" not in value
            and not _CREDENTIAL_CONTENT_PATTERN.search(value)
            and (
                key not in _SAFE_PARAM_VALUES
                or _SAFE_PARAM_VALUES[key] is None
                or value in _SAFE_PARAM_VALUES[key]
            )
            and (key != "ticketRef" or bool(re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value)))
        )
        if not (safe_scalar or safe_text):
            raise NotificationValidationError("notification param value is invalid")
        result[key] = value
    return result


def validate_creation(request: NotificationCreateRequest, *, now: datetime) -> NotificationRecord:
    normalized = replace(
        request,
        recipient_uid=_strip_text(request.recipient_uid),
        recipient_role=_strip_text(request.recipient_role),
        type=_strip_text(request.type),
        severity=_strip_text(request.severity),
        category=_strip_text(request.category),
        title_key=_strip_text(request.title_key),
        body_key=_strip_text(request.body_key),
        source_key=_strip_text(request.source_key),
        navigation_target=_strip_text(request.navigation_target),
        related_ticket_ref=_strip_text(request.related_ticket_ref),
        policy_version=_strip_text(request.policy_version),
    )
    request = normalized
    if not isinstance(request.recipient_uid, str) or not request.recipient_uid or len(request.recipient_uid) > 128:
        raise NotificationValidationError("recipient is invalid")
    if request.recipient_role not in _ROLE_TYPES:
        raise NotificationValidationError("recipient role is invalid")
    if request.type not in NOTIFICATION_TYPES or request.type not in _ROLE_TYPES[request.recipient_role]:
        raise NotificationValidationError("notification type is not approved for recipient role")
    if request.severity not in NOTIFICATION_SEVERITIES:
        raise NotificationValidationError("notification severity is invalid")
    if request.category not in NOTIFICATION_CATEGORIES:
        raise NotificationValidationError("notification category is invalid")
    if request.navigation_target not in NOTIFICATION_NAVIGATION_TARGETS:
        raise NotificationValidationError("notification navigation target is invalid")
    if request.related_ticket_ref is not None and (
        not isinstance(request.related_ticket_ref, str)
        or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", request.related_ticket_ref)
    ):
        raise NotificationValidationError("related ticket reference is invalid")
    if request.policy_version != NOTIFICATION_POLICY_VERSION:
        raise NotificationValidationError("notification policy version is invalid")
    title_key = _validate_localization_key(request.title_key)
    body_key = _validate_localization_key(request.body_key)
    if title_key.split(".")[1] != request.type or body_key.split(".")[1] != request.type:
        raise NotificationValidationError("localization key does not match notification type")
    if (
        not isinstance(request.source_key, str)
        or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_:/.-]{0,255}", request.source_key)
    ):
        raise NotificationValidationError("invalid source key")
    source_key = request.source_key
    if _CREDENTIAL_CONTENT_PATTERN.search(source_key):
        raise NotificationValidationError("source key is invalid")
    created_at = _normalise_datetime(now)
    reference = notification_reference(request)
    return NotificationRecord(
        notification_ref=reference,
        recipient_uid=request.recipient_uid,
        type=request.type,
        severity=request.severity,
        category=request.category,
        title_key=title_key,
        body_key=body_key,
        params=_validate_params(request.type, request.params),
        navigation_target=request.navigation_target,
        related_ticket_ref=request.related_ticket_ref,
        created_at=created_at,
        read_at=None,
        policy_version=request.policy_version,
        expires_at=created_at + NOTIFICATION_RETENTION,
        dedupe_key_hash=reference,
    )


_PUBLIC_CUSTOMER_STATUSES = frozenset(
    {"submitted", "triaged", "in_progress", "awaiting_customer", "resolved", "closed"}
)
_CUSTOMER_TRIGGER_SPECS = {
    "complaint_received": ("complaint", "notifications.complaint_received", {"ticketRef"}),
    "department_assigned": ("assignment", "notifications.department_assigned", {"ticketRef", "departmentKey"}),
    "staff_reply": ("response", "notifications.staff_reply", {"ticketRef"}),
    "information_requested": ("response", "notifications.information_requested", {"ticketRef"}),
    "status_changed": ("complaint", "notifications.status_changed", {"ticketRef", "status"}),
    "complaint_resolved": ("complaint", "notifications.complaint_resolved", {"ticketRef"}),
}


def build_customer_notification_request(
    *,
    notification_type: str,
    recipient_uid: str,
    ticket_ref: str,
    source_key: str,
    department_key: str | None = None,
    status: str | None = None,
) -> NotificationCreateRequest:
    """Build only the approved Customer trigger shapes for trusted workflows."""

    spec = _CUSTOMER_TRIGGER_SPECS.get(notification_type)
    if spec is None:
        raise NotificationValidationError("unsupported Customer workflow notification")
    category, key_prefix, allowed_params = spec
    if notification_type == "department_assigned" and department_key not in DEPARTMENT_IDS:
        raise NotificationValidationError("Customer department notification requires a safe department")
    if notification_type == "status_changed" and status not in _PUBLIC_CUSTOMER_STATUSES:
        raise NotificationValidationError("Customer status notification requires a public status")
    params: dict[str, str] = {"ticketRef": ticket_ref}
    if department_key is not None:
        params["departmentKey"] = department_key
    if status is not None:
        params["status"] = status
    if set(params) != allowed_params:
        raise NotificationValidationError("Customer notification parameters are incomplete")
    return NotificationCreateRequest(
        recipient_uid=recipient_uid,
        recipient_role="customer",
        type=notification_type,
        severity="info",
        category=category,
        title_key=f"{key_prefix}.title",
        body_key=f"{key_prefix}.body",
        source_key=source_key,
        navigation_target="customer_ticket",
        related_ticket_ref=ticket_ref,
        params=params,
    )


def validate_customer_recipient_profile(
    profile: Any, *, recipient_uid: str, require_active: bool = True
) -> None:
    """Fail closed for malformed Customer recipients and optional active state."""

    if (
        not isinstance(profile, dict)
        or profile.get("role") != "customer"
        or not isinstance(profile.get("active"), bool)
        or (require_active and profile.get("active") is not True)
        or profile.get("departmentId") is not None
        or not isinstance(profile.get("email"), str)
        or not _EMAIL_PATTERN.fullmatch(profile["email"].strip())
        or not isinstance(profile.get("displayName"), str)
        or not profile["displayName"].strip()
        or profile.get("locale") not in {"en", "my"}
        or profile.get("createdAt") is None
        or profile.get("updatedAt") is None
    ):
        raise NotificationProfileError("Customer notification recipient is invalid")
    profile_uid = profile.get("uid")
    if profile_uid is not None and profile_uid != recipient_uid:
        raise NotificationProfileError("Customer notification recipient is invalid")


def stage_customer_notification(
    *,
    transaction: Any,
    db: Any,
    writer: NotificationWriter,
    request: NotificationCreateRequest,
    require_active_profile: bool = False,
) -> NotificationRecord:
    """Validate the trusted ticket owner and stage one notification atomically.

    Initial complaint creation opts into active-profile validation. Later trusted
    ticket mutations may notify a structurally valid inactive owner so that
    existing Staff/Manager work is not blocked; notification read APIs retain
    their separate active-profile authorization.
    """

    recipient_uid = request.recipient_uid
    if (
        not isinstance(recipient_uid, str)
        or not recipient_uid
        or len(recipient_uid) > 128
        or recipient_uid != recipient_uid.strip()
        or any(ord(character) < 32 for character in recipient_uid)
    ):
        raise NotificationProfileError("Customer notification recipient is invalid")

    profile_ref = db.collection("users").document(recipient_uid)
    profile_snapshot = next(transaction.get(profile_ref))
    if not profile_snapshot.exists:
        raise NotificationProfileError("Customer notification recipient is invalid")
    validate_customer_recipient_profile(
        profile_snapshot.to_dict(),
        recipient_uid=recipient_uid,
        require_active=require_active_profile,
    )
    return writer.stage_create(transaction, request)


def _immutable_payload(record: NotificationRecord) -> dict[str, Any]:
    return {
        "recipientUid": record.recipient_uid,
        "type": record.type,
        "severity": record.severity,
        "category": record.category,
        "relatedTicketRef": record.related_ticket_ref,
        "titleKey": record.title_key,
        "bodyKey": record.body_key,
        "params": record.params,
        "navigationTarget": record.navigation_target,
        "policyVersion": record.policy_version,
        "dedupeKeyHash": record.dedupe_key_hash,
    }


def _validate_persisted_record(record: NotificationRecord) -> NotificationRecord:
    if not NOTIFICATION_REF_PATTERN.fullmatch(record.notification_ref):
        raise NotificationValidationError("stored notification reference is invalid")
    if not isinstance(record.recipient_uid, str) or not record.recipient_uid:
        raise NotificationValidationError("stored notification recipient is invalid")
    if record.type not in NOTIFICATION_TYPES or record.severity not in NOTIFICATION_SEVERITIES:
        raise NotificationValidationError("stored notification enum is invalid")
    if record.category not in NOTIFICATION_CATEGORIES or record.navigation_target not in NOTIFICATION_NAVIGATION_TARGETS:
        raise NotificationValidationError("stored notification enum is invalid")
    title_key = _validate_localization_key(record.title_key)
    body_key = _validate_localization_key(record.body_key)
    if title_key.split(".")[1] != record.type or body_key.split(".")[1] != record.type:
        raise NotificationValidationError("stored localization key is invalid")
    _validate_params(record.type, record.params)
    if record.related_ticket_ref is not None and not re.fullmatch(
        r"[A-Za-z0-9_-]{1,128}", record.related_ticket_ref
    ):
        raise NotificationValidationError("stored ticket reference is invalid")
    if record.dedupe_key_hash != record.notification_ref:
        raise NotificationValidationError("stored dedupe reference is invalid")
    if record.expires_at != record.created_at + NOTIFICATION_RETENTION:
        raise NotificationValidationError("stored notification expiry is invalid")
    return record


def _record_order(record: NotificationRecord) -> tuple[datetime, datetime, str]:
    return (
        _normalise_datetime(record.expires_at),
        _normalise_datetime(record.created_at),
        record.notification_ref,
    )


class InMemoryNotificationBackend:
    """Pure fake repository; no Firebase SDK or network is constructed."""

    def __init__(self) -> None:
        self.records: dict[str, NotificationRecord] = {}

    def create(self, record: NotificationRecord) -> NotificationRecord:
        existing = self.records.get(record.notification_ref)
        if existing is not None:
            if _immutable_payload(existing) != _immutable_payload(record):
                raise NotificationConflictError("notification reference conflict")
            return existing
        self.records[record.notification_ref] = record
        return record

    def list_for_recipient(self, recipient_uid: str, *, unread_only: bool, cursor: tuple[datetime, datetime, str] | None, page_size: int, now: datetime) -> NotificationPage:
        current = _normalise_datetime(now)
        records = [
            record for record in self.records.values()
            if record.recipient_uid == recipient_uid
            and record.expires_at > current
            and (not unread_only or record.read_at is None)
        ]
        records.sort(key=_record_order, reverse=True)
        if cursor is not None:
            records = [record for record in records if _record_order(record) < cursor]
        page = records[:page_size]
        next_cursor = (
            encode_cursor(_record_order(page[-1]), unread_only=unread_only)
            if len(records) > page_size
            else None
        )
        return NotificationPage(page, next_cursor)

    def get_for_recipient(self, recipient_uid: str, notification_ref: str, *, now: datetime) -> NotificationRecord | None:
        record = self.records.get(notification_ref)
        if record is None or record.recipient_uid != recipient_uid or record.expires_at <= _normalise_datetime(now):
            return None
        return record

    def mark_read(self, recipient_uid: str, notification_ref: str, *, now: datetime) -> NotificationRecord | None:
        record = self.get_for_recipient(recipient_uid, notification_ref, now=now)
        if record is None:
            return None
        if record.read_at is None:
            record = replace(record, read_at=_normalise_datetime(now))
            self.records[notification_ref] = record
        return record

    def mark_all_read(self, recipient_uid: str, *, now: datetime, limit: int) -> int:
        current = _normalise_datetime(now)
        unread = [
            record for record in self.records.values()
            if record.recipient_uid == recipient_uid and record.read_at is None and record.expires_at > current
        ]
        unread.sort(key=_record_order, reverse=True)
        for record in unread[:limit]:
            self.mark_read(recipient_uid, record.notification_ref, now=current)
        return min(len(unread), limit)

    def unread_count(self, recipient_uid: str, *, now: datetime) -> int:
        current = _normalise_datetime(now)
        return sum(
            record.recipient_uid == recipient_uid and record.read_at is None and record.expires_at > current
            for record in self.records.values()
        )


class NotificationService:
    def __init__(self, backend: NotificationBackend, *, clock: Any = _utc_now) -> None:
        self._backend = backend
        self._clock = clock

    def create(self, request: NotificationCreateRequest) -> NotificationRecord:
        return self._backend.create(validate_creation(request, now=self._clock()))

    def list(self, recipient_uid: str, *, unread_only: bool, cursor: str | None, page_size: int) -> NotificationPage:
        if not 1 <= page_size <= MAX_NOTIFICATION_PAGE_SIZE:
            raise NotificationValidationError("notification page size is invalid")
        return self._backend.list_for_recipient(
            recipient_uid,
            unread_only=unread_only,
            cursor=decode_cursor(cursor, unread_only=unread_only),
            page_size=page_size,
            now=self._clock(),
        )

    def mark_read(self, recipient_uid: str, notification_ref: str) -> NotificationRecord:
        _validate_reference(notification_ref)
        record = self._backend.mark_read(recipient_uid, notification_ref, now=self._clock())
        if record is None:
            raise NotificationNotFoundError("notification not found")
        return record

    def mark_all_read(self, recipient_uid: str) -> int:
        return self._backend.mark_all_read(recipient_uid, now=self._clock(), limit=MAX_READ_ALL_BATCH)

    def unread_count(self, recipient_uid: str) -> int:
        return self._backend.unread_count(recipient_uid, now=self._clock())


def _validate_reference(value: str) -> str:
    if not isinstance(value, str) or not NOTIFICATION_REF_PATTERN.fullmatch(value):
        raise NotificationValidationError("notification reference is invalid")
    return value


def require_active_notification_profile(authorization: str | None, backend: Any) -> NotificationPrincipal:
    """Authorize any active, structurally valid application profile."""

    if not authorization:
        from app.ticketing import AuthenticationError

        raise AuthenticationError("Firebase ID token required")
    scheme, separator, token = authorization.partition(" ")
    if separator != " " or scheme.lower() != "bearer" or not token.strip():
        from app.ticketing import AuthenticationError

        raise AuthenticationError("Firebase ID token required")
    try:
        uid = backend.verify_id_token(token.strip())
    except Exception as exc:
        from app.ticketing import AuthenticationError

        raise AuthenticationError("invalid Firebase ID token") from exc
    if not isinstance(uid, str) or not uid.strip():
        raise NotificationProfileError("verified identity is invalid")
    try:
        profile = backend.get_user_profile(uid)
    except Exception as exc:
        raise PersistenceError("profile lookup failed") from exc
    if not isinstance(profile, dict) or profile.get("active") is not True:
        raise NotificationProfileError("active application profile required")
    if (
        not isinstance(profile.get("email"), str)
        or not _EMAIL_PATTERN.fullmatch(profile["email"].strip())
        or not isinstance(profile.get("displayName"), str)
        or not profile["displayName"].strip()
        or profile.get("locale") not in {"en", "my"}
        or profile.get("createdAt") is None
        or profile.get("updatedAt") is None
    ):
        raise NotificationProfileError("complete application profile required")
    role = profile.get("role")
    if role not in _ROLE_TYPES:
        raise NotificationProfileError("valid application role required")
    profile_uid = profile.get("uid")
    if profile_uid is not None and profile_uid != uid:
        raise NotificationProfileError("profile identity mismatch")
    department_id = profile.get("departmentId")
    if role == "staff" and department_id not in DEPARTMENT_IDS:
        raise NotificationProfileError("valid staff department required")
    if role != "staff" and department_id not in (None, ""):
        raise NotificationProfileError("invalid non-staff department")
    return NotificationPrincipal(uid=uid, role=role)


class FirebaseAdminNotificationBackend:
    """Local-only Admin SDK adapter; construction is explicitly fail-closed."""

    def __init__(self, db: Any = None, server_timestamp: object | None = None) -> None:
        if db is not None:
            self._db = db
            if server_timestamp is None:
                from firebase_admin import firestore

                server_timestamp = firestore.SERVER_TIMESTAMP
            self._server_timestamp = server_timestamp
            return
        try:
            _, self._db, self._server_timestamp = firebase_admin_clients()
        except Exception as exc:
            logger.warning("Firebase Admin notification adapter initialization failed (%s)", type(exc).__name__)
            raise PersistenceError("Firebase Admin is not configured") from exc

    @staticmethod
    def _record_from_document(data: dict[str, Any], ref: str) -> NotificationRecord:
        return _validate_persisted_record(NotificationRecord(
            notification_ref=ref,
            recipient_uid=data["recipientUid"],
            type=data["type"],
            severity=data["severity"],
            category=data["category"],
            title_key=data["titleKey"],
            body_key=data["bodyKey"],
            params=dict(data.get("params", {})),
            navigation_target=data["navigationTarget"],
            related_ticket_ref=data.get("relatedTicketRef"),
            created_at=_normalise_datetime(data["createdAt"]),
            read_at=_normalise_datetime(data["readAt"]) if data.get("readAt") else None,
            policy_version=data["policyVersion"],
            expires_at=_normalise_datetime(data["expiresAt"]),
            dedupe_key_hash=data["dedupeKeyHash"],
        ))

    def _stage_record(
        self, transaction: Any, record: NotificationRecord
    ) -> NotificationRecord:
        reference = self._db.collection("notifications").document(record.notification_ref)
        document = _immutable_payload(record) | {"createdAt": self._server_timestamp, "readAt": None, "expiresAt": record.expires_at}
        snapshot = next(transaction.get(reference))
        if snapshot.exists:
            existing = self._record_from_document(snapshot.to_dict(), snapshot.id)
            if _immutable_payload(existing) != _immutable_payload(record):
                raise NotificationConflictError("notification reference conflict")
            return existing
        transaction.create(reference, document)
        return record

    def stage_create(
        self, transaction: Any, request: NotificationCreateRequest
    ) -> NotificationRecord:
        return self._stage_record(transaction, validate_creation(request, now=_utc_now()))

    def create(self, record: NotificationRecord) -> NotificationRecord:
        def operation(transaction: Any) -> NotificationRecord:
            return self._stage_record(transaction, record)

        try:
            return run_firestore_transaction(self._db, operation)
        except (NotificationConflictError, NotificationValidationError):
            raise
        except Exception as exc:
            raise PersistenceError("notification creation transaction failed") from exc

    def _query(
        self,
        recipient_uid: str,
        *,
        unread_only: bool,
        now: datetime,
        cursor: tuple[datetime, datetime, str] | None,
    ) -> Any:
        from google.cloud.firestore_v1.base_query import FieldFilter
        from google.cloud.firestore_v1.field_path import FieldPath

        query = self._db.collection("notifications").where(
            filter=FieldFilter("recipientUid", "==", recipient_uid)
        )
        if unread_only:
            query = query.where(filter=FieldFilter("readAt", "==", None))
        query = query.where(filter=FieldFilter("expiresAt", ">", _normalise_datetime(now)))
        query = query.order_by("expiresAt", direction="DESCENDING").order_by(
            "createdAt", direction="DESCENDING"
        ).order_by(FieldPath.document_id(), direction="DESCENDING")
        if cursor is not None:
            query = query.start_after(cursor)
        return query

    def list_for_recipient(self, recipient_uid: str, *, unread_only: bool, cursor: tuple[datetime, datetime, str] | None, page_size: int, now: datetime) -> NotificationPage:
        records = []
        for snapshot in self._query(
            recipient_uid, unread_only=unread_only, now=now, cursor=cursor
        ).stream():
            data = snapshot.to_dict()
            if data.get("createdAt") is None or data.get("expiresAt") is None:
                continue
            try:
                record = self._record_from_document(data, snapshot.id)
            except (KeyError, TypeError, ValueError, NotificationValidationError):
                continue
            if unread_only and record.read_at is not None:
                continue
            records.append(record)
        records.sort(key=_record_order, reverse=True)
        page = records[:page_size]
        return NotificationPage(
            page,
            encode_cursor(_record_order(page[-1]), unread_only=unread_only)
            if len(records) > page_size
            else None,
        )

    def get_for_recipient(self, recipient_uid: str, notification_ref: str, *, now: datetime) -> NotificationRecord | None:
        snapshot = self._db.collection("notifications").document(notification_ref).get()
        if not snapshot.exists:
            return None
        try:
            record = self._record_from_document(snapshot.to_dict(), snapshot.id)
        except (KeyError, TypeError, ValueError, NotificationValidationError):
            return None
        if record.recipient_uid != recipient_uid or record.expires_at <= _normalise_datetime(now):
            return None
        return record

    def mark_read(self, recipient_uid: str, notification_ref: str, *, now: datetime) -> NotificationRecord | None:
        reference = self._db.collection("notifications").document(notification_ref)
        current = _normalise_datetime(now)

        def operation(transaction: Any) -> NotificationRecord | None:
            snapshot = next(transaction.get(reference))
            if not snapshot.exists:
                return None
            try:
                record = self._record_from_document(snapshot.to_dict(), snapshot.id)
            except (KeyError, TypeError, ValueError, NotificationValidationError):
                return None
            if record.recipient_uid != recipient_uid or record.expires_at <= current:
                return None
            if record.read_at is None:
                transaction.update(reference, {"readAt": self._server_timestamp})
                return replace(record, read_at=current)
            return record

        try:
            return run_firestore_transaction(self._db, operation)
        except Exception as exc:
            raise PersistenceError("notification read transaction failed") from exc

    def mark_all_read(self, recipient_uid: str, *, now: datetime, limit: int) -> int:
        current = _normalise_datetime(now)
        references = []
        for snapshot in self._query(
            recipient_uid, unread_only=True, now=current, cursor=None
        ).stream():
            try:
                record = self._record_from_document(snapshot.to_dict(), snapshot.id)
            except (KeyError, TypeError, ValueError, NotificationValidationError):
                continue
            if record.read_at is None:
                references.append(snapshot.reference)
            if len(references) == limit:
                break
        if not references:
            return 0
        batch = self._db.batch()
        for reference in references:
            batch.update(reference, {"readAt": self._server_timestamp})
        try:
            batch.commit()
        except Exception as exc:
            raise PersistenceError("notification read-all failed") from exc
        return len(references)

    def unread_count(self, recipient_uid: str, *, now: datetime) -> int:
        current = _normalise_datetime(now)
        return sum(
            1
            for snapshot in self._query(
                recipient_uid, unread_only=True, now=current, cursor=None
            ).stream()
            if (record := self._safe_record_from_snapshot(snapshot)) is not None
            and record.read_at is None
        )

    def _safe_record_from_snapshot(self, snapshot: Any) -> NotificationRecord | None:
        try:
            return self._record_from_document(snapshot.to_dict(), snapshot.id)
        except (KeyError, TypeError, ValueError, NotificationValidationError):
            return None
