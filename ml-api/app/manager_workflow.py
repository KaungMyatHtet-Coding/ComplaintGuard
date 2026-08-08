"""Manager workflow service and Firestore backend adapter for Day 16."""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from app.schemas import LABELS


class ManagerWorkflowError(Exception):
    """Base exception for manager workflow operations."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ManagerPermissionError(ManagerWorkflowError):
    """Raised when user role is not manager."""


class TicketNotFound(ManagerWorkflowError):
    """Raised when target ticket is not found."""


class InvalidDepartmentError(ManagerWorkflowError):
    """Raised when target department ID is invalid."""


def _sample_dev_manager_data() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Sample data for local development when Firebase Admin SDK is unconfigured."""
    tickets = [
        {
            "id": "cg_ticket_001",
            "customerId": "cust_101",
            "complaintText": "Money transfer was deducted from my account but recipient has not received it yet.",
            "inputLocale": "en",
            "predictedDepartmentId": "transfer_payment",
            "predictionConfidence": 0.92,
            "departmentId": "transfer_payment",
            "status": "in_progress",
            "priority": "normal",
            "routingSource": "model",
            "createdAt": "2026-08-02T10:00:00Z",
            "updatedAt": "2026-08-03T11:00:00Z",
            "resolvedAt": None,
        },
        {
            "id": "cg_ticket_002",
            "customerId": "cust_102",
            "complaintText": "ATM at Downtown branch failed to dispense cash during withdrawal.",
            "inputLocale": "en",
            "predictedDepartmentId": "card_atm",
            "predictionConfidence": 0.88,
            "departmentId": "card_atm",
            "status": "resolved",
            "priority": "high",
            "routingSource": "model",
            "createdAt": "2026-07-29T14:00:00Z",
            "updatedAt": "2026-07-30T09:00:00Z",
            "resolvedAt": "2026-07-30T09:00:00Z",
        },
        {
            "id": "cg_ticket_lc01",
            "customerId": "cust_103",
            "complaintText": "I was charged an unknown monthly fee and my card statement shows unverified transaction.",
            "inputLocale": "en",
            "predictedDepartmentId": "account_support",
            "predictionConfidence": 0.48,
            "departmentId": "account_support",
            "status": "triaged",
            "priority": "high",
            "routingSource": "manual_review",
            "createdAt": "2026-08-03T08:30:00Z",
            "updatedAt": "2026-08-03T08:30:00Z",
            "resolvedAt": None,
        },
        {
            "id": "cg_ticket_lc02",
            "customerId": "cust_104",
            "complaintText": "Loan interest rate calculation is confusing and monthly payment deduction failed.",
            "inputLocale": "en",
            "predictedDepartmentId": "loan_credit",
            "predictionConfidence": 0.52,
            "departmentId": "loan_credit",
            "status": "triaged",
            "priority": "normal",
            "routingSource": "model",
            "createdAt": "2026-08-03T09:15:00Z",
            "updatedAt": "2026-08-03T09:15:00Z",
            "resolvedAt": None,
        },
    ]

    return tickets, []


class ManagerBackend(ABC):
    """Abstract interface for Manager Firestore operations."""

    @abstractmethod
    def get_all_tickets(self) -> list[dict[str, Any]]:
        """Fetch all tickets for analytics aggregation."""

    @abstractmethod
    def get_low_confidence_tickets(
        self, threshold: float = 0.60
    ) -> list[dict[str, Any]]:
        """Fetch tickets with low prediction confidence or manual triage flags."""

    @abstractmethod
    def override_department(
        self,
        ticket_id: str,
        new_department_id: str,
        manager_id: str,
        reason: str | None,
        action_id: str,
    ) -> dict[str, Any]:
        """Override ticket department assignment."""


class InMemoryManagerBackend(ManagerBackend):
    """In-memory backend for local testing and development."""

    def __init__(self, tickets: list[dict[str, Any]] | None = None) -> None:
        if tickets is None:
            tickets, _ = _sample_dev_manager_data()
        self.tickets = {ticket["id"]: dict(ticket) for ticket in tickets}
        self.overrides: list[dict[str, Any]] = []
        self.actions: dict[str, dict[str, Any]] = {}

    def get_all_tickets(self) -> list[dict[str, Any]]:
        return [dict(t) for t in self.tickets.values()]

    def get_low_confidence_tickets(
        self, threshold: float = 0.60
    ) -> list[dict[str, Any]]:
        results = []
        for t in self.tickets.values():
            conf = t.get("predictionConfidence")
            src = t.get("routingSource")
            if (conf is not None and conf < threshold) or src == "manual_review":
                results.append(dict(t))
        return results

    def override_department(
        self,
        ticket_id: str,
        new_department_id: str,
        manager_id: str,
        reason: str | None,
        action_id: str,
    ) -> dict[str, Any]:
        if action_id in self.actions:
            return dict(self.actions[action_id])
        if ticket_id not in self.tickets:
            raise TicketNotFound("target ticket not found")

        if new_department_id not in LABELS:
            raise InvalidDepartmentError("invalid department ID")

        doc = self.tickets[ticket_id]
        previous_department_id = doc.get("departmentId")
        doc["departmentId"] = new_department_id
        doc["routingSource"] = "manager_override"
        doc["updatedAt"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        override_record = {
            "ticketId": ticket_id,
            "previousDepartmentId": previous_department_id,
            "newDepartmentId": new_department_id,
            "managerId": manager_id,
            "reason": reason,
            "timestamp": doc["updatedAt"],
        }
        self.overrides.append(override_record)
        self.actions[action_id] = dict(doc)
        return doc


class FirebaseAdminManagerBackend(ManagerBackend):
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

    def get_all_tickets(self) -> list[dict[str, Any]]:
        docs = self.db.collection("tickets").stream()
        results = []
        for doc in docs:
            data = doc.to_dict()
            data["id"] = doc.id
            results.append(data)
        return results

    def get_low_confidence_tickets(
        self, threshold: float = 0.60
    ) -> list[dict[str, Any]]:
        docs = self.db.collection("tickets").stream()
        results = []
        for doc in docs:
            data = doc.to_dict()
            data["id"] = doc.id
            conf = data.get("predictionConfidence")
            src = data.get("routingSource")
            if (conf is not None and conf < threshold) or src == "manual_review":
                results.append(data)
        return results

    def override_department(
        self,
        ticket_id: str,
        new_department_id: str,
        manager_id: str,
        reason: str | None,
        action_id: str,
    ) -> dict[str, Any]:
        if new_department_id not in LABELS:
            raise InvalidDepartmentError("invalid department ID")

        doc_ref = self.db.collection("tickets").document(ticket_id)
        now_str = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        action_ref = doc_ref.collection("actions").document(action_id)
        audit_ref = doc_ref.collection("events").document(action_id)
        updates = {
            "departmentId": new_department_id,
            "routingSource": "manager_override",
            "updatedAt": now_str,
        }
        try:
            from app.ticketing import run_firestore_transaction

            def operation(transaction: Any) -> dict[str, Any]:
                action_snapshot = next(transaction.get(action_ref))
                if action_snapshot.exists:
                    return action_snapshot.to_dict()["result"]
                snapshot = next(transaction.get(doc_ref))
                if not snapshot.exists:
                    raise TicketNotFound("target ticket not found")
                doc_data = snapshot.to_dict()
                previous_department_id = doc_data.get("departmentId")
                result = {**doc_data, **updates, "id": ticket_id}
                transaction.update(doc_ref, updates)
                transaction.set(
                    audit_ref,
                    {
                        "ticketId": ticket_id,
                        "type": "manager_override",
                        "actorId": manager_id,
                        "actorRole": "manager",
                        "fromValue": previous_department_id,
                        "toValue": new_department_id,
                        "reason": reason,
                        "createdAt": now_str,
                    },
                )
                transaction.set(
                    action_ref, {"type": "manager_override", "result": result}
                )
                return result

            return run_firestore_transaction(self.db, operation)
        except TicketNotFound:
            raise
        except Exception as exc:
            from app.ticketing import PersistenceError

            raise PersistenceError("manager override transaction failed") from exc


class ManagerWorkflowService:
    """Core domain service for Manager Dashboard & Analytics."""

    def __init__(self, backend: ManagerBackend) -> None:
        self.backend = backend

    def get_analytics(self) -> dict[str, Any]:
        tickets = self.backend.get_all_tickets()
        total_tickets = len(tickets)
        active_tickets = sum(
            1
            for t in tickets
            if t.get("status")
            in ("submitted", "triaged", "in_progress", "awaiting_customer")
        )
        resolved_count = sum(1 for t in tickets if t.get("status") == "resolved")
        low_confidence_count = len(self.backend.get_low_confidence_tickets(0.60))

        resolution_hours: list[float] = []
        for t in tickets:
            if (
                t.get("status") == "resolved"
                and t.get("createdAt")
                and t.get("resolvedAt")
            ):
                try:
                    c_dt = datetime.fromisoformat(
                        str(t["createdAt"]).replace("Z", "+00:00")
                    )
                    r_dt = datetime.fromisoformat(
                        str(t["resolvedAt"]).replace("Z", "+00:00")
                    )
                    diff = (r_dt - c_dt).total_seconds() / 3600.0
                    if diff >= 0:
                        resolution_hours.append(diff)
                except (TypeError, ValueError):
                    continue

        avg_resolution_hours = (
            round(sum(resolution_hours) / len(resolution_hours), 1)
            if resolution_hours
            else 0.0
        )

        dept_stats: dict[str, dict[str, Any]] = {
            dept_id: {
                "departmentId": dept_id,
                "label": dept_id.replace("_", " ").title(),
                "total": 0,
                "inProgress": 0,
                "resolved": 0,
                "resolutionHours": [],
            }
            for dept_id in LABELS
        }

        for t in tickets:
            dept = t.get("departmentId")
            if dept in dept_stats:
                dept_stats[dept]["total"] += 1
                if t.get("status") in (
                    "submitted",
                    "triaged",
                    "in_progress",
                    "awaiting_customer",
                ):
                    dept_stats[dept]["inProgress"] += 1
                elif t.get("status") == "resolved":
                    dept_stats[dept]["resolved"] += 1
                    if t.get("createdAt") and t.get("resolvedAt"):
                        try:
                            c_dt = datetime.fromisoformat(
                                str(t["createdAt"]).replace("Z", "+00:00")
                            )
                            r_dt = datetime.fromisoformat(
                                str(t["resolvedAt"]).replace("Z", "+00:00")
                            )
                            diff = (r_dt - c_dt).total_seconds() / 3600.0
                            if diff >= 0:
                                dept_stats[dept]["resolutionHours"].append(diff)
                        except (TypeError, ValueError):
                            continue

        department_metrics = []
        for dept_id, data in dept_stats.items():
            hrs = data["resolutionHours"]
            avg_hrs = round(sum(hrs) / len(hrs), 1) if hrs else 0.0
            department_metrics.append(
                {
                    "departmentId": dept_id,
                    "label": data["label"],
                    "total": data["total"],
                    "inProgress": data["inProgress"],
                    "resolved": data["resolved"],
                    "avgResolutionHours": avg_hrs,
                }
            )

        return {
            "totalTickets": total_tickets,
            "activeTickets": active_tickets,
            "resolvedTickets": resolved_count,
            "lowConfidenceCount": low_confidence_count,
            "avgResolutionHours": avg_resolution_hours,
            "departmentMetrics": department_metrics,
        }

    def list_low_confidence_tickets(self) -> list[dict[str, Any]]:
        return self.backend.get_low_confidence_tickets(0.60)

    def override_department(
        self,
        ticket_id: str,
        new_department_id: str,
        manager_id: str,
        reason: str | None = None,
        action_id: str = "",
    ) -> dict[str, Any]:
        return self.backend.override_department(
            ticket_id=ticket_id,
            new_department_id=new_department_id,
            manager_id=manager_id,
            reason=reason,
            action_id=action_id,
        )
