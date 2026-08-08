"""Synthetic Day 14 staff workflow API and authorization tests."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.model import Prediction
from app.staff_workflow import (
    ALLOWED_STAFF_TRANSITIONS,
    InvalidTransition,
    MutationResult,
    StaffActor,
    StaffTicketNotFound,
    validate_staff_transition,
)
from app.synthetic_fixture import build_synthetic_triaged_ticket

NOW = datetime(2026, 8, 2, 8, 0, tzinfo=UTC)


class FakeClassifier:
    model_version = "v1"

    def predict(self, _text: str) -> Prediction:
        return Prediction("card_atm", 0.8, False, None)


def ticket(
    ticket_id: str, department_id: str | None, status: str = "triaged"
) -> dict[str, Any]:
    return {
        "ticketId": ticket_id,
        "customerId": "synthetic-customer",
        "complaintText": "Synthetic staff workflow complaint.",
        "inputLocale": "en",
        "departmentId": department_id,
        "assignedStaffId": None,
        "status": status,
        "priority": "normal",
        "predictedDepartmentId": None,
        "predictionConfidence": None,
        "routingSource": "manual_review" if department_id else "pending",
        "escalated": False,
        "resolutionSummary": None,
        "createdAt": NOW,
        "updatedAt": NOW,
        "resolvedAt": None,
    }


class FakeStaffBackend:
    def __init__(self) -> None:
        self.uid = "staff-card-uid"
        self.profile: dict[str, Any] | None = {
            "active": True,
            "role": "staff",
            "departmentId": "card_atm",
        }
        self.tickets = {
            "same": ticket("same", "card_atm"),
            "other": ticket("other", "loan_credit"),
            "pending": ticket("pending", None, "submitted"),
        }
        self.messages: dict[str, list[dict[str, Any]]] = {
            key: [] for key in self.tickets
        }
        self.events: dict[str, list[dict[str, Any]]] = {key: [] for key in self.tickets}
        self.actions: set[str] = set()
        self.fail_transaction = False
        self.last_query_department: str | None = None

    def verify_id_token(self, token: str) -> str:
        if token != "valid-staff-token":
            raise ValueError("invalid, malformed, or expired token")
        return self.uid

    def get_user_profile(self, uid: str) -> dict[str, Any] | None:
        assert uid == self.uid
        return self.profile

    def list_department_tickets(
        self,
        department_id: str,
        *,
        status: str | None,
        priority: str | None,
        created_from: datetime | None,
        created_to: datetime | None,
    ) -> list[dict[str, Any]]:
        self.last_query_department = department_id
        values = [
            deepcopy(value)
            for value in self.tickets.values()
            if value["departmentId"] == department_id
        ]
        if status:
            values = [value for value in values if value["status"] == status]
        if priority:
            values = [value for value in values if value["priority"] == priority]
        if created_from:
            values = [value for value in values if value["createdAt"] >= created_from]
        if created_to:
            values = [value for value in values if value["createdAt"] <= created_to]
        return values

    def get_department_ticket(
        self, ticket_id: str, department_id: str
    ) -> dict[str, Any] | None:
        value = self.tickets.get(ticket_id)
        return (
            deepcopy(value)
            if value and value["departmentId"] == department_id
            else None
        )

    def list_messages(self, ticket_id: str) -> list[dict[str, Any]]:
        return deepcopy(self.messages[ticket_id])

    def list_events(self, ticket_id: str) -> list[dict[str, Any]]:
        return deepcopy(self.events[ticket_id])

    def _authorized(self, ticket_id: str, actor: StaffActor) -> dict[str, Any]:
        value = self.tickets.get(ticket_id)
        if not value or value["departmentId"] != actor.department_id:
            raise StaffTicketNotFound("ticket not found")
        return value

    def _duplicate(self, ticket_id: str, action_id: str) -> MutationResult | None:
        if action_id in self.actions:
            return MutationResult(
                ticket_id, action_id, self.tickets[ticket_id]["status"], True
            )
        return None

    def add_reply(
        self, *, ticket_id: str, actor: StaffActor, body: str, action_id: str
    ) -> MutationResult:
        value = self._authorized(ticket_id, actor)
        duplicate = self._duplicate(ticket_id, action_id)
        if duplicate:
            return duplicate
        if self.fail_transaction:
            raise RuntimeError("synthetic transaction failure")
        self.messages[ticket_id].append(
            {
                "messageId": action_id,
                "authorId": actor.uid,
                "authorRole": "staff",
                "body": body,
                "visibility": "participants",
                "createdAt": NOW,
            }
        )
        self.events[ticket_id].append(
            {
                "eventId": f"reply_{action_id}",
                "type": "staff_reply",
                "actorId": actor.uid,
                "actorRole": "staff",
                "fromValue": None,
                "toValue": action_id,
                "createdAt": NOW,
            }
        )
        self.actions.add(action_id)
        return MutationResult(ticket_id, action_id, value["status"], False)

    def transition_ticket(
        self,
        *,
        ticket_id: str,
        actor: StaffActor,
        to_status: str,
        resolution_summary: str | None,
        action_id: str,
    ) -> MutationResult:
        value = self._authorized(ticket_id, actor)
        duplicate = self._duplicate(ticket_id, action_id)
        if duplicate:
            return duplicate
        validate_staff_transition(value["status"], to_status)
        if to_status == "resolved" and not resolution_summary:
            raise InvalidTransition("resolution summary is required")
        if self.fail_transaction:
            raise RuntimeError("synthetic transaction failure")
        previous = value["status"]
        next_value = deepcopy(value)
        next_events = deepcopy(self.events[ticket_id])
        next_value["status"] = to_status
        next_value["updatedAt"] = NOW
        if to_status == "resolved":
            next_value["resolutionSummary"] = resolution_summary
            next_value["resolvedAt"] = NOW
        next_events.append(
            {
                "eventId": action_id,
                "type": "status_transition",
                "actorId": actor.uid,
                "actorRole": "staff",
                "fromValue": previous,
                "toValue": to_status,
                "createdAt": NOW,
            }
        )
        self.tickets[ticket_id] = next_value
        self.events[ticket_id] = next_events
        self.actions.add(action_id)
        return MutationResult(ticket_id, action_id, to_status, False)

    def request_action(
        self,
        *,
        ticket_id: str,
        actor: StaffActor,
        request_type: str,
        reason: str,
        action_id: str,
    ) -> MutationResult:
        value = self._authorized(ticket_id, actor)
        duplicate = self._duplicate(ticket_id, action_id)
        if duplicate:
            return duplicate
        if self.fail_transaction:
            raise RuntimeError("synthetic transaction failure")
        self.events[ticket_id].append(
            {
                "eventId": action_id,
                "type": request_type,
                "actorId": actor.uid,
                "actorRole": "staff",
                "fromValue": None,
                "toValue": reason,
                "createdAt": NOW,
            }
        )
        self.actions.add(action_id)
        return MutationResult(ticket_id, action_id, value["status"], False)


@pytest.fixture
def backend() -> FakeStaffBackend:
    return FakeStaffBackend()


@pytest.fixture
def client(tmp_path: Path, backend: FakeStaffBackend):
    settings = Settings(model_path=tmp_path / "model.joblib", expected_model_sha256="a")
    with TestClient(
        create_app(
            settings=settings,
            model_loader=lambda *_args, **_kwargs: FakeClassifier(),
            staff_backend=backend,
        )
    ) as api:
        yield api


def headers(token: str = "valid-staff-token") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize("token", [None, "malformed", "expired", "invalid"])
def test_missing_malformed_expired_and_invalid_tokens(
    client: TestClient, token: str | None
) -> None:
    response = client.get("/staff/tickets", headers=headers(token) if token else {})
    assert response.status_code == 401


@pytest.mark.parametrize(
    "profile",
    [
        None,
        {"active": False, "role": "staff", "departmentId": "card_atm"},
        {"active": True, "role": "customer", "departmentId": None},
        {"active": True, "role": "staff", "departmentId": None},
        {"active": True, "role": "staff", "departmentId": "pending"},
    ],
)
def test_invalid_staff_profiles_are_denied(
    client: TestClient, backend: FakeStaffBackend, profile: dict[str, Any] | None
) -> None:
    backend.profile = profile
    assert client.get("/staff/tickets", headers=headers()).status_code == 403


def test_queue_is_always_department_scoped_and_filters_do_not_broaden(
    client: TestClient, backend: FakeStaffBackend
) -> None:
    response = client.get(
        "/staff/tickets?status=triaged&priority=normal", headers=headers()
    )
    assert response.status_code == 200
    assert [item["ticketId"] for item in response.json()["tickets"]] == ["same"]
    assert backend.last_query_department == "card_atm"
    empty = client.get(
        "/staff/tickets",
        params={"created_from": (NOW + timedelta(days=1)).isoformat()},
        headers=headers(),
    )
    assert empty.status_code == 200 and empty.json() == {"tickets": []}


@pytest.mark.parametrize("ticket_id", ["other", "pending", "missing"])
def test_detail_hides_cross_department_pending_and_missing_tickets(
    client: TestClient, ticket_id: str
) -> None:
    response = client.get(f"/staff/tickets/{ticket_id}", headers=headers())
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ticket_not_found"


def test_same_department_detail_includes_messages_and_events(
    client: TestClient,
) -> None:
    response = client.get("/staff/tickets/same", headers=headers())
    assert response.status_code == 200
    assert response.json()["ticketId"] == "same"
    assert response.json()["messages"] == [] and response.json()["events"] == []


@pytest.mark.parametrize(
    ("from_status", "to_status"),
    [
        ("triaged", "in_progress"),
        ("in_progress", "awaiting_customer"),
        ("awaiting_customer", "in_progress"),
        ("in_progress", "resolved"),
    ],
)
def test_every_valid_transition(
    client: TestClient, backend: FakeStaffBackend, from_status: str, to_status: str
) -> None:
    backend.tickets["same"]["status"] = from_status
    payload: dict[str, Any] = {
        "status": to_status,
        "actionId": f"action_{from_status}_{to_status}",
    }
    if to_status == "resolved":
        payload["resolutionSummary"] = "Synthetic issue resolved."
    response = client.post(
        "/staff/tickets/same/transitions", json=payload, headers=headers()
    )
    assert response.status_code == 200
    assert backend.tickets["same"]["status"] == to_status
    assert backend.events["same"][-1]["type"] == "status_transition"


@pytest.mark.parametrize(
    ("from_status", "to_status"),
    [
        (source, target)
        for source in [
            "submitted",
            "triaged",
            "in_progress",
            "awaiting_customer",
            "resolved",
            "closed",
        ]
        for target in ["in_progress", "awaiting_customer", "resolved"]
        if target not in ALLOWED_STAFF_TRANSITIONS.get(source, frozenset())
    ],
)
def test_every_invalid_transition_is_rejected(
    client: TestClient, backend: FakeStaffBackend, from_status: str, to_status: str
) -> None:
    backend.tickets["same"]["status"] = from_status
    response = client.post(
        "/staff/tickets/same/transitions",
        json={
            "status": to_status,
            "resolutionSummary": "Synthetic resolution",
            "actionId": f"invalid_{from_status}_{to_status}",
        },
        headers=headers(),
    )
    assert response.status_code == 409


def test_protected_fields_and_status_spoofing_are_rejected(client: TestClient) -> None:
    response = client.post(
        "/staff/tickets/same/transitions",
        json={
            "status": "in_progress",
            "departmentId": "loan_credit",
            "actionId": "protected_001",
        },
        headers=headers(),
    )
    assert response.status_code == 422
    assert (
        client.post(
            "/staff/tickets/same/transitions",
            json={"status": "closed", "actionId": "protected_002"},
            headers=headers(),
        ).status_code
        == 422
    )


def test_reply_binds_author_redacts_pii_and_is_idempotent(
    client: TestClient, backend: FakeStaffBackend
) -> None:
    payload = {
        "body": "Reply with PIN 1234 and card 4111 1111 1111 1111 removed.",
        "authorId": "spoofed",
        "actionId": "reply_action_001",
    }
    assert (
        client.post(
            "/staff/tickets/same/replies", json=payload, headers=headers()
        ).status_code
        == 422
    )
    payload.pop("authorId")
    first = client.post("/staff/tickets/same/replies", json=payload, headers=headers())
    second = client.post("/staff/tickets/same/replies", json=payload, headers=headers())
    assert first.status_code == 200 and first.json()["duplicate"] is False
    assert second.status_code == 200 and second.json()["duplicate"] is True
    assert backend.messages["same"][0]["authorId"] == backend.uid
    assert (
        "1234" not in backend.messages["same"][0]["body"]
        and "4111" not in backend.messages["same"][0]["body"]
    )
    assert len(backend.messages["same"]) == 1 and len(backend.events["same"]) == 1


def test_resolution_is_atomic_and_rolls_back_on_failure(
    client: TestClient, backend: FakeStaffBackend
) -> None:
    backend.tickets["same"]["status"] = "in_progress"
    before = deepcopy(backend.tickets["same"])
    backend.fail_transaction = True
    response = client.post(
        "/staff/tickets/same/transitions",
        json={
            "status": "resolved",
            "resolutionSummary": "Synthetic resolution",
            "actionId": "resolve_fail_001",
        },
        headers=headers(),
    )
    assert response.status_code == 503
    assert backend.tickets["same"] == before and backend.events["same"] == []


@pytest.mark.parametrize("request_type", ["request_reassignment", "request_escalation"])
def test_request_actions_are_audit_only(
    client: TestClient, backend: FakeStaffBackend, request_type: str
) -> None:
    protected_before = {
        key: backend.tickets["same"][key]
        for key in ["departmentId", "assignedStaffId", "priority", "escalated"]
    }
    response = client.post(
        "/staff/tickets/same/requests",
        json={
            "type": request_type,
            "reason": "Synthetic manager review requested.",
            "actionId": f"{request_type}_001",
        },
        headers=headers(),
    )
    assert response.status_code == 200
    assert backend.events["same"][-1]["type"] == request_type
    assert {
        key: backend.tickets["same"][key] for key in protected_before
    } == protected_before


def test_manager_only_operations_have_no_staff_endpoint(client: TestClient) -> None:
    for suffix in ["assign", "reroute", "priority", "escalate", "close", "reopen"]:
        assert (
            client.post(
                f"/staff/tickets/same/{suffix}", json={}, headers=headers()
            ).status_code
            == 404
        )


def test_synthetic_fixture_is_fixed_triaged_and_uses_no_seventh_department() -> None:
    timestamp = object()
    value = build_synthetic_triaged_ticket(timestamp)
    assert value["customerId"].startswith("synthetic-")
    assert value["departmentId"] == "card_atm"
    assert value["status"] == "triaged"
    assert value["routingSource"] == "manual_review"
    assert value["predictedDepartmentId"] is None
    assert value["predictionConfidence"] is None
    assert value["createdAt"] is timestamp and value["updatedAt"] is timestamp
    assert "pending" not in {value["departmentId"]}
