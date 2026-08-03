"""Pytest suite for Day 15 Customer Workflow API and Backend Service."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi.testclient import TestClient

from app.customer_workflow import InMemoryCustomerBackend, CustomerWorkflowService
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


def test_customer_ticket_detail_access_denied():
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
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "ticket_access_denied"


def test_customer_send_message_pii_redacted():
    backend = InMemoryCustomerBackend(_sample_tickets())
    app = create_app(
        ticket_backend=FakeTicketBackend(),
        customer_backend=backend,
    )
    client = TestClient(app)

    payload = {"messageText": "My account password: MyPassword123 and card number: 1234567890123456"}
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

    payload = {"rating": 5, "comments": "Great service, resolved quickly!"}
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
    payload = {"rating": 4, "comments": "Not yet resolved"}
    res = client.post(
        "/customer/tickets/t1/feedback",
        json=payload,
        headers={"Authorization": "Bearer valid_customer_token"},
    )
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "invalid_ticket_state"
