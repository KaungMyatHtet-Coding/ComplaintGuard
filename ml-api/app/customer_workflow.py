"""ComplaintGuard Day 15 Customer Workflow Backend Service."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from app.schemas import (
    CustomerFeedbackRequest,
    CustomerFeedbackResponse,
    CustomerMessageRequest,
    CustomerTicketDetail,
    CustomerTicketSummary,
)
from app.ticketing import redact_sensitive_data as redact_pii


class CustomerWorkflowError(Exception):
    """Base exception for customer workflow operations."""


class TicketAccessDenied(CustomerWorkflowError):
    """Raised when customer attempts to access another user's ticket."""


class TicketNotFound(CustomerWorkflowError):
    """Raised when ticket ID does not exist."""


class InvalidTicketState(CustomerWorkflowError):
    """Raised when operation is invalid for current ticket state."""


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
    def get_customer_ticket(self, customer_id: str, ticket_id: str) -> dict[str, Any] | None:
        """Get ticket dict if owned by customer_id, else None if not found or denied."""

    @abstractmethod
    def get_ticket_raw(self, ticket_id: str) -> dict[str, Any] | None:
        """Get ticket dict regardless of owner to distinguish 404 from 403."""

    @abstractmethod
    def get_ticket_messages(self, ticket_id: str) -> list[dict[str, Any]]:
        """Get all message thread items for a ticket."""

    @abstractmethod
    def add_customer_message(
        self,
        customer_id: str,
        ticket_id: str,
        message_text: str,
        created_at: datetime,
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
    ) -> dict[str, Any]:
        """Save feedback rating/comments for a resolved ticket."""


class InMemoryCustomerBackend(CustomerBackend):
    """In-memory mock backend for testing and development."""

    def __init__(self, initial_tickets: list[dict[str, Any]] | None = None) -> None:
        self.tickets: dict[str, dict[str, Any]] = {}
        self.messages: dict[str, list[dict[str, Any]]] = {}
        self.feedbacks: dict[str, dict[str, Any]] = {}

        if initial_tickets:
            for t in initial_tickets:
                tid = t["id"]
                self.tickets[tid] = dict(t)
                self.messages[tid] = t.get("messages", [])

    def list_customer_tickets(self, customer_id: str) -> list[dict[str, Any]]:
        res = [t for t in self.tickets.values() if t.get("customerId") == customer_id]
        res.sort(key=lambda x: x.get("createdAt", ""), reverse=True)
        return res

    def get_customer_ticket(self, customer_id: str, ticket_id: str) -> dict[str, Any] | None:
        t = self.tickets.get(ticket_id)
        if not t or t.get("customerId") != customer_id:
            return None
        return t

    def get_ticket_raw(self, ticket_id: str) -> dict[str, Any] | None:
        return self.tickets.get(ticket_id)

    def get_ticket_messages(self, ticket_id: str) -> list[dict[str, Any]]:
        msgs = self.messages.get(ticket_id, [])
        msgs_sorted = sorted(msgs, key=lambda x: x.get("createdAt", ""))
        return msgs_sorted

    def add_customer_message(
        self,
        customer_id: str,
        ticket_id: str,
        message_text: str,
        created_at: datetime,
    ) -> dict[str, Any]:
        msg_id = f"msg_{len(self.messages.get(ticket_id, [])) + 1}"
        iso_str = created_at.isoformat()
        msg_doc = {
            "id": msg_id,
            "senderId": customer_id,
            "senderRole": "customer",
            "text": message_text,
            "createdAt": iso_str,
        }
        if ticket_id not in self.messages:
            self.messages[ticket_id] = []
        self.messages[ticket_id].append(msg_doc)

        if ticket_id in self.tickets:
            self.tickets[ticket_id]["updatedAt"] = iso_str

        return msg_doc

    def save_ticket_feedback(
        self,
        customer_id: str,
        ticket_id: str,
        rating: int,
        comments: str,
        created_at: datetime,
    ) -> dict[str, Any]:
        fb_id = f"fb_{ticket_id}"
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
                import firebase_admin
                from firebase_admin import firestore

                try:
                    firebase_admin.get_app()
                except ValueError:
                    firebase_admin.initialize_app()
                self.db = firestore.client()
            except Exception as exc:
                from app.ticketing import PersistenceError
                raise PersistenceError("Firebase Admin is not configured") from exc

    def list_customer_tickets(self, customer_id: str) -> list[dict[str, Any]]:
        query = (
            self.db.collection("complaints")
            .where("customerId", "==", customer_id)
            .order_by("createdAt", direction="DESCENDING")
        )
        docs = query.stream()
        results = []
        for d in docs:
            data = d.to_dict()
            data["id"] = d.id
            results.append(data)
        return results

    def get_customer_ticket(self, customer_id: str, ticket_id: str) -> dict[str, Any] | None:
        doc_ref = self.db.collection("complaints").document(ticket_id)
        snapshot = doc_ref.get()
        if not snapshot.exists:
            return None
        data = snapshot.to_dict()
        if data.get("customerId") != customer_id:
            return None
        data["id"] = snapshot.id
        return data

    def get_ticket_raw(self, ticket_id: str) -> dict[str, Any] | None:
        doc_ref = self.db.collection("complaints").document(ticket_id)
        snapshot = doc_ref.get()
        if not snapshot.exists:
            return None
        data = snapshot.to_dict()
        data["id"] = snapshot.id
        return data

    def get_ticket_messages(self, ticket_id: str) -> list[dict[str, Any]]:
        msgs_ref = (
            self.db.collection("complaints")
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

    def add_customer_message(
        self,
        customer_id: str,
        ticket_id: str,
        message_text: str,
        created_at: datetime,
    ) -> dict[str, Any]:
        doc_ref = self.db.collection("complaints").document(ticket_id)
        msg_ref = doc_ref.collection("messages").document()
        msg_data = {
            "senderId": customer_id,
            "senderRole": "customer",
            "text": message_text,
            "createdAt": created_at,
        }
        msg_ref.set(msg_data)
        doc_ref.update({"updatedAt": created_at})
        msg_data["id"] = msg_ref.id
        msg_data["createdAt"] = created_at.isoformat()
        return msg_data

    def save_ticket_feedback(
        self,
        customer_id: str,
        ticket_id: str,
        rating: int,
        comments: str,
        created_at: datetime,
    ) -> dict[str, Any]:
        fb_ref = self.db.collection("feedback").document(f"fb_{ticket_id}")
        fb_data = {
            "ticketId": ticket_id,
            "customerId": customer_id,
            "rating": rating,
            "comments": comments,
            "createdAt": created_at,
        }
        fb_ref.set(fb_data)
        self.db.collection("complaints").document(ticket_id).update(
            {
                "feedback": {
                    "rating": rating,
                    "comments": comments,
                    "submittedAt": created_at.isoformat(),
                }
            }
        )
        fb_data["id"] = fb_ref.id
        fb_data["createdAt"] = created_at.isoformat()
        return fb_data


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
                    predictedDepartmentId=t.get("predictedDepartmentId") or t.get("departmentId"),
                    assignedDepartmentId=t.get("assignedDepartmentId") or t.get("departmentId"),
                    createdAt=str(t.get("createdAt", "")),
                    updatedAt=str(t.get("updatedAt", t.get("createdAt", ""))),
                    summaryText=summary_text,
                )
            )
        return summaries

    def get_ticket_detail(self, customer_id: str, ticket_id: str) -> CustomerTicketDetail:
        raw_ticket = self.backend.get_customer_ticket(customer_id, ticket_id)
        if not raw_ticket:
            raw_check = self.backend.get_ticket_raw(ticket_id)
            if raw_check:
                raise TicketAccessDenied("Access denied to requested ticket.")
            raise TicketNotFound("Ticket not found.")

        messages_raw = self.backend.get_ticket_messages(ticket_id)
        messages_formatted = []
        for m in messages_raw:
            messages_formatted.append(
                {
                    "id": m.get("id", ""),
                    "senderId": m.get("senderId", ""),
                    "senderRole": m.get("senderRole", "staff"),
                    "text": m.get("text", ""),
                    "createdAt": str(m.get("createdAt", "")),
                }
            )

        feedback_dict = raw_ticket.get("feedback")

        return CustomerTicketDetail(
            id=raw_ticket["id"],
            customerId=raw_ticket.get("customerId", customer_id),
            status=raw_ticket.get("status", "submitted"),
            complaintText=raw_ticket.get("complaintText", raw_ticket.get("originalText", "")),
            inputLocale=raw_ticket.get("inputLocale", "en"),
            predictedDepartmentId=raw_ticket.get("predictedDepartmentId") or raw_ticket.get("departmentId"),
            assignedDepartmentId=raw_ticket.get("assignedDepartmentId") or raw_ticket.get("departmentId"),
            priority=raw_ticket.get("priority", "medium"),
            createdAt=str(raw_ticket.get("createdAt", "")),
            updatedAt=str(raw_ticket.get("updatedAt", raw_ticket.get("createdAt", ""))),
            resolvedAt=str(raw_ticket["resolvedAt"]) if raw_ticket.get("resolvedAt") else None,
            messages=messages_formatted,
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

        clean_text = redact_pii(req.message_text.strip())
        if not clean_text:
            raise ValueError("Message text cannot be empty.")

        now_dt = now or datetime.now(timezone.utc)
        return self.backend.add_customer_message(
            customer_id=customer_id,
            ticket_id=ticket_id,
            message_text=clean_text,
            created_at=now_dt,
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
            raise InvalidTicketState("Feedback can only be submitted for resolved or closed tickets.")

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
        )

        return CustomerFeedbackResponse(
            ticketId=ticket_id,
            feedbackId=fb_doc["id"],
            status="feedback_submitted",
        )
