"""ComplaintGuard Day 15 Customer Workflow Backend Service."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from app.message_schema import normalize_message_document
from app.schemas import (
    CustomerFeedbackRequest,
    CustomerFeedbackResponse,
    CustomerMessageItem,
    CustomerMessageRequest,
    CustomerTimelineItem,
    CustomerTicketDetail,
    CustomerTicketSummary,
)
from app.ticketing import redact_sensitive_data as redact_pii


_PUBLIC_DEPARTMENTS = frozenset(
    {
        "transfer_payment",
        "account_support",
        "card_atm",
        "fraud_security",
        "loan_credit",
        "general_support",
    }
)
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


def _timestamp_text(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str) and value.strip():
        return value
    return None


def _timeline_sort_key(item: dict[str, Any]) -> tuple[datetime, int, str]:
    occurred_at = item["occurredAt"].replace("Z", "+00:00")
    parsed = datetime.fromisoformat(occurred_at)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed, int(item.get("rank", 0)), item["type"]


def _is_timeline_timestamp(value: str) -> bool:
    try:
        _timeline_sort_key({"occurredAt": value, "rank": 0, "type": "_"})
    except (TypeError, ValueError):
        return False
    return True


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
    def list_customer_tickets(self, customer_id: str) -> list[dict[str, Any]]:
        """List all tickets owned by customer_id."""

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

    def list_customer_tickets(self, customer_id: str) -> list[dict[str, Any]]:
        res = [t for t in self.tickets.values() if t.get("customerId") == customer_id]
        res.sort(key=lambda x: x.get("createdAt", ""), reverse=True)
        return res

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
        msgs_sorted = sorted(msgs, key=lambda x: x.get("createdAt", ""))
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
    ) -> dict[str, Any]:
        key = (ticket_id, f"message:{action_id}")
        if key in self.actions:
            return dict(self.actions[key])
        msg_id = action_id
        iso_str = created_at.isoformat()
        msg_doc = {
            "id": msg_id,
            "authorId": customer_id,
            "authorRole": "customer",
            "body": message_text,
            "visibility": "participants",
            "createdAt": iso_str,
        }
        if ticket_id not in self.messages:
            self.messages[ticket_id] = []
        self.messages[ticket_id].append(msg_doc)
        result = {
            "senderRole": "customer",
            "body": message_text,
            "createdAt": iso_str,
        }
        self.actions[key] = dict(result)

        if ticket_id in self.tickets:
            self.tickets[ticket_id]["updatedAt"] = iso_str

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
        iso_str = created_at.isoformat()
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

    def __init__(self, db: Any = None) -> None:
        if db is not None:
            self.db = db
        else:
            try:
                from app.ticketing import firebase_admin_clients

                _, self.db, _ = firebase_admin_clients()
            except Exception as exc:
                from app.ticketing import PersistenceError

                raise PersistenceError("Firebase Admin is not configured") from exc

    def list_customer_tickets(self, customer_id: str) -> list[dict[str, Any]]:
        from google.cloud.firestore_v1.base_query import FieldFilter

        query = (
            self.db.collection("tickets")
            .where(filter=FieldFilter("customerId", "==", customer_id))
            .order_by("createdAt", direction="DESCENDING")
        )
        docs = query.stream()
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
        )
        results = []
        for d in msgs_ref.stream():
            data = d.to_dict()
            data["id"] = d.id
            results.append(data)
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
    ) -> dict[str, Any]:
        from app.ticketing import PersistenceError, run_firestore_transaction

        doc_ref = self.db.collection("tickets").document(ticket_id)
        msg_ref = doc_ref.collection("messages").document(action_id)
        action_ref = doc_ref.collection("actions").document(f"message_{action_id}")
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
            "createdAt": created_at.isoformat(),
        }
        try:

            def operation(transaction: Any) -> dict[str, Any]:
                action_snapshot = next(transaction.get(action_ref))
                if action_snapshot.exists:
                    return action_snapshot.to_dict()["result"]
                transaction.set(msg_ref, msg_data)
                transaction.update(doc_ref, {"updatedAt": created_at})
                transaction.set(
                    action_ref, {"type": "customer_message", "result": result}
                )
                return result

            return run_firestore_transaction(self.db, operation)
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

    def list_tickets(self, customer_id: str) -> list[CustomerTicketSummary]:
        raw_tickets = self.backend.list_customer_tickets(customer_id)
        summaries = []
        for t in raw_tickets:
            summary_text = t.get("complaintText", t.get("originalText", ""))[:120]
            summaries.append(
                CustomerTicketSummary(
                    id=t["id"],
                    status=t.get("status", "submitted"),
                    priority=t.get("priority", "normal"),
                    departmentId=t.get("departmentId"),
                    createdAt=str(t.get("createdAt", "")),
                    updatedAt=str(t.get("updatedAt", t.get("createdAt", ""))),
                    resolvedAt=str(t["resolvedAt"])
                    if t.get("resolvedAt")
                    else None,
                    summaryText=summary_text,
                )
            )
        return summaries

    @staticmethod
    def _project_message(raw_message: dict[str, Any]) -> CustomerMessageItem:
        canonical = normalize_message_document(raw_message)
        occurred_at = _timestamp_text(canonical.get("createdAt"))
        if not occurred_at or not _is_timeline_timestamp(occurred_at):
            raise ValueError("message is missing a valid timestamp")
        author_role = canonical.get("authorRole")
        if author_role == "customer":
            public_role = "customer"
        elif author_role in {"staff", "manager"}:
            public_role = "support_team"
        else:
            raise ValueError("message has an unsupported author role")
        if canonical.get("visibility") != "participants":
            raise ValueError("message is not participant-visible")
        body = canonical.get("body")
        if not isinstance(body, str):
            raise ValueError("message has an invalid body")
        return CustomerMessageItem(
            senderRole=public_role,
            body=body,
            createdAt=occurred_at,
        )

    @staticmethod
    def _event_timeline_item(raw_event: dict[str, Any]) -> dict[str, Any] | None:
        event_type = raw_event.get("type")
        occurred_at = _timestamp_text(raw_event.get("createdAt"))
        if not occurred_at or not _is_timeline_timestamp(occurred_at):
            return None

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
            return None

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
        created_at = _timestamp_text(raw_ticket.get("createdAt"))
        if created_at and _is_timeline_timestamp(created_at):
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
            if _is_timeline_timestamp(message.created_at):
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
        if not raw_ticket:
            raise TicketNotFound("Ticket not found.")

        messages_raw = self.backend.get_ticket_messages(ticket_id)
        messages_formatted: list[CustomerMessageItem] = []
        for m in messages_raw:
            messages_formatted.append(self._project_message(m))

        timeline = self._project_timeline(
            raw_ticket,
            messages_formatted,
            self.backend.get_ticket_events(ticket_id),
        )

        feedback_dict = raw_ticket.get("feedback")
        if feedback_dict:
            feedback_dict = dict(feedback_dict)
            feedback_dict["submittedAt"] = str(feedback_dict["submittedAt"])

        return CustomerTicketDetail(
            id=raw_ticket["id"],
            status=raw_ticket.get("status", "submitted"),
            complaintText=raw_ticket.get(
                "complaintText", raw_ticket.get("originalText", "")
            ),
            inputLocale=raw_ticket.get("inputLocale", "en"),
            priority=raw_ticket.get("priority", "normal"),
            departmentId=raw_ticket.get("departmentId"),
            createdAt=str(raw_ticket.get("createdAt", "")),
            updatedAt=str(raw_ticket.get("updatedAt", raw_ticket.get("createdAt", ""))),
            resolvedAt=str(raw_ticket["resolvedAt"])
            if raw_ticket.get("resolvedAt")
            else None,
            messages=messages_formatted,
            timeline=timeline,
            feedback=feedback_dict,
        )

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

        raw_msg = getattr(req, "text", "") or getattr(req, "message_text", "")
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
