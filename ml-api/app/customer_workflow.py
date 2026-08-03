from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from app.schemas import LABELS
from app.ticketing import PersistenceError


class CustomerWorkflowError(Exception):
    """Base exception for customer workflow domain errors."""


class TicketNotFound(CustomerWorkflowError):
    """Raised when a ticket is not found in customer backend."""


class TicketAccessDenied(CustomerWorkflowError):
    """Raised when a customer tries to access another customer's ticket."""


class InvalidTicketState(CustomerWorkflowError):
    """Raised when an operation is invalid for the ticket's current state."""


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sample_dev_tickets() -> list[dict[str, Any]]:
    now = _iso_now()
    return [
        {
            "id": "cg_ticket_cust1",
            "customerId": "demo_customer_uid",
            "status": "triaged",
            "complaintText": "I was charged an unknown monthly fee and my card was declined.",
            "inputLocale": "en",
            "predictedDepartmentId": "account_support",
            "assignedDepartmentId": "account_support",
            "priority": "normal",
            "createdAt": now,
            "updatedAt": now,
            "messages": [
                {
                    "messageId": "msg_001",
                    "senderId": "demo_customer_uid",
                    "senderRole": "customer",
                    "text": "Please check why my card was declined.",
                    "createdAt": now,
                }
            ],
        },
        {
            "id": "cg_ticket_cust2",
            "customerId": "demo_customer_uid",
            "status": "resolved",
            "complaintText": "Loan interest rate calculation is confusing and higher than quoted.",
            "inputLocale": "en",
            "predictedDepartmentId": "loan_credit",
            "assignedDepartmentId": "loan_credit",
            "priority": "high",
            "createdAt": now,
            "updatedAt": now,
            "resolvedAt": now,
            "messages": [],
            "rating": 5,
            "feedbackComments": "Resolution was fast and clear.",
        },
    ]


class CustomerBackend(ABC):
    @abstractmethod
    def list_tickets(self, customer_id: str) -> list[dict[str, Any]]:
        pass

    @abstractmethod
    def get_ticket_detail(self, ticket_id: str, customer_id: str) -> dict[str, Any]:
        pass

    @abstractmethod
    def add_customer_message(
        self, ticket_id: str, customer_id: str, text: str
    ) -> dict[str, Any]:
        pass

    @abstractmethod
    def submit_feedback(
        self, ticket_id: str, customer_id: str, rating: int, comments: str | None
    ) -> dict[str, Any]:
        pass


class FirebaseAdminCustomerBackend(CustomerBackend):
    def __init__(self, db_client: Any | None = None) -> None:
        if db_client is not None:
            self._db = db_client
            return
        try:
            import firebase_admin
            from firebase_admin import firestore

            if not firebase_admin._apps:
                firebase_admin.initialize_app()
            self._db = firestore.client()
        except Exception as exc:
            raise PersistenceError("Firebase Admin SDK initialization failed.") from exc

    def list_tickets(self, customer_id: str) -> list[dict[str, Any]]:
        try:
            query = (
                self._db.collection("tickets")
                .where("customerId", "==", customer_id)
                .order_by("createdAt", direction="DESCENDING")
            )
            docs = query.get()
            results = []
            for doc in docs:
                data = doc.to_dict() or {}
                data["id"] = doc.id
                results.append(data)
            return results
        except Exception as exc:
            raise PersistenceError("Failed to query customer tickets from Firestore.") from exc

    def get_ticket_detail(self, ticket_id: str, customer_id: str) -> dict[str, Any]:
        try:
            doc_ref = self._db.collection("tickets").document(ticket_id)
            doc = doc_ref.get()
            if not doc.exists:
                raise TicketNotFound(f"Ticket {ticket_id} not found.")
            data = doc.to_dict() or {}
            data["id"] = doc.id
            if data.get("customerId") != customer_id:
                raise TicketAccessDenied("Access denied to ticket.")
            return data
        except (TicketNotFound, TicketAccessDenied):
            raise
        except Exception as exc:
            raise PersistenceError("Failed to fetch ticket detail from Firestore.") from exc

    def add_customer_message(
        self, ticket_id: str, customer_id: str, text: str
    ) -> dict[str, Any]:
        try:
            doc_ref = self._db.collection("tickets").document(ticket_id)
            doc = doc_ref.get()
            if not doc.exists:
                raise TicketNotFound(f"Ticket {ticket_id} not found.")
            data = doc.to_dict() or {}
            if data.get("customerId") != customer_id:
                raise TicketAccessDenied("Access denied to ticket.")
            if data.get("status") == "resolved":
                raise InvalidTicketState("Cannot add message to resolved ticket.")

            msg_id = f"msg_{int(datetime.now(timezone.utc).timestamp() * 1000)}"
            now = _iso_now()
            new_msg = {
                "messageId": msg_id,
                "senderId": customer_id,
                "senderRole": "customer",
                "text": text,
                "createdAt": now,
            }
            messages = list(data.get("messages", []))
            messages.append(new_msg)

            doc_ref.update({"messages": messages, "updatedAt": now})
            return new_msg
        except (TicketNotFound, TicketAccessDenied, InvalidTicketState):
            raise
        except Exception as exc:
            raise PersistenceError("Failed to add customer message in Firestore.") from exc

    def submit_feedback(
        self, ticket_id: str, customer_id: str, rating: int, comments: str | None
    ) -> dict[str, Any]:
        try:
            doc_ref = self._db.collection("tickets").document(ticket_id)
            doc = doc_ref.get()
            if not doc.exists:
                raise TicketNotFound(f"Ticket {ticket_id} not found.")
            data = doc.to_dict() or {}
            if data.get("customerId") != customer_id:
                raise TicketAccessDenied("Access denied to ticket.")
            if data.get("status") != "resolved":
                raise InvalidTicketState("Cannot rate an unresolved ticket.")

            now = _iso_now()
            updates: dict[str, Any] = {"rating": rating, "updatedAt": now}
            if comments:
                updates["feedbackComments"] = comments

            doc_ref.update(updates)
            return {"ticketId": ticket_id, "rating": rating, "submittedAt": now}
        except (TicketNotFound, TicketAccessDenied, InvalidTicketState):
            raise
        except Exception as exc:
            raise PersistenceError("Failed to submit feedback in Firestore.") from exc


class InMemoryCustomerBackend(CustomerBackend):
    def __init__(self, initial_tickets: list[dict[str, Any]] | None = None) -> None:
        self._tickets: dict[str, dict[str, Any]] = {}
        for t in initial_tickets or []:
            self._tickets[t["id"]] = dict(t)

    def list_tickets(self, customer_id: str) -> list[dict[str, Any]]:
        matched = [
            dict(t) for t in self._tickets.values() if t.get("customerId") == customer_id
        ]
        return sorted(matched, key=lambda x: x.get("createdAt", ""), reverse=True)

    def get_ticket_detail(self, ticket_id: str, customer_id: str) -> dict[str, Any]:
        if ticket_id not in self._tickets:
            raise TicketNotFound(f"Ticket {ticket_id} not found.")
        data = self._tickets[ticket_id]
        if data.get("customerId") != customer_id:
            raise TicketAccessDenied("Access denied to ticket.")
        return dict(data)

    def add_customer_message(
        self, ticket_id: str, customer_id: str, text: str
    ) -> dict[str, Any]:
        if ticket_id not in self._tickets:
            raise TicketNotFound(f"Ticket {ticket_id} not found.")
        data = self._tickets[ticket_id]
        if data.get("customerId") != customer_id:
            raise TicketAccessDenied("Access denied to ticket.")
        if data.get("status") == "resolved":
            raise InvalidTicketState("Cannot add message to resolved ticket.")

        msg_id = f"msg_{int(datetime.now(timezone.utc).timestamp() * 1000)}"
        now = _iso_now()
        new_msg = {
            "messageId": msg_id,
            "senderId": customer_id,
            "senderRole": "customer",
            "text": text,
            "createdAt": now,
        }
        messages = list(data.get("messages", []))
        messages.append(new_msg)
        data["messages"] = messages
        data["updatedAt"] = now
        return new_msg

    def submit_feedback(
        self, ticket_id: str, customer_id: str, rating: int, comments: str | None
    ) -> dict[str, Any]:
        if ticket_id not in self._tickets:
            raise TicketNotFound(f"Ticket {ticket_id} not found.")
        data = self._tickets[ticket_id]
        if data.get("customerId") != customer_id:
            raise TicketAccessDenied("Access denied to ticket.")
        if data.get("status") != "resolved":
            raise InvalidTicketState("Cannot rate an unresolved ticket.")

        now = _iso_now()
        data["rating"] = rating
        if comments:
            data["feedbackComments"] = comments
        data["updatedAt"] = now
        return {"ticketId": ticket_id, "rating": rating, "submittedAt": now}


class CustomerWorkflowService:
    def __init__(self, backend: CustomerBackend) -> None:
        self._backend = backend

    def list_tickets(self, customer_id: str) -> list[dict[str, Any]]:
        return self._backend.list_tickets(customer_id)

    def get_ticket_detail(self, ticket_id: str, customer_id: str) -> dict[str, Any]:
        return self._backend.get_ticket_detail(ticket_id, customer_id)

    def add_customer_message(
        self, ticket_id: str, customer_id: str, text: str
    ) -> dict[str, Any]:
        return self._backend.add_customer_message(ticket_id, customer_id, text)

    def submit_feedback(
        self, ticket_id: str, customer_id: str, rating: int, comments: str | None
    ) -> dict[str, Any]:
        return self._backend.submit_feedback(ticket_id, customer_id, rating, comments)
