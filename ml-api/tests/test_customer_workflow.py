"""Pytest suite for Day 15 Customer Workflow API and Backend Service."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from app.customer_workflow import InMemoryCustomerBackend
from app.main import create_app


class FakeTicketBackend:
    def verify_id_token(self, token: str) -> str:
        if token == "valid_customer_token":
            return "cust_123"
        if token == "customer_2_token":
            return "cust_456"
        if token == "staff_token":
            return "staff_999"
        raise RuntimeError("Invalid token")

    def get_user_profile(self, uid: str) -> dict[str, Any] | None:
        if uid in ("cust_123", "cust_456"):
            return {"role": "customer", "active": True}
        if uid == "staff_999":
            return {"role": "staff", "active": True, "departmentId": "transfer_payment"}
        return None


def _sample_tickets() -> list[dict[str, Any]]:
    return [
        {
            "id": "t1",
            "customerId": "cust_123",
            "status": "in_progress",
            "complaintText": "My money transfer failed card number 1234567890123456",
            "inputLocale": "en",
            "predictedDepartmentId": "transfer_payment",
            "assignedDepartmentId": "transfer_payment",
            "priority": "medium",
            "createdAt": "2026-08-01T10:00:00Z",
            "updatedAt": "2026-08-01T10:30:00Z",
            "messages": [
                {
                    "id": "msg_1",
                    "senderId": "cust_123",
                    "senderRole": "customer",
                    "text": "Please help check this transfer",
                    "createdAt": "2026-08-01T10:05:00Z",
                },
                {
                    "id": "msg_2",
                    "senderId": "staff_999",
                    "senderRole": "staff",
                    "text": "We are looking into it.",
                    "createdAt": "2026-08-01T10:15:00Z",
                },
            ],
        },
        {
            "id": "t2",
            "customerId": "cust_123",
            "status": "resolved",
            "complaintText": "ATM swallowed my card",
            "inputLocale": "en",
            "predictedDepartmentId": "card_atm",
            "assignedDepartmentId": "card_atm",
            "priority": "high",
            "createdAt": "2026-07-28T09:00:00Z",
            "updatedAt": "2026-07-29T11:00:00Z",
            "resolvedAt": "2026-07-29T11:00:00Z",
            "messages": [],
        },
        {
            "id": "t3_other",
            "customerId": "cust_456",
            "status": "submitted",
            "complaintText": "Another customer complaint",
            "inputLocale": "en",
            "createdAt": "2026-08-02T12:00:00Z",
        },
    ]


def test_customer_list_tickets():
    backend = InMemoryCustomerBackend(_sample_tickets())
    app = create_app(
        ticket_backend=FakeTicketBackend(),
        customer_backend=backend,
    )
    client = TestClient(app)

    res = client.get(
        "/customer/tickets",
        headers={"Authorization": "Bearer valid_customer_token"},
    )
    assert res.status_code == 200
    data = res.json()
    assert len(data["tickets"]) == 2
    ids = {t["id"] for t in data["tickets"]}
    assert ids == {"t1", "t2"}


def test_customer_ticket_detail_success():
    backend = InMemoryCustomerBackend(_sample_tickets())
    app = create_app(
        ticket_backend=FakeTicketBackend(),
        customer_backend=backend,
    )
    client = TestClient(app)

    res = client.get(
        "/customer/tickets/t1",
        headers={"Authorization": "Bearer valid_customer_token"},
    )
    assert res.status_code == 200
    detail = res.json()
    assert detail["id"] == "t1"
    assert detail["status"] == "in_progress"
    assert len(detail["messages"]) == 2


def test_cross_customer_ticket_does_not_leak_existence():
    backend = InMemoryCustomerBackend(_sample_tickets())
    app = create_app(
        ticket_backend=FakeTicketBackend(),
        customer_backend=backend,
    )
    client = TestClient(app)

    # Customer 1 trying to access Customer 2's ticket t3_other
    res = client.get(
        "/customer/tickets/t3_other",
        headers={"Authorization": "Bearer valid_customer_token"},
    )
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "ticket_not_found"


def test_customer_send_message_pii_redacted():
    backend = InMemoryCustomerBackend(_sample_tickets())
    app = create_app(
        ticket_backend=FakeTicketBackend(),
        customer_backend=backend,
    )
    client = TestClient(app)

    payload = {
        "messageText": "My account password: MyPassword123 and card number: 1234567890123456",
        "actionId": "message-action-001",
    }
    res = client.post(
        "/customer/tickets/t1/messages",
        json=payload,
        headers={"Authorization": "Bearer valid_customer_token"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["senderRole"] == "customer"
    assert "[REDACTED]" in body["text"]
    assert "MyPassword123" not in body["text"]


def test_customer_submit_feedback_resolved_ticket():
    backend = InMemoryCustomerBackend(_sample_tickets())
    app = create_app(
        ticket_backend=FakeTicketBackend(),
        customer_backend=backend,
    )
    client = TestClient(app)

    payload = {
        "rating": 5,
        "comments": "Great service, resolved quickly!",
        "actionId": "feedback-action-001",
    }
    res = client.post(
        "/customer/tickets/t2/feedback",
        json=payload,
        headers={"Authorization": "Bearer valid_customer_token"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "feedback_submitted"
    assert body["ticketId"] == "t2"


def test_customer_submit_feedback_unresolved_ticket_fails():
    backend = InMemoryCustomerBackend(_sample_tickets())
    app = create_app(
        ticket_backend=FakeTicketBackend(),
        customer_backend=backend,
    )
    client = TestClient(app)

    # Ticket t1 is in_progress, not resolved
    payload = {
        "rating": 4,
        "comments": "Not yet resolved",
        "actionId": "feedback-action-002",
    }
    res = client.post(
        "/customer/tickets/t1/feedback",
        json=payload,
        headers={"Authorization": "Bearer valid_customer_token"},
    )
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "invalid_ticket_state"


def test_retried_customer_message_is_idempotent():
    backend = InMemoryCustomerBackend(_sample_tickets())
    client = TestClient(
        create_app(ticket_backend=FakeTicketBackend(), customer_backend=backend)
    )
    payload = {"messageText": "Please retry safely", "actionId": "message-retry-001"}
    headers = {"Authorization": "Bearer valid_customer_token"}

    first = client.post("/customer/tickets/t1/messages", json=payload, headers=headers)
    second = client.post("/customer/tickets/t1/messages", json=payload, headers=headers)

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert len(backend.messages["t1"]) == 3


def test_missing_invalid_wrong_role_and_inactive_customer_are_denied():
    backend = InMemoryCustomerBackend(_sample_tickets())
    auth = FakeTicketBackend()
    client = TestClient(create_app(ticket_backend=auth, customer_backend=backend))

    assert client.get("/customer/tickets").status_code == 401
    assert (
        client.get(
            "/customer/tickets", headers={"Authorization": "Bearer invalid"}
        ).status_code
        == 401
    )
    assert (
        client.get(
            "/customer/tickets", headers={"Authorization": "Bearer staff_token"}
        ).status_code
        == 403
    )
    auth.get_user_profile = lambda _uid: {"role": "customer", "active": False}
    assert (
        client.get(
            "/customer/tickets",
            headers={"Authorization": "Bearer valid_customer_token"},
        ).status_code
        == 403
    )


def test_customer_message_rejects_protected_field_spoofing():
    backend = InMemoryCustomerBackend(_sample_tickets())
    client = TestClient(
        create_app(ticket_backend=FakeTicketBackend(), customer_backend=backend)
    )
    response = client.post(
        "/customer/tickets/t1/messages",
        json={
            "messageText": "Synthetic follow-up",
            "actionId": "message-spoof-001",
            "senderId": "spoofed-user",
            "senderRole": "manager",
            "departmentId": "fraud_security",
        },
        headers={"Authorization": "Bearer valid_customer_token"},
    )
    assert response.status_code == 422
    assert backend.messages["t1"] == _sample_tickets()[0]["messages"]
