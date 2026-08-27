"""ComplaintGuard Day 15 Customer Workflow Backend Service."""

from __future__ import annotations

import base64
import hashlib
import json
import math
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.message_schema import normalize_message_document
from app.schemas import (
    CustomerFeedbackRequest,
    CustomerFeedbackResponse,
    CustomerMessageItem,
    CustomerMessageRequest,
    CustomerTicketDetail,
    CustomerTicketListResponse,
    CustomerTicketSummary,
    CustomerTimelineItem,
)
from app.ticketing import PersistenceError
from app.ticketing import redact_sensitive_data as redact_pii

CUSTOMER_HISTORY_STATUSES = frozenset(
    {
        "submitted",
        "triaged",
        "in_progress",
        "awaiting_customer",
        "resolved",
        "closed",
    }
)
CUSTOMER_HISTORY_DEPARTMENTS = frozenset(
    {
        "transfer_payment",
        "account_support",
        "card_atm",
        "fraud_security",
        "loan_credit",
        "general_support",
    }
)
_PUBLIC_DEPARTMENTS = CUSTOMER_HISTORY_DEPARTMENTS
_TIMELINE_STATUS_TYPES = {
    "in_progress": "review_started",
    "awaiting_customer": "information_requested",
    "resolved": "complaint_resolved",
    "closed": "complaint_closed",
}
_TIMELINE_STATUS_RANKS = {
    "in_progress": 30,
    "awaiting_customer": 31,
    "resolved": 32,
    "closed": 33,
}
_TICKET_ID_PATTERN = re.compile(r"^ticket_[a-f0-9]{32}$")
CUSTOMER_HISTORY_DEFAULT_PAGE_SIZE = 25
CUSTOMER_HISTORY_MIN_PAGE_SIZE = 1
CUSTOMER_HISTORY_MAX_PAGE_SIZE = 50
CUSTOMER_HISTORY_CURSOR_MAX_LENGTH = 512
CUSTOMER_HISTORY_CURSOR_VERSION = 2
CUSTOMER_HISTORY_ENVIRONMENT = "local-emulator"
CUSTOMER_HISTORY_PROJECT = "demo-complaintguard"
_CUSTOMER_HISTORY_CURSOR_DOMAIN = "complaintguard:customer-history-cursor:v2"
_CUSTOMER_HISTORY_QUERY_DOMAIN = "complaintguard:customer-history-query:v2"
_CUSTOMER_HISTORY_PROJECTION = (
    "complaintId",
    "status",
    "departmentId",
    "createdAt",
    "updatedAt",
    "resolvedAt",
)
_RFC3339_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?"
    r"(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$"
)
_MESSAGE_ACTION_DOMAIN = "complaintguard:customer-message:v1"
_MESSAGE_ACTION_VERSION = 1
_MESSAGE_ACTION_OPERATION = "customer_message"
_MESSAGE_ACTION_FINGERPRINT_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_ACTION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
_MESSAGE_READ_LIMIT = 100
_MESSAGE_READ_BOUND = _MESSAGE_READ_LIMIT + 1


class CustomerHistoryCursorError(ValueError):
    """Raised when a Customer History cursor is not canonical and compatible."""


class CustomerHistoryDataError(PersistenceError):
    """Raised when an owned ticket cannot be safely projected."""


class CustomerMessageIdempotencyConflict(ValueError):
    """Raised when an action ID is reused for different message details."""


def _message_request_fingerprint(
    customer_id: str,
    ticket_id: str,
    message_text: str,
    action_id: str,
) -> str:
    canonical = json.dumps(
        {
            "actionId": action_id,
            "customerId": customer_id,
            "domain": _MESSAGE_ACTION_DOMAIN,
            "messageText": message_text,
            "ticketId": ticket_id,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _canonical_message_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _validated_message_action_result(
    record: Any,
    expected_fingerprint: str,
    expected_customer_id: str,
    expected_ticket_id: str,
    expected_action_id: str,
) -> dict[str, Any]:
    required_keys = {
        "version",
        "type",
        "customerId",
        "ticketId",
        "operation",
        "state",
        "actionId",
        "fingerprint",
        "messageId",
        "result",
    }
    if not isinstance(record, dict) or set(record) != required_keys:
        raise PersistenceError("customer message idempotency record is invalid")
    if (
        type(record.get("version")) is not int
        or record.get("version") != _MESSAGE_ACTION_VERSION
        or record.get("type") != _MESSAGE_ACTION_OPERATION
        or record.get("operation") != _MESSAGE_ACTION_OPERATION
        or record.get("state") != "completed"
    ):
        raise PersistenceError("customer message idempotency record is invalid")
    if not isinstance(record.get("customerId"), str) or not record["customerId"]:
        raise PersistenceError("customer message idempotency record is invalid")
    if not isinstance(record.get("ticketId"), str) or not record["ticketId"]:
        raise PersistenceError("customer message idempotency record is invalid")
    if not isinstance(record.get("actionId"), str) or not _ACTION_ID_PATTERN.fullmatch(record["actionId"]):
        raise PersistenceError("customer message idempotency record is invalid")
    if not isinstance(record.get("messageId"), str) or record["messageId"] != record["actionId"]:
        raise PersistenceError("customer message idempotency record is invalid")
    if record["customerId"] != expected_customer_id or record["ticketId"] != expected_ticket_id:
        raise CustomerMessageIdempotencyConflict(
            "This message action was already used for different details."
        )
    if record["actionId"] != expected_action_id:
        raise PersistenceError("customer message idempotency record is invalid")
    persisted_fingerprint = record.get("fingerprint")
    if (
        not isinstance(persisted_fingerprint, str)
        or not _MESSAGE_ACTION_FINGERPRINT_PATTERN.fullmatch(persisted_fingerprint)
    ):
        raise PersistenceError("customer message idempotency record is invalid")
    if persisted_fingerprint != expected_fingerprint:
        raise CustomerMessageIdempotencyConflict(
            "This message action was already used for different details."
        )
    try:
        result = CustomerMessageItem.model_validate(record.get("result"))
    except Exception as exc:
        raise PersistenceError("customer message idempotency result is invalid") from exc
    if (
        result.sender_role != "customer"
        or not _is_timeline_timestamp(result.created_at)
        or not result.created_at.endswith("Z")
    ):
        raise PersistenceError("customer message idempotency result is invalid")
    try:
        parsed_result_timestamp = _timestamp_from_value(result.created_at)
    except CustomerHistoryDataError as exc:
        raise PersistenceError("customer message idempotency result is invalid") from exc
    if result.created_at != _rfc3339(parsed_result_timestamp):
        raise PersistenceError("customer message idempotency result is invalid")
    return result.model_dump(by_alias=True)


def _validated_persisted_customer_message(
    record: Any,
    expected_customer_id: str,
    expected_action_id: str,
    expected_result: dict[str, Any],
) -> None:
    if not isinstance(record, dict):
        raise PersistenceError("customer message persistence is invalid")
    try:
        canonical = normalize_message_document(record)
    except (TypeError, ValueError) as exc:
        raise PersistenceError("customer message persistence is invalid") from exc
    if set(canonical) != {
        "authorId",
        "authorRole",
        "body",
        "visibility",
        "createdAt",
        "id",
    }:
        raise PersistenceError("customer message persistence is invalid")
    if (
        canonical.get("id") != expected_action_id
        or canonical.get("authorId") != expected_customer_id
        or canonical.get("authorRole") != "customer"
        or canonical.get("visibility") != "participants"
        or not isinstance(canonical.get("body"), str)
    ):
        raise PersistenceError("customer message persistence is invalid")
    occurred_at = _timestamp_text(canonical.get("createdAt"))
    if not occurred_at or not _is_timeline_timestamp(occurred_at):
        raise PersistenceError("customer message persistence is invalid")
    if canonical["body"] != expected_result["body"]:
        raise PersistenceError("customer message persistence is invalid")
    try:
        persisted_at = _timestamp_from_value(occurred_at)
        result_at = _timestamp_from_value(expected_result["createdAt"])
    except CustomerHistoryDataError as exc:
        raise PersistenceError("customer message persistence is invalid") from exc
    if persisted_at.astimezone(timezone.utc) != result_at.astimezone(timezone.utc):
        raise PersistenceError("customer message persistence is invalid")


class CustomerHistoryCursor:
    def __init__(
        self,
        created_at: datetime,
        complaint_id: str,
        filters: CustomerHistoryFilters | None = None,
    ) -> None:
        self.created_at = created_at
        self.complaint_id = complaint_id
        self.filters = filters or CustomerHistoryFilters()


@dataclass(frozen=True)
class CustomerHistoryFilters:
    status: str | None = None
    department_id: str | None = None


def validate_customer_history_filters(filters: CustomerHistoryFilters) -> None:
    if (
        filters.status is not None
        and filters.status not in CUSTOMER_HISTORY_STATUSES
    ):
        raise ValueError("customer history status is invalid")
    if (
        filters.department_id is not None
        and filters.department_id not in CUSTOMER_HISTORY_DEPARTMENTS
    ):
        raise ValueError("customer history department is invalid")


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _sha256_hex(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def customer_history_binding(customer_id: str) -> str:
    return _sha256_hex(
        {
            "domain": _CUSTOMER_HISTORY_CURSOR_DOMAIN,
            "environment": CUSTOMER_HISTORY_ENVIRONMENT,
            "project": CUSTOMER_HISTORY_PROJECT,
            "uid": customer_id,
        }
    )


def customer_history_contract_fingerprint(
    filters: CustomerHistoryFilters | None = None,
) -> str:
    selected = filters or CustomerHistoryFilters()
    validate_customer_history_filters(selected)
    return _sha256_hex(
        {
            "domain": _CUSTOMER_HISTORY_QUERY_DOMAIN,
            "pageSize": {
                "default": CUSTOMER_HISTORY_DEFAULT_PAGE_SIZE,
                "min": CUSTOMER_HISTORY_MIN_PAGE_SIZE,
                "max": CUSTOMER_HISTORY_MAX_PAGE_SIZE,
            },
            "projection": list(_CUSTOMER_HISTORY_PROJECTION),
            "query": {
                "filters": {
                    "status": selected.status,
                    "departmentId": selected.department_id,
                },
                "order": [["createdAt", "DESC"], ["__name__", "DESC"]],
            },
        }
    )


def _timestamp_from_value(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and _RFC3339_PATTERN.fullmatch(value):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise CustomerHistoryDataError("ticket timestamp is invalid") from exc
    else:
        raise CustomerHistoryDataError("ticket timestamp is invalid")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CustomerHistoryDataError("ticket timestamp has no UTC offset")
    return parsed


def _rfc3339(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _cursor_payload(cursor: CustomerHistoryCursor, customer_id: str) -> dict[str, object]:
    return {
        "v": CUSTOMER_HISTORY_CURSOR_VERSION,
        "customerBinding": customer_history_binding(customer_id),
        "contract": customer_history_contract_fingerprint(cursor.filters),
        "createdAt": _rfc3339(cursor.created_at),
        "complaintId": cursor.complaint_id,
    }


def encode_customer_history_cursor(
    cursor: CustomerHistoryCursor,
    customer_id: str,
    filters: CustomerHistoryFilters | None = None,
) -> str:
    if filters is not None and filters != cursor.filters:
        cursor = CustomerHistoryCursor(cursor.created_at, cursor.complaint_id, filters)
    payload = _cursor_payload(cursor, customer_id)
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    encoded = base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")
    if len(encoded) > CUSTOMER_HISTORY_CURSOR_MAX_LENGTH:
        raise CustomerHistoryCursorError("cursor is too long")
    return encoded


def _strict_object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, item in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = item
    return result


def decode_customer_history_cursor(
    value: str,
    customer_id: str,
    filters: CustomerHistoryFilters | None = None,
) -> CustomerHistoryCursor:
    selected = filters or CustomerHistoryFilters()
    validate_customer_history_filters(selected)
    if (
        not isinstance(value, str)
        or not value
        or len(value) > CUSTOMER_HISTORY_CURSOR_MAX_LENGTH
        or not value.isascii()
        or "=" in value
        or not re.fullmatch(r"[A-Za-z0-9_-]+", value)
        or len(value) % 4 == 1
    ):
        raise CustomerHistoryCursorError("cursor is invalid")
    try:
        padding = "=" * (-len(value) % 4)
        raw = base64.b64decode(value + padding, altchars=b"-_", validate=True)
        payload = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_strict_object_pairs
        )
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CustomerHistoryCursorError("cursor is invalid") from exc
    if (
        not isinstance(payload, dict)
        or list(payload) != ["v", "customerBinding", "contract", "createdAt", "complaintId"]
        or payload.get("v") != CUSTOMER_HISTORY_CURSOR_VERSION
        or not isinstance(payload.get("customerBinding"), str)
        or not re.fullmatch(r"[0-9a-f]{64}", payload["customerBinding"])
        or payload["customerBinding"] != customer_history_binding(customer_id)
        or not isinstance(payload.get("contract"), str)
        or not re.fullmatch(r"[0-9a-f]{64}", payload["contract"])
        or payload["contract"]
        != customer_history_contract_fingerprint(selected)
        or not isinstance(payload.get("createdAt"), str)
        or not isinstance(payload.get("complaintId"), str)
        or not _TICKET_ID_PATTERN.fullmatch(payload["complaintId"])
    ):
        raise CustomerHistoryCursorError("cursor is incompatible")
    try:
        created_at = _timestamp_from_value(payload["createdAt"])
    except CustomerHistoryDataError as exc:
        raise CustomerHistoryCursorError("cursor timestamp is invalid") from exc
    if payload["createdAt"] != _rfc3339(created_at):
        raise CustomerHistoryCursorError("cursor timestamp is not canonical")
    cursor = CustomerHistoryCursor(created_at, payload["complaintId"], selected)
    try:
        canonical = encode_customer_history_cursor(cursor, customer_id)
    except (CustomerHistoryCursorError, UnicodeEncodeError) as exc:
        raise CustomerHistoryCursorError("cursor is not canonical") from exc
    if canonical != value:
        raise CustomerHistoryCursorError("cursor is not canonical")
    return cursor


def _timestamp_text(value: Any) -> str | None:
    try:
        return _rfc3339(_timestamp_from_value(value))
    except CustomerHistoryDataError:
        return None


def _require_canonical_timestamp(value: Any, label: str) -> str:
    try:
        parsed = _timestamp_from_value(value)
    except CustomerHistoryDataError as exc:
        raise CustomerHistoryDataError(f"{label} is invalid") from exc
    canonical = _rfc3339(parsed)
    if isinstance(value, str) and value != canonical:
        raise CustomerHistoryDataError(f"{label} is not canonical")
    return canonical


def _timeline_sort_key(item: dict[str, Any]) -> tuple[datetime, int, str]:
    occurred_at = item["occurredAt"].replace("Z", "+00:00")
    parsed = datetime.fromisoformat(occurred_at)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed, int(item.get("rank", 0)), item["type"]


def _is_timeline_timestamp(value: str) -> bool:
    try:
        return _require_canonical_timestamp(value, "timeline timestamp") == value
    except CustomerHistoryDataError:
        return False


class CustomerWorkflowError(Exception):
    """Base exception for customer workflow operations."""


class TicketAccessDenied(CustomerWorkflowError):
    """Raised when customer attempts to access another user's ticket."""


class TicketNotFound(CustomerWorkflowError):
    """Raised when ticket ID does not exist."""


class InvalidTicketState(CustomerWorkflowError):
    """Raised when operation is invalid for current ticket state."""


class FeedbackAlreadySubmitted(CustomerWorkflowError):
    """Raised when a ticket already has feedback from a prior action."""


def _sample_dev_tickets() -> list[dict[str, Any]]:
    return [
        {
            "id": "cg_ticket_001",
            "customerId": "demo_customer_uid",
            "status": "in_progress",
            "complaintText": "Money transfer was deducted from my account but recipient has not received it yet.",
            "inputLocale": "en",
            "predictedDepartmentId": "transfer_payment",
            "assignedDepartmentId": "transfer_payment",
            "priority": "normal",
            "createdAt": "2026-08-02T10:00:00Z",
            "updatedAt": "2026-08-03T11:00:00Z",
            "messages": [
                {
                    "id": "msg_01",
                    "senderId": "demo_customer_uid",
                    "senderRole": "customer",
                    "text": "Hello, I sent money yesterday but the status says pending.",
                    "createdAt": "2026-08-02T10:05:00Z",
                },
                {
                    "id": "msg_02",
                    "senderId": "staff_01",
                    "senderRole": "staff",
                    "text": "We are verifying with the partner bank. Please allow up to 24 hours.",
                    "createdAt": "2026-08-02T10:30:00Z",
                },
            ],
        },
        {
            "id": "cg_ticket_002",
            "customerId": "demo_customer_uid",
            "status": "resolved",
            "complaintText": "ATM at Downtown branch failed to dispense cash during withdrawal.",
            "inputLocale": "en",
            "predictedDepartmentId": "card_atm",
            "assignedDepartmentId": "card_atm",
            "priority": "high",
            "createdAt": "2026-07-29T14:00:00Z",
            "updatedAt": "2026-07-30T09:00:00Z",
            "resolvedAt": "2026-07-30T09:00:00Z",
            "messages": [],
        },
    ]


class CustomerBackend(ABC):
    """Abstract interface for Customer Firestore operations."""

    @abstractmethod
    def list_customer_tickets(
        self,
        customer_id: str,
        page_size: int,
        cursor: CustomerHistoryCursor | None,
        filters: CustomerHistoryFilters,
    ) -> list[dict[str, Any]]:
        """List at most page_size + 1 owned tickets after the cursor."""

    @abstractmethod
    def get_customer_ticket(
        self, customer_id: str, ticket_id: str
    ) -> dict[str, Any] | None:
        """Get ticket dict if owned by customer_id, else None if not found or denied."""

    @abstractmethod
    def get_ticket_messages(self, ticket_id: str) -> list[dict[str, Any]]:
        """Get all message thread items for a ticket."""

    @abstractmethod
    def get_ticket_events(self, ticket_id: str) -> list[dict[str, Any]]:
        """Get immutable ticket events for safe server-side projection."""

    @abstractmethod
    def add_customer_message(
        self,
        customer_id: str,
        ticket_id: str,
        message_text: str,
        created_at: datetime,
        action_id: str,
        request_text: str | None = None,
    ) -> dict[str, Any]:
        """Add customer message to ticket thread and update ticket timestamp."""

    @abstractmethod
    def save_ticket_feedback(
        self,
        customer_id: str,
        ticket_id: str,
        rating: int,
        comments: str,
        created_at: datetime,
        action_id: str,
    ) -> dict[str, Any]:
        """Save feedback rating/comments for a resolved ticket."""


class InMemoryCustomerBackend(CustomerBackend):
    """In-memory mock backend for testing and development."""

    def __init__(self, initial_tickets: list[dict[str, Any]] | None = None) -> None:
        tickets = initial_tickets or []
        self.tickets = {ticket["id"]: dict(ticket) for ticket in tickets}
        self.messages = {
            ticket["id"]: list(ticket.get("messages", [])) for ticket in tickets
        }
        self.events = {
            ticket["id"]: list(ticket.get("events", [])) for ticket in tickets
        }
        self.feedbacks: dict[str, dict[str, Any]] = {}
        self.actions: dict[tuple[str, str], dict[str, Any]] = {}
        self.message_actions: dict[str, dict[str, Any]] = {}

    def list_customer_tickets(
        self,
        customer_id: str,
        page_size: int,
        cursor: CustomerHistoryCursor | None,
        filters: CustomerHistoryFilters,
    ) -> list[dict[str, Any]]:
        records: list[tuple[datetime, str, dict[str, Any]]] = []
        validate_customer_history_filters(filters)
        for ticket in self.tickets.values():
            if ticket.get("customerId") != customer_id:
                continue
            if filters.status is not None and ticket.get("status") != filters.status:
                continue
            if (
                filters.department_id is not None
                and ticket.get("departmentId") != filters.department_id
            ):
                continue
            created_at = _timestamp_from_value(ticket.get("createdAt"))
            ticket_id = ticket.get("id")
            if not isinstance(ticket_id, str) or not _TICKET_ID_PATTERN.fullmatch(ticket_id):
                raise CustomerHistoryDataError("ticket reference is invalid")
            records.append((created_at, ticket_id, ticket))
        records.sort(key=lambda item: (item[0], item[1]), reverse=True)
        if cursor is not None:
            records = [
                item
                for item in records
                if (item[0], item[1]) < (cursor.created_at, cursor.complaint_id)
            ]
        return [item[2] for item in records[: page_size + 1]]

    def get_customer_ticket(
        self, customer_id: str, ticket_id: str
    ) -> dict[str, Any] | None:
        t = self.tickets.get(ticket_id)
        if not t:
            return None
        if t.get("customerId") != customer_id:
            return None
        return t

    def get_ticket_messages(self, ticket_id: str) -> list[dict[str, Any]]:
        msgs = self.messages.get(ticket_id, [])
        if len(msgs) > _MESSAGE_READ_BOUND:
            raise PersistenceError("customer message limit exceeded")
        try:
            msgs_sorted = sorted(
                msgs,
                key=lambda item: (
                    _timestamp_from_value(item.get("createdAt")),
                    item.get("id", ""),
                ),
            )
        except Exception as exc:
            raise PersistenceError("customer messages cannot be ordered safely") from exc
        if len(msgs_sorted) > _MESSAGE_READ_LIMIT:
            raise PersistenceError("customer message limit exceeded")
        return msgs_sorted

    def get_ticket_events(self, ticket_id: str) -> list[dict[str, Any]]:
        return list(self.events.get(ticket_id, []))

    def add_customer_message(
        self,
        customer_id: str,
        ticket_id: str,
        message_text: str,
        created_at: datetime,
        action_id: str,
        request_text: str | None = None,
    ) -> dict[str, Any]:
        fingerprint = _message_request_fingerprint(
            customer_id,
            ticket_id,
            request_text if request_text is not None else message_text,
            action_id,
        )
        if action_id in self.message_actions:
            result = _validated_message_action_result(
                self.message_actions[action_id],
                fingerprint,
                customer_id,
                ticket_id,
                action_id,
            )
            stored = next(
                (item for item in self.messages.get(ticket_id, []) if item.get("id") == action_id),
                None,
            )
            _validated_persisted_customer_message(
                stored, customer_id, action_id, result
            )
            return result
        msg_id = action_id
        response_timestamp = _canonical_message_timestamp(created_at)
        msg_doc = {
            "id": msg_id,
            "authorId": customer_id,
            "authorRole": "customer",
            "body": message_text,
            "visibility": "participants",
            "createdAt": response_timestamp,
        }
        if any(item.get("id") == action_id for item in self.messages.get(ticket_id, [])):
            raise PersistenceError("customer message persistence is contradictory")
        if ticket_id not in self.messages:
            self.messages[ticket_id] = []
        self.messages[ticket_id].append(msg_doc)
        result = {
            "senderRole": "customer",
            "body": message_text,
            "createdAt": response_timestamp,
        }
        self.message_actions[action_id] = {
            "version": _MESSAGE_ACTION_VERSION,
            "type": "customer_message",
            "customerId": customer_id,
            "ticketId": ticket_id,
            "operation": _MESSAGE_ACTION_OPERATION,
            "state": "completed",
            "actionId": action_id,
            "fingerprint": fingerprint,
            "messageId": msg_id,
            "result": dict(result),
        }

        if ticket_id in self.tickets:
            self.tickets[ticket_id]["updatedAt"] = response_timestamp

        return result

    def save_ticket_feedback(
        self,
        customer_id: str,
        ticket_id: str,
        rating: int,
        comments: str,
        created_at: datetime,
        action_id: str,
    ) -> dict[str, Any]:
        key = (ticket_id, f"feedback:{action_id}")
        if key in self.actions:
            return dict(self.actions[key])
        fb_id = f"fb_{ticket_id}"
        if fb_id in self.feedbacks or self.tickets.get(ticket_id, {}).get("feedback"):
            raise FeedbackAlreadySubmitted("Feedback has already been submitted.")
        iso_str = _canonical_message_timestamp(created_at)
        doc = {
            "id": fb_id,
            "ticketId": ticket_id,
            "customerId": customer_id,
            "rating": rating,
            "comments": comments,
            "createdAt": iso_str,
        }
        self.feedbacks[fb_id] = doc
        self.actions[key] = dict(doc)
        if ticket_id in self.tickets:
            self.tickets[ticket_id]["feedback"] = {
                "rating": rating,
                "comments": comments,
                "submittedAt": iso_str,
            }
        return doc


class FirebaseAdminCustomerBackend(CustomerBackend):
    """Production Firestore backend using Firebase Admin SDK."""

    def __init__(self, db: Any = None, notification_writer: Any = None) -> None:
        if db is not None:
            self.db = db
            from firebase_admin import firestore
            self.server_timestamp = firestore.SERVER_TIMESTAMP
        else:
            try:
                from app.ticketing import firebase_admin_clients

                _, self.db, self.server_timestamp = firebase_admin_clients()
            except Exception as exc:
                from app.ticketing import PersistenceError

                raise PersistenceError("Firebase Admin is not configured") from exc
        if notification_writer is None:
            from app.notifications import FirebaseAdminNotificationBackend
            notification_writer = FirebaseAdminNotificationBackend(
                db=self.db, server_timestamp=self.server_timestamp
            )
        self._notification_writer = notification_writer

    def list_customer_tickets(
        self,
        customer_id: str,
        page_size: int,
        cursor: CustomerHistoryCursor | None,
        filters: CustomerHistoryFilters,
    ) -> list[dict[str, Any]]:
        from google.cloud.firestore_v1.base_query import FieldFilter

        validate_customer_history_filters(filters)
        query = (
            self.db.collection("tickets")
            .where(filter=FieldFilter("customerId", "==", customer_id))
        )
        if filters.status is not None:
            query = query.where(filter=FieldFilter("status", "==", filters.status))
        if filters.department_id is not None:
            query = query.where(
                filter=FieldFilter(
                    "departmentId", "==", filters.department_id
                )
            )
        query = (
            query
            .order_by("createdAt", direction="DESCENDING")
            .order_by("__name__", direction="DESCENDING")
        )
        if cursor is not None:
            query = query.start_after(
                {
                    "createdAt": cursor.created_at,
                    "__name__": self.db.collection("tickets").document(cursor.complaint_id),
                }
            )
        docs = query.limit(page_size + 1).stream()
        results = []
        for d in docs:
            data = d.to_dict()
            data["id"] = d.id
            results.append(data)
        return results

    def get_customer_ticket(
        self, customer_id: str, ticket_id: str
    ) -> dict[str, Any] | None:
        doc_ref = self.db.collection("tickets").document(ticket_id)
        snapshot = doc_ref.get()
        if not snapshot.exists:
            return None
        data = snapshot.to_dict()
        if data.get("customerId") != customer_id:
            return None
        data["id"] = snapshot.id
        return data

    def get_ticket_messages(self, ticket_id: str) -> list[dict[str, Any]]:
        msgs_ref = (
            self.db.collection("tickets")
            .document(ticket_id)
            .collection("messages")
            .order_by("createdAt", direction="ASCENDING")
            .order_by("__name__", direction="ASCENDING")
            .limit(_MESSAGE_READ_BOUND)
        )
        results = []
        for d in msgs_ref.stream():
            data = d.to_dict()
            data["id"] = d.id
            results.append(data)
        if len(results) > _MESSAGE_READ_LIMIT:
            raise PersistenceError("customer message limit exceeded")
        return results

    def get_ticket_events(self, ticket_id: str) -> list[dict[str, Any]]:
        events_ref = (
            self.db.collection("tickets")
            .document(ticket_id)
            .collection("events")
            .order_by("createdAt")
        )
        results = []
        for d in events_ref.stream():
            data = d.to_dict()
            data["eventId"] = d.id
            results.append(data)
        return results

    def add_customer_message(
        self,
        customer_id: str,
        ticket_id: str,
        message_text: str,
        created_at: datetime,
        action_id: str,
        request_text: str | None = None,
    ) -> dict[str, Any]:
        from app.ticketing import PersistenceError, run_firestore_transaction

        doc_ref = self.db.collection("tickets").document(ticket_id)
        msg_ref = doc_ref.collection("messages").document(action_id)
        action_ref = self.db.collection("customerMessageActions").document(action_id)
        legacy_action_ref = doc_ref.collection("actions").document(f"message_{action_id}")
        fingerprint = _message_request_fingerprint(
            customer_id,
            ticket_id,
            request_text if request_text is not None else message_text,
            action_id,
        )
        msg_data = {
            "authorId": customer_id,
            "authorRole": "customer",
            "body": message_text,
            "visibility": "participants",
            "createdAt": created_at,
        }
        result = {
            "senderRole": "customer",
            "body": message_text,
            "createdAt": _canonical_message_timestamp(created_at),
        }
        try:

            def operation(transaction: Any) -> dict[str, Any]:
                action_snapshot = next(transaction.get(action_ref))
                legacy_action_snapshot = next(transaction.get(legacy_action_ref))
                message_snapshot = next(transaction.get(msg_ref))
                if legacy_action_snapshot.exists:
                    raise PersistenceError(
                        "legacy customer message idempotency record is unsupported"
                    )
                if action_snapshot.exists:
                    replay = _validated_message_action_result(
                        action_snapshot.to_dict(),
                        fingerprint,
                        customer_id,
                        ticket_id,
                        action_id,
                    )
                    if not message_snapshot.exists:
                        raise PersistenceError(
                            "customer message idempotency record has no message"
                        )
                    persisted_message = message_snapshot.to_dict() or {}
                    if "id" in persisted_message:
                        raise PersistenceError("customer message persistence is invalid")
                    persisted_message["id"] = message_snapshot.id
                    _validated_persisted_customer_message(
                        persisted_message, customer_id, action_id, replay
                    )
                    return replay
                if message_snapshot.exists:
                    raise PersistenceError(
                        "customer message exists without idempotency record"
                    )
                ticket_snapshot = next(transaction.get(doc_ref))
                ticket_data = ticket_snapshot.to_dict() or {}
                if not ticket_snapshot.exists or ticket_data.get("customerId") != customer_id:
                    raise TicketNotFound("Ticket not found.")
                from app.notifications import stage_staff_ticket_notification

                stage_staff_ticket_notification(
                    transaction=transaction, db=self.db,
                    writer=self._notification_writer, ticket=ticket_data,
                    ticket_ref=ticket_id,
                    source_key=f"ticket:{ticket_id}:customer_reply:{action_id}",
                )
                transaction.set(msg_ref, msg_data)
                transaction.update(doc_ref, {"updatedAt": created_at})
                transaction.set(
                    action_ref,
                    {
                        "version": _MESSAGE_ACTION_VERSION,
                        "type": "customer_message",
                        "customerId": customer_id,
                        "ticketId": ticket_id,
                        "operation": _MESSAGE_ACTION_OPERATION,
                        "state": "completed",
                        "actionId": action_id,
                        "fingerprint": fingerprint,
                        "messageId": action_id,
                        "result": result,
                    },
                )
                return result

            return run_firestore_transaction(self.db, operation)
        except (CustomerMessageIdempotencyConflict, TicketNotFound):
            raise
        except PersistenceError:
            raise
        except Exception as exc:
            raise PersistenceError("customer message transaction failed") from exc

    def save_ticket_feedback(
        self,
        customer_id: str,
        ticket_id: str,
        rating: int,
        comments: str,
        created_at: datetime,
        action_id: str,
    ) -> dict[str, Any]:
        from app.ticketing import PersistenceError, run_firestore_transaction

        ticket_ref = self.db.collection("tickets").document(ticket_id)
        fb_ref = self.db.collection("feedback").document(f"fb_{ticket_id}")
        action_ref = ticket_ref.collection("actions").document(f"feedback_{action_id}")
        fb_data = {
            "ticketId": ticket_id,
            "customerId": customer_id,
            "rating": rating,
            "comments": comments,
            "createdAt": created_at,
        }
        result = {**fb_data, "id": fb_ref.id, "createdAt": created_at.isoformat()}
        try:

            def operation(transaction: Any) -> dict[str, Any]:
                action_snapshot = next(transaction.get(action_ref))
                if action_snapshot.exists:
                    return action_snapshot.to_dict()["result"]
                feedback_snapshot = next(transaction.get(fb_ref))
                ticket_snapshot = next(transaction.get(ticket_ref))
                ticket_data = ticket_snapshot.to_dict() or {}
                if feedback_snapshot.exists or ticket_data.get("feedback"):
                    raise FeedbackAlreadySubmitted(
                        "Feedback has already been submitted."
                    )
                transaction.set(fb_ref, fb_data)
                transaction.update(
                    ticket_ref,
                    {
                        "feedback": {
                            "rating": rating,
                            "comments": comments,
                            "submittedAt": created_at,
                        }
                    },
                )
                transaction.set(
                    action_ref, {"type": "customer_feedback", "result": result}
                )
                return result

            return run_firestore_transaction(self.db, operation)
        except FeedbackAlreadySubmitted:
            raise
        except Exception as exc:
            raise PersistenceError("customer feedback transaction failed") from exc


class CustomerWorkflowService:
    """Business logic service for customer tracking and messaging."""

    def __init__(self, backend: CustomerBackend) -> None:
        self.backend = backend

    def list_ticket_page(
        self,
        customer_id: str,
        page_size: int,
        cursor: CustomerHistoryCursor | None,
        filters: CustomerHistoryFilters,
    ) -> CustomerTicketListResponse:
        try:
            raw_tickets = self.backend.list_customer_tickets(
                customer_id, page_size, cursor, filters
            )
            if len(raw_tickets) > page_size + 1:
                raise CustomerHistoryDataError("history page exceeded bound")
            for ticket in raw_tickets:
                if ticket.get("customerId") != customer_id:
                    raise CustomerHistoryDataError("ticket ownership is invalid")
                ticket_id = ticket.get("id")
                if not isinstance(ticket_id, str) or not _TICKET_ID_PATTERN.fullmatch(ticket_id):
                    raise CustomerHistoryDataError("ticket reference is invalid")
                _timestamp_from_value(ticket.get("createdAt"))
            summaries: list[CustomerTicketSummary] = []
            for ticket in raw_tickets[:page_size]:
                created_at = _timestamp_from_value(ticket.get("createdAt"))
                updated_at = _timestamp_from_value(
                    ticket.get("updatedAt", ticket.get("createdAt"))
                )
                resolved_raw = ticket.get("resolvedAt")
                resolved_at = (
                    _timestamp_from_value(resolved_raw)
                    if resolved_raw is not None
                    else None
                )
                summary = CustomerTicketSummary(
                    complaintId=ticket.get("id"),
                    status=ticket.get("status"),
                    departmentId=ticket.get("departmentId"),
                    createdAt=_rfc3339(created_at),
                    updatedAt=_rfc3339(updated_at),
                    resolvedAt=_rfc3339(resolved_at) if resolved_at else None,
                )
                summaries.append(summary)
            ids = [summary.complaint_id for summary in summaries]
            if len(ids) != len(set(ids)):
                raise CustomerHistoryDataError("history page contains duplicate tickets")
            has_more = len(raw_tickets) > page_size
            next_cursor = (
                encode_customer_history_cursor(
                    CustomerHistoryCursor(
                        _timestamp_from_value(raw_tickets[page_size - 1]["createdAt"]),
                        raw_tickets[page_size - 1]["id"],
                        filters,
                    ),
                    customer_id,
                    filters,
                )
                if has_more
                else None
            )
            return CustomerTicketListResponse(
                tickets=summaries,
                nextCursor=next_cursor,
                hasMore=has_more,
            )
        except CustomerHistoryDataError:
            raise
        except PersistenceError:
            raise
        except Exception as exc:
            raise CustomerHistoryDataError("customer history projection failed") from exc

    def list_tickets(
        self,
        customer_id: str,
        page_size: int | None = None,
        cursor: CustomerHistoryCursor | None = None,
        filters: CustomerHistoryFilters | None = None,
    ) -> CustomerTicketListResponse | list[CustomerTicketSummary]:
        selected = filters or CustomerHistoryFilters()
        page = self.list_ticket_page(
            customer_id,
            page_size or CUSTOMER_HISTORY_DEFAULT_PAGE_SIZE,
            cursor,
            selected,
        )
        if page_size is None and cursor is None and filters is None:
            return page.tickets
        return page

    @staticmethod
    def _project_message(raw_message: dict[str, Any]) -> CustomerMessageItem:
        if not isinstance(raw_message, dict):
            raise CustomerHistoryDataError("message persistence is invalid")
        try:
            canonical = normalize_message_document(raw_message)
        except (TypeError, ValueError) as exc:
            raise CustomerHistoryDataError("message persistence is invalid") from exc
        if set(canonical) != {
            "id", "authorId", "authorRole", "body", "visibility", "createdAt"
        }:
            raise CustomerHistoryDataError("message persistence is invalid")
        if (
            not isinstance(canonical["id"], str)
            or not canonical["id"]
            or not isinstance(canonical["authorId"], str)
            or not canonical["authorId"]
            or canonical["visibility"] != "participants"
            or canonical["authorRole"] not in {"customer", "staff", "manager"}
            or not isinstance(canonical["body"], str)
            or not canonical["body"]
        ):
            raise CustomerHistoryDataError("message persistence is invalid")
        occurred_at = _require_canonical_timestamp(
            canonical["createdAt"], "message timestamp"
        )
        public_role = (
            "customer" if canonical["authorRole"] == "customer" else "support_team"
        )
        try:
            return CustomerMessageItem(
                senderRole=public_role,
                body=canonical["body"],
                createdAt=occurred_at,
            )
        except (TypeError, ValueError) as exc:
            raise CustomerHistoryDataError("message projection is invalid") from exc

    @staticmethod
    def _validate_ticket_persistence(
        raw_ticket: Any, customer_id: str, ticket_id: str
    ) -> dict[str, Any]:
        if not isinstance(raw_ticket, dict):
            raise CustomerHistoryDataError("ticket persistence is invalid")
        if (
            raw_ticket.get("id") != ticket_id
            or not _TICKET_ID_PATTERN.fullmatch(ticket_id)
            or raw_ticket.get("customerId") != customer_id
            or not isinstance(raw_ticket.get("complaintText"), str)
            or not raw_ticket.get("complaintText")
            or raw_ticket.get("inputLocale") not in {"en", "my"}
            or raw_ticket.get("status") not in CUSTOMER_HISTORY_STATUSES
            or (
                raw_ticket.get("departmentId") is not None
                and raw_ticket.get("departmentId") not in _PUBLIC_DEPARTMENTS
            )
        ):
            raise CustomerHistoryDataError("ticket persistence is invalid")
        required = {
            "id", "customerId", "complaintText", "inputLocale", "departmentId",
            "status", "createdAt", "updatedAt", "resolvedAt",
        }
        if not required.issubset(raw_ticket):
            raise CustomerHistoryDataError("ticket persistence is incomplete")
        created_at = _require_canonical_timestamp(raw_ticket["createdAt"], "createdAt")
        updated_at = _require_canonical_timestamp(raw_ticket["updatedAt"], "updatedAt")
        resolved_raw = raw_ticket["resolvedAt"]
        resolved_at = (
            _require_canonical_timestamp(resolved_raw, "resolvedAt")
            if resolved_raw is not None
            else None
        )
        created_dt = _timestamp_from_value(created_at)
        updated_dt = _timestamp_from_value(updated_at)
        resolved_dt = _timestamp_from_value(resolved_at) if resolved_at else None
        status = raw_ticket["status"]
        if updated_dt < created_dt:
            raise CustomerHistoryDataError("ticket timestamps are contradictory")
        if status in {"resolved", "closed"} and resolved_dt is None:
            raise CustomerHistoryDataError("resolved ticket is missing resolvedAt")
        if status not in {"resolved", "closed"} and resolved_dt is not None:
            raise CustomerHistoryDataError("unresolved ticket has resolvedAt")
        if resolved_dt is not None and (
            resolved_dt < created_dt or resolved_dt > updated_dt
        ):
            raise CustomerHistoryDataError("ticket timestamps are contradictory")
        if status != "submitted" and raw_ticket["departmentId"] is None:
            raise CustomerHistoryDataError("routed ticket is missing departmentId")
        internal_string_fields = {
            "assignedStaffId", "resolutionSummary", "manualReviewReason",
            "predictionModelVersion", "schemaVersion",
        }
        for field_name in internal_string_fields:
            if field_name in raw_ticket and raw_ticket[field_name] is not None and (
                not isinstance(raw_ticket[field_name], str) or not raw_ticket[field_name]
            ):
                raise CustomerHistoryDataError("ticket internal field is invalid")
        if "priority" in raw_ticket and raw_ticket["priority"] not in {
            "normal", "high", "urgent"
        }:
            raise CustomerHistoryDataError("ticket priority is invalid")
        if "predictedDepartmentId" in raw_ticket and (
            raw_ticket["predictedDepartmentId"] is not None
            and raw_ticket["predictedDepartmentId"] not in _PUBLIC_DEPARTMENTS
        ):
            raise CustomerHistoryDataError("ticket prediction is invalid")
        if "assignedDepartmentId" in raw_ticket and (
            raw_ticket["assignedDepartmentId"] is not None
            and raw_ticket["assignedDepartmentId"] not in _PUBLIC_DEPARTMENTS
        ):
            raise CustomerHistoryDataError("ticket assignment is invalid")
        if "predictionConfidence" in raw_ticket:
            confidence = raw_ticket["predictionConfidence"]
            if confidence is not None and (
                isinstance(confidence, bool)
                or not isinstance(confidence, (int, float))
                or not math.isfinite(float(confidence))
                or not 0.0 <= float(confidence) <= 1.0
            ):
                raise CustomerHistoryDataError("ticket confidence is invalid")
        if "routingSource" in raw_ticket and raw_ticket["routingSource"] not in {
            "model", "manual_review", "manager_override", "pending"
        }:
            raise CustomerHistoryDataError("ticket routing source is invalid")
        if "routingSource" in raw_ticket:
            routing_source = raw_ticket["routingSource"]
            department_id = raw_ticket["departmentId"]
            if routing_source == "pending" and (
                status != "submitted" or department_id is not None
            ):
                raise CustomerHistoryDataError("ticket routing state is invalid")
            if routing_source == "manual_review" and department_id is not None:
                raise CustomerHistoryDataError("ticket routing state is invalid")
            if routing_source in {"model", "manager_override"} and department_id is None:
                raise CustomerHistoryDataError("ticket routing state is invalid")
        if "escalated" in raw_ticket and type(raw_ticket["escalated"]) is not bool:
            raise CustomerHistoryDataError("ticket escalation state is invalid")
        if "detectedLanguage" in raw_ticket and raw_ticket["detectedLanguage"] not in {
            "en", "mixed", "unsupported"
        }:
            raise CustomerHistoryDataError("ticket language metadata is invalid")
        return {
            "id": ticket_id,
            "status": status,
            "complaintText": raw_ticket["complaintText"],
            "inputLocale": raw_ticket["inputLocale"],
            "departmentId": raw_ticket["departmentId"],
            "createdAt": created_at,
            "updatedAt": updated_at,
            "resolvedAt": resolved_at,
        }

    @staticmethod
    def _validate_feedback_persistence(
        raw_feedback: Any,
        ticket: dict[str, Any],
    ) -> dict[str, Any] | None:
        if raw_feedback is None:
            return None
        if not isinstance(raw_feedback, dict) or set(raw_feedback) != {
            "rating", "comments", "submittedAt"
        }:
            raise CustomerHistoryDataError("feedback persistence is invalid")
        if ticket["status"] not in {"resolved", "closed"}:
            raise CustomerHistoryDataError("feedback is not eligible for this ticket")
        rating = raw_feedback["rating"]
        if type(rating) is not int or not 1 <= rating <= 5:
            raise CustomerHistoryDataError("feedback rating is invalid")
        comments = raw_feedback["comments"]
        if comments is not None and not isinstance(comments, str):
            raise CustomerHistoryDataError("feedback comments are invalid")
        submitted_at = _require_canonical_timestamp(
            raw_feedback["submittedAt"], "feedback timestamp"
        )
        if _timestamp_from_value(submitted_at) < _timestamp_from_value(ticket["createdAt"]):
            raise CustomerHistoryDataError("feedback timestamp is contradictory")
        return {
            "rating": rating,
            "comments": comments,
            "submittedAt": submitted_at,
        }

    @staticmethod
    def _validate_event_persistence(
        raw_event: Any, ticket_id: str
    ) -> dict[str, Any]:
        if not isinstance(raw_event, dict):
            raise CustomerHistoryDataError("event persistence is invalid")
        required = {"type", "actorId", "actorRole", "fromValue", "toValue", "createdAt"}
        allowed = required | {
            "eventId", "ticketId", "reason", "predictionConfidence", "routingSource",
            "predictedDepartmentId",
        }
        if not required.issubset(raw_event) or set(raw_event) - allowed:
            raise CustomerHistoryDataError("event persistence is invalid")
        if "ticketId" in raw_event and raw_event["ticketId"] != ticket_id:
            raise CustomerHistoryDataError("event ticket binding is invalid")
        event_type = raw_event["type"]
        if event_type not in {
            "model_prediction", "manager_override", "status_transition", "staff_reply"
        }:
            raise CustomerHistoryDataError("event type is not customer-safe")
        if (
            not isinstance(raw_event["actorId"], str)
            or not raw_event["actorId"]
            or raw_event["actorRole"] not in {"customer", "staff", "manager", "system"}
            or (raw_event["fromValue"] is not None and not isinstance(raw_event["fromValue"], str))
            or (raw_event["toValue"] is not None and not isinstance(raw_event["toValue"], str))
        ):
            raise CustomerHistoryDataError("event persistence is invalid")
        _require_canonical_timestamp(raw_event["createdAt"], "event timestamp")
        if "reason" in raw_event and raw_event["reason"] is not None and not isinstance(
            raw_event["reason"], str
        ):
            raise CustomerHistoryDataError("event reason is invalid")
        if "predictionConfidence" in raw_event:
            confidence = raw_event["predictionConfidence"]
            if confidence is not None and (
                isinstance(confidence, bool)
                or not isinstance(confidence, (int, float))
                or not math.isfinite(float(confidence))
                or not 0.0 <= float(confidence) <= 1.0
            ):
                raise CustomerHistoryDataError("event confidence is invalid")
        if "routingSource" in raw_event and raw_event["routingSource"] not in {
            "model", "manual_review", "manager_override", "pending"
        }:
            raise CustomerHistoryDataError("event routing source is invalid")
        if "predictedDepartmentId" in raw_event and (
            raw_event["predictedDepartmentId"] is not None
            and raw_event["predictedDepartmentId"] not in _PUBLIC_DEPARTMENTS
        ):
            raise CustomerHistoryDataError("event prediction is invalid")
        if "eventId" in raw_event and (
            not isinstance(raw_event["eventId"], str) or not raw_event["eventId"]
        ):
            raise CustomerHistoryDataError("event persistence is invalid")
        if event_type == "manager_override":
            if raw_event["actorRole"] != "manager" or raw_event["toValue"] not in _PUBLIC_DEPARTMENTS:
                raise CustomerHistoryDataError("event department is invalid")
            if raw_event["fromValue"] is not None and raw_event["fromValue"] not in _PUBLIC_DEPARTMENTS:
                raise CustomerHistoryDataError("event department is invalid")
        elif event_type == "model_prediction":
            if raw_event["actorRole"] != "system":
                raise CustomerHistoryDataError("event actor is invalid")
            if raw_event["toValue"] is not None and raw_event["toValue"] not in _PUBLIC_DEPARTMENTS:
                raise CustomerHistoryDataError("event department is invalid")
            if raw_event["fromValue"] is not None and raw_event["fromValue"] not in _PUBLIC_DEPARTMENTS:
                raise CustomerHistoryDataError("event department is invalid")
        elif event_type == "status_transition":
            if raw_event["actorRole"] not in {"staff", "manager"}:
                raise CustomerHistoryDataError("event actor is invalid")
            if raw_event["toValue"] not in CUSTOMER_HISTORY_STATUSES:
                raise CustomerHistoryDataError("event status is invalid")
            if raw_event["fromValue"] is not None and raw_event["fromValue"] not in CUSTOMER_HISTORY_STATUSES:
                raise CustomerHistoryDataError("event status is invalid")
        elif event_type == "staff_reply":
            if raw_event["actorRole"] != "staff" or not isinstance(raw_event["toValue"], str) or not raw_event["toValue"]:
                raise CustomerHistoryDataError("event persistence is invalid")
        return raw_event

    @staticmethod
    def _event_timeline_item(raw_event: dict[str, Any]) -> dict[str, Any] | None:
        event_type = raw_event["type"]
        occurred_at = _require_canonical_timestamp(raw_event["createdAt"], "event timestamp")

        public_type: str | None = None
        department_id: str | None = None
        rank = 10
        if event_type in {"model_prediction", "manager_override"}:
            candidate_department = raw_event.get("toValue")
            if candidate_department not in _PUBLIC_DEPARTMENTS:
                return None
            public_type = "assigned_to_team"
            department_id = candidate_department
            rank = 20
        elif event_type == "status_transition":
            status = raw_event.get("toValue")
            public_type = _TIMELINE_STATUS_TYPES.get(status)
            rank = _TIMELINE_STATUS_RANKS.get(status, 30)
        elif event_type == "staff_reply":
            public_type = "team_replied"
            rank = 40
        else:
            raise CustomerHistoryDataError("event type is not customer-safe")

        if public_type is None:
            return None

        return {
            "type": public_type,
            "occurredAt": occurred_at,
            "departmentId": department_id,
            "rank": rank,
        }

    def _project_timeline(
        self,
        raw_ticket: dict[str, Any],
        messages: list[CustomerMessageItem],
        raw_events: list[dict[str, Any]],
    ) -> list[CustomerTimelineItem]:
        candidates: list[dict[str, Any]] = []
        created_at = raw_ticket["createdAt"]
        candidates.append(
            {
                "type": "complaint_received",
                "occurredAt": created_at,
                "departmentId": None,
                "rank": 0,
            }
        )

        for event in raw_events:
            item = self._event_timeline_item(event)
            if item:
                candidates.append(item)

        for message in messages:
            candidates.append(
                {
                    "type": "customer_replied"
                    if message.sender_role == "customer"
                    else "team_replied",
                    "occurredAt": message.created_at,
                    "departmentId": None,
                    "rank": 40,
                }
            )

        candidates.sort(key=_timeline_sort_key)
        deduplicated: list[dict[str, Any]] = []
        for candidate in candidates:
            duplicate = any(
                prior["type"] == candidate["type"]
                and prior["occurredAt"] == candidate["occurredAt"]
                for prior in deduplicated
            )
            if not duplicate:
                deduplicated.append(candidate)

        return [
            CustomerTimelineItem(
                type=item["type"],
                occurredAt=item["occurredAt"],
                departmentId=item["departmentId"],
            )
            for item in deduplicated
        ]

    def get_ticket_detail(
        self, customer_id: str, ticket_id: str
    ) -> CustomerTicketDetail:
        raw_ticket = self.backend.get_customer_ticket(customer_id, ticket_id)
        if raw_ticket is None:
            raise TicketNotFound("Ticket not found.")
        ticket = self._validate_ticket_persistence(raw_ticket, customer_id, ticket_id)
        messages_formatted = [
            self._project_message(message)
            for message in self.backend.get_ticket_messages(ticket_id)
        ]
        raw_events = self.backend.get_ticket_events(ticket_id)
        validated_events = [
            self._validate_event_persistence(event, ticket_id) for event in raw_events
        ]
        timeline = self._project_timeline(ticket, messages_formatted, validated_events)
        feedback = self._validate_feedback_persistence(raw_ticket.get("feedback"), ticket)
        try:
            return CustomerTicketDetail(
                id=ticket["id"],
                status=ticket["status"],
                complaintText=ticket["complaintText"],
                inputLocale=ticket["inputLocale"],
                departmentId=ticket["departmentId"],
                createdAt=ticket["createdAt"],
                updatedAt=ticket["updatedAt"],
                resolvedAt=ticket["resolvedAt"],
                messages=messages_formatted,
                timeline=timeline,
                feedback=feedback,
            )
        except (TypeError, ValueError) as exc:
            raise CustomerHistoryDataError("customer detail projection is invalid") from exc

    def ensure_owned_ticket(self, customer_id: str, ticket_id: str) -> None:
        if not self.backend.get_customer_ticket(customer_id, ticket_id):
            raise TicketNotFound("Ticket not found.")

    def send_message(
        self,
        customer_id: str,
        ticket_id: str,
        req: CustomerMessageRequest,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        detail = self.get_ticket_detail(customer_id, ticket_id)
        if detail.status in ("closed",):
            raise InvalidTicketState("Cannot add message to closed ticket.")

        raw_msg = req.message_text
        clean_text = redact_pii(raw_msg.strip())
        if not clean_text:
            raise ValueError("Message text cannot be empty.")

        now_dt = now or datetime.now(timezone.utc)
        return self.backend.add_customer_message(
            customer_id=customer_id,
            ticket_id=ticket_id,
            message_text=clean_text,
            created_at=now_dt,
            action_id=req.action_id,
            request_text=raw_msg,
        )

    def submit_feedback(
        self,
        customer_id: str,
        ticket_id: str,
        req: CustomerFeedbackRequest,
        now: datetime | None = None,
    ) -> CustomerFeedbackResponse:
        detail = self.get_ticket_detail(customer_id, ticket_id)
        if detail.status not in ("resolved", "closed"):
            raise InvalidTicketState(
                "Feedback can only be submitted for resolved or closed tickets."
            )

        if req.rating < 1 or req.rating > 5:
            raise ValueError("Rating must be between 1 and 5.")

        clean_comments = redact_pii(req.comments.strip()) if req.comments else ""
        now_dt = now or datetime.now(timezone.utc)

        fb_doc = self.backend.save_ticket_feedback(
            customer_id=customer_id,
            ticket_id=ticket_id,
            rating=req.rating,
            comments=clean_comments,
            created_at=now_dt,
            action_id=req.action_id,
        )

        return CustomerFeedbackResponse(
            ticketId=ticket_id,
            feedbackId=fb_doc["id"],
            status="feedback_submitted",
        )
