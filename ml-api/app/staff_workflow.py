"""Department-scoped trusted staff workflow and Firestore adapter."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal, Protocol

from app.message_schema import normalize_message_document
from app.schemas import DepartmentId
from app.ticketing import (
    DEPARTMENT_IDS,
    AuthenticationError,
    FirebaseAdminTicketBackend,
    PermissionError,
    PersistenceError,
    redact_sensitive_data,
    run_firestore_transaction,
)

StaffStatus = Literal[
    "submitted", "triaged", "in_progress", "awaiting_customer", "resolved", "closed"
]
RequestType = Literal["request_reassignment", "request_escalation"]

ALLOWED_STAFF_TRANSITIONS: dict[str, frozenset[str]] = {
    "triaged": frozenset({"in_progress"}),
    "in_progress": frozenset({"awaiting_customer", "resolved"}),
    "awaiting_customer": frozenset({"in_progress"}),
}


class StaffTicketNotFound(RuntimeError):
    """Ticket is absent or outside the authenticated department boundary."""


class InvalidTransition(RuntimeError):
    """Requested staff transition is not permitted."""


@dataclass(frozen=True)
class StaffActor:
    uid: str
    department_id: DepartmentId


@dataclass(frozen=True)
class MutationResult:
    ticket_id: str
    action_id: str
    status: StaffStatus
    duplicate: bool


class StaffBackend(Protocol):
    def verify_id_token(self, token: str) -> str: ...

    def get_user_profile(self, uid: str) -> dict[str, Any] | None: ...

    def list_department_tickets(
        self,
        department_id: str,
        *,
        status: str | None,
        priority: str | None,
        created_from: datetime | None,
        created_to: datetime | None,
    ) -> list[dict[str, Any]]: ...

    def get_department_ticket(
        self, ticket_id: str, department_id: str
    ) -> dict[str, Any] | None: ...

    def list_messages(self, ticket_id: str) -> list[dict[str, Any]]: ...

    def list_events(self, ticket_id: str) -> list[dict[str, Any]]: ...

    def add_reply(
        self, *, ticket_id: str, actor: StaffActor, body: str, action_id: str
    ) -> MutationResult: ...

    def transition_ticket(
        self,
        *,
        ticket_id: str,
        actor: StaffActor,
        to_status: str,
        resolution_summary: str | None,
        action_id: str,
    ) -> MutationResult: ...

    def request_action(
        self,
        *,
        ticket_id: str,
        actor: StaffActor,
        request_type: RequestType,
        reason: str,
        action_id: str,
    ) -> MutationResult: ...


class StaffWorkflowService:
    def __init__(self, backend: StaffBackend) -> None:
        self._backend = backend

    def authenticate(self, authorization: str | None) -> StaffActor:
        token = _bearer_token(authorization)
        try:
            uid = self._backend.verify_id_token(token)
        except Exception as exc:
            raise AuthenticationError("invalid Firebase ID token") from exc
        try:
            profile = self._backend.get_user_profile(uid)
        except Exception as exc:
            raise PersistenceError("profile lookup failed") from exc
        if (
            not profile
            or profile.get("active") is not True
            or profile.get("role") != "staff"
        ):
            raise PermissionError("active staff profile required")
        department_id = profile.get("departmentId")
        if not isinstance(department_id, str) or department_id not in DEPARTMENT_IDS:
            raise PermissionError("valid staff department required")
        return StaffActor(uid=uid, department_id=department_id)  # type: ignore[arg-type]

    def list_tickets(
        self,
        actor: StaffActor,
        *,
        status: str | None,
        priority: str | None,
        created_from: datetime | None,
        created_to: datetime | None,
    ) -> list[dict[str, Any]]:
        try:
            return self._backend.list_department_tickets(
                actor.department_id,
                status=status,
                priority=priority,
                created_from=created_from,
                created_to=created_to,
            )
        except Exception as exc:
            raise PersistenceError("ticket query failed") from exc

    def detail(self, actor: StaffActor, ticket_id: str) -> dict[str, Any]:
        try:
            ticket = self._backend.get_department_ticket(ticket_id, actor.department_id)
        except Exception as exc:
            raise PersistenceError("ticket lookup failed") from exc
        if ticket is None:
            raise StaffTicketNotFound("ticket not found")
        try:
            return {
                **ticket,
                "messages": self._backend.list_messages(ticket_id),
                "events": self._backend.list_events(ticket_id),
            }
        except Exception as exc:
            raise PersistenceError("ticket history lookup failed") from exc

    def reply(
        self, actor: StaffActor, ticket_id: str, *, body: str, action_id: str
    ) -> MutationResult:
        try:
            return self._backend.add_reply(
                ticket_id=ticket_id,
                actor=actor,
                body=redact_sensitive_data(body),
                action_id=action_id,
            )
        except StaffTicketNotFound:
            raise
        except Exception as exc:
            raise PersistenceError("reply transaction failed") from exc

    def transition(
        self,
        actor: StaffActor,
        ticket_id: str,
        *,
        to_status: str,
        resolution_summary: str | None,
        action_id: str,
    ) -> MutationResult:
        try:
            return self._backend.transition_ticket(
                ticket_id=ticket_id,
                actor=actor,
                to_status=to_status,
                resolution_summary=(
                    redact_sensitive_data(resolution_summary)
                    if resolution_summary is not None
                    else None
                ),
                action_id=action_id,
            )
        except (StaffTicketNotFound, InvalidTransition):
            raise
        except Exception as exc:
            raise PersistenceError("transition transaction failed") from exc

    def request(
        self,
        actor: StaffActor,
        ticket_id: str,
        *,
        request_type: RequestType,
        reason: str,
        action_id: str,
    ) -> MutationResult:
        try:
            return self._backend.request_action(
                ticket_id=ticket_id,
                actor=actor,
                request_type=request_type,
                reason=redact_sensitive_data(reason),
                action_id=action_id,
            )
        except StaffTicketNotFound:
            raise
        except Exception as exc:
            raise PersistenceError("request transaction failed") from exc


def validate_staff_transition(from_status: str, to_status: str) -> None:
    if to_status not in ALLOWED_STAFF_TRANSITIONS.get(from_status, frozenset()):
        raise InvalidTransition(
            f"transition {from_status} to {to_status} is not allowed"
        )


def _bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise AuthenticationError("Firebase ID token required")
    scheme, separator, token = authorization.partition(" ")
    if separator != " " or scheme.lower() != "bearer" or not token.strip():
        raise AuthenticationError("Firebase ID token required")
    return token.strip()


class FirebaseAdminStaffBackend(FirebaseAdminTicketBackend):
    """Admin-SDK adapter. All mutations recheck department inside transactions."""

    def __init__(self, db: Any = None) -> None:
        if db is None:
            super().__init__()
            return
        self._db = db
        from firebase_admin import firestore

        self.server_timestamp = firestore.SERVER_TIMESTAMP

    def _summary(self, snapshot: Any) -> dict[str, Any]:
        data = snapshot.to_dict()
        return {"ticketId": snapshot.id, **data}

    def list_department_tickets(
        self,
        department_id: str,
        *,
        status: str | None,
        priority: str | None,
        created_from: datetime | None,
        created_to: datetime | None,
    ) -> list[dict[str, Any]]:
        from google.cloud.firestore_v1.base_query import FieldFilter

        # Authorization is the only Firestore predicate. Optional UI filters are
        # applied to the already department-scoped demo result set, avoiding a
        # combinatorial set of guessed composite indexes on the Spark plan.
        query = self._db.collection("tickets").where(
            filter=FieldFilter("departmentId", "==", department_id)
        )
        values = [self._summary(item) for item in query.stream()]
        if status:
            values = [value for value in values if value["status"] == status]
        if priority:
            values = [value for value in values if value["priority"] == priority]
        if created_from:
            values = [value for value in values if value["createdAt"] >= created_from]
        if created_to:
            values = [value for value in values if value["createdAt"] <= created_to]
        return sorted(values, key=lambda value: value["createdAt"], reverse=True)

    def get_department_ticket(
        self, ticket_id: str, department_id: str
    ) -> dict[str, Any] | None:
        snapshot = self._db.collection("tickets").document(ticket_id).get()
        if not snapshot.exists or snapshot.get("departmentId") != department_id:
            return None
        return self._summary(snapshot)

    def list_messages(self, ticket_id: str) -> list[dict[str, Any]]:
        query = (
            self._db.collection("tickets")
            .document(ticket_id)
            .collection("messages")
            .order_by("createdAt")
        )
        return [
            {"messageId": item.id, **normalize_message_document(item.to_dict())}
            for item in query.stream()
        ]

    def list_events(self, ticket_id: str) -> list[dict[str, Any]]:
        query = (
            self._db.collection("tickets")
            .document(ticket_id)
            .collection("events")
            .order_by("createdAt")
        )
        return [{"eventId": item.id, **item.to_dict()} for item in query.stream()]

    def _ticket_for_mutation(
        self, transaction: Any, ticket_id: str, actor: StaffActor
    ) -> tuple[Any, dict[str, Any]]:
        reference = self._db.collection("tickets").document(ticket_id)
        snapshot = next(transaction.get(reference))
        if not snapshot.exists or snapshot.get("departmentId") != actor.department_id:
            raise StaffTicketNotFound("ticket not found")
        return reference, snapshot.to_dict()

    def add_reply(
        self, *, ticket_id: str, actor: StaffActor, body: str, action_id: str
    ) -> MutationResult:
        def operation(transaction: Any) -> MutationResult:
            ticket_ref, ticket = self._ticket_for_mutation(
                transaction, ticket_id, actor
            )
            message_ref = ticket_ref.collection("messages").document(action_id)
            event_ref = ticket_ref.collection("events").document(f"reply_{action_id}")
            if next(transaction.get(event_ref)).exists:
                return MutationResult(ticket_id, action_id, ticket["status"], True)
            transaction.set(
                message_ref,
                {
                    "authorId": actor.uid,
                    "authorRole": "staff",
                    "body": body,
                    "visibility": "participants",
                    "createdAt": self.server_timestamp,
                },
            )
            transaction.set(
                event_ref,
                {
                    "type": "staff_reply",
                    "actorId": actor.uid,
                    "actorRole": "staff",
                    "fromValue": None,
                    "toValue": action_id,
                    "createdAt": self.server_timestamp,
                },
            )
            transaction.update(ticket_ref, {"updatedAt": self.server_timestamp})
            return MutationResult(ticket_id, action_id, ticket["status"], False)

        return run_firestore_transaction(self._db, operation)

    def transition_ticket(
        self,
        *,
        ticket_id: str,
        actor: StaffActor,
        to_status: str,
        resolution_summary: str | None,
        action_id: str,
    ) -> MutationResult:
        def operation(transaction: Any) -> MutationResult:
            ticket_ref, ticket = self._ticket_for_mutation(
                transaction, ticket_id, actor
            )
            event_ref = ticket_ref.collection("events").document(action_id)
            if next(transaction.get(event_ref)).exists:
                return MutationResult(ticket_id, action_id, ticket["status"], True)
            from_status = ticket["status"]
            validate_staff_transition(from_status, to_status)
            if to_status == "resolved" and not resolution_summary:
                raise InvalidTransition("resolution summary is required")
            changes: dict[str, Any] = {
                "status": to_status,
                "updatedAt": self.server_timestamp,
            }
            if to_status == "resolved":
                changes.update(
                    {
                        "resolutionSummary": resolution_summary,
                        "resolvedAt": self.server_timestamp,
                    }
                )
            transaction.update(ticket_ref, changes)
            transaction.set(
                event_ref,
                {
                    "type": "status_transition",
                    "actorId": actor.uid,
                    "actorRole": "staff",
                    "fromValue": from_status,
                    "toValue": to_status,
                    "createdAt": self.server_timestamp,
                },
            )
            return MutationResult(ticket_id, action_id, to_status, False)

        return run_firestore_transaction(self._db, operation)

    def request_action(
        self,
        *,
        ticket_id: str,
        actor: StaffActor,
        request_type: RequestType,
        reason: str,
        action_id: str,
    ) -> MutationResult:
        def operation(transaction: Any) -> MutationResult:
            ticket_ref, ticket = self._ticket_for_mutation(
                transaction, ticket_id, actor
            )
            event_ref = ticket_ref.collection("events").document(action_id)
            if next(transaction.get(event_ref)).exists:
                return MutationResult(ticket_id, action_id, ticket["status"], True)
            transaction.set(
                event_ref,
                {
                    "type": request_type,
                    "actorId": actor.uid,
                    "actorRole": "staff",
                    "fromValue": None,
                    "toValue": reason,
                    "createdAt": self.server_timestamp,
                },
            )
            transaction.update(ticket_ref, {"updatedAt": self.server_timestamp})
            return MutationResult(ticket_id, action_id, ticket["status"], False)

        return run_firestore_transaction(self._db, operation)


def _sample_dev_staff_tickets() -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return [
        {
            "ticketId": "cg_ticket_cust1",
            "id": "cg_ticket_cust1",
            "customerId": "demo_customer_uid",
            "departmentId": "general_support",
            "assignedDepartmentId": "general_support",
            "status": "triaged",
            "priority": "normal",
            "inputLocale": "en",
            "complaintText": "I was charged an unknown monthly fee and my card was declined.",
            "assignedStaffId": "staff1_uid",
            "predictedDepartmentId": "general_support",
            "predictionConfidence": 0.85,
            "routingSource": "model",
            "escalated": False,
            "resolutionSummary": None,
            "resolvedAt": None,
            "createdAt": now,
            "updatedAt": now,
        },
        {
            "ticketId": "cg_ticket_cust2",
            "id": "cg_ticket_cust2",
            "customerId": "demo_customer_uid",
            "departmentId": "general_support",
            "assignedDepartmentId": "general_support",
            "status": "in_progress",
            "priority": "high",
            "inputLocale": "en",
            "complaintText": "Cannot access online account login since yesterday.",
            "assignedStaffId": "staff1_uid",
            "predictedDepartmentId": "general_support",
            "predictionConfidence": 0.92,
            "routingSource": "model",
            "escalated": False,
            "resolutionSummary": None,
            "resolvedAt": None,
            "createdAt": now,
            "updatedAt": now,
        },
    ]


class InMemoryStaffBackend:
    def __init__(self, tickets: list[dict[str, Any]] | None = None) -> None:
        raw_tickets = tickets if tickets is not None else _sample_dev_staff_tickets()
        self._tickets: dict[str, dict[str, Any]] = {
            ticket["id"]: dict(ticket) for ticket in raw_tickets
        }
        self._messages: dict[str, list[dict[str, Any]]] = {}
        self._events: dict[str, list[dict[str, Any]]] = {}

    def verify_id_token(self, token: str) -> str:
        return "demo_staff_uid"

    def get_user_profile(self, uid: str) -> dict[str, Any] | None:
        return {
            "role": "staff",
            "departmentId": "general_support",
            "active": True,
        }

    def list_department_tickets(
        self,
        department_id: str,
        *,
        status: str | None,
        priority: str | None,
        created_from: datetime | None,
        created_to: datetime | None,
    ) -> list[dict[str, Any]]:
        results = []
        target = self._tickets
        for t in target.values():
            if t.get("departmentId") != department_id:
                continue
            if status and t.get("status") != status:
                continue
            if priority and t.get("priority") != priority:
                continue
            results.append({"ticketId": t["id"], **t})
        return results

    def get_department_ticket(
        self, ticket_id: str, department_id: str
    ) -> dict[str, Any] | None:
        t = self._tickets.get(ticket_id)
        if not t:
            return None
        return dict(t)

    def list_messages(self, ticket_id: str) -> list[dict[str, Any]]:
        return list(self._messages.get(ticket_id, []))

    def list_events(self, ticket_id: str) -> list[dict[str, Any]]:
        return list(self._events.get(ticket_id, []))

    def add_reply(
        self, *, ticket_id: str, actor: StaffActor, body: str, action_id: str
    ) -> MutationResult:
        if ticket_id not in self._tickets:
            raise StaffTicketNotFound("ticket not found")
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        msg = {
            "messageId": action_id,
            "id": action_id,
            "authorId": actor.uid,
            "senderId": actor.uid,
            "authorRole": "staff",
            "senderRole": "staff",
            "body": body,
            "text": body,
            "visibility": "participants",
            "createdAt": now,
        }
        self._messages.setdefault(ticket_id, []).append(msg)
        return MutationResult(
            ticket_id, action_id, self._tickets[ticket_id]["status"], False
        )

    def transition_ticket(
        self,
        *,
        ticket_id: str,
        actor: StaffActor,
        to_status: str,
        resolution_summary: str | None,
        action_id: str,
    ) -> MutationResult:
        if ticket_id not in self._tickets:
            raise StaffTicketNotFound("ticket not found")
        t = self._tickets[ticket_id]
        from_status = t["status"]
        validate_staff_transition(from_status, to_status)
        if to_status == "resolved" and not resolution_summary:
            raise InvalidTransition("resolution summary is required")
        t["status"] = to_status
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        t["updatedAt"] = now
        if to_status == "resolved":
            t["resolutionSummary"] = resolution_summary
            t["resolvedAt"] = now
        return MutationResult(ticket_id, action_id, to_status, False)

    def request_action(
        self,
        *,
        ticket_id: str,
        actor: StaffActor,
        request_type: RequestType,
        reason: str,
        action_id: str,
    ) -> MutationResult:
        if ticket_id not in self._tickets:
            raise StaffTicketNotFound("ticket not found")
        return MutationResult(
            ticket_id, action_id, self._tickets[ticket_id]["status"], False
        )
