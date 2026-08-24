"""Pytest suite for Day 15 Customer Workflow API and Backend Service."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
from app.customer_workflow import (
    CustomerHistoryCursor,
    CustomerWorkflowService,
    InMemoryCustomerBackend,
    customer_history_binding,
    customer_history_contract_fingerprint,
    decode_customer_history_cursor,
    encode_customer_history_cursor,
)
from app.main import create_app
from fastapi.testclient import TestClient


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
            return {"role": "customer", "active": True, "accountState": "active"}
        if uid == "staff_999":
            return {"role": "staff", "active": True, "accountState": "active", "departmentId": "transfer_payment"}
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


def _valid_history_tickets() -> list[dict[str, Any]]:
    tickets = _sample_tickets()
    tickets[0]["id"] = "ticket_" + "1" * 32
    tickets[1]["id"] = "ticket_" + "2" * 32
    tickets[2]["id"] = "ticket_" + "3" * 32
    tickets[0]["departmentId"] = "transfer_payment"
    tickets[1]["departmentId"] = "card_atm"
    return tickets


def test_customer_list_tickets():
    backend = InMemoryCustomerBackend(_valid_history_tickets())
    app = create_app(
        ticket_backend=FakeTicketBackend(),
        customer_backend=backend,
    )
    client = TestClient(app)

    res = client.get(
        "/customer/tickets?pageSize=1",
        headers={"Authorization": "Bearer valid_customer_token"},
    )
    assert res.status_code == 200
    data = res.json()
    assert len(data["tickets"]) == 1
    assert set(data["tickets"][0]) == {
        "complaintId", "status", "departmentId", "createdAt", "updatedAt", "resolvedAt"
    }
    assert data["hasMore"] is True
    assert data["nextCursor"]


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


def test_customer_detail_maps_complete_canonical_staff_message_body():
    backend = InMemoryCustomerBackend(_sample_tickets())
    backend.messages["t1"] = [
        {
            "id": "canonical-staff-message",
            "authorId": "staff_999",
            "authorRole": "staff",
            "body": "Complete canonical staff reply.",
            "visibility": "participants",
            "createdAt": "2026-08-01T10:15:00Z",
        }
    ]

    detail = CustomerWorkflowService(backend).get_ticket_detail("cust_123", "t1")

    assert detail.messages[0].sender_role == "support_team"
    assert detail.messages[0].body == "Complete canonical staff reply."
    assert "staff_999" not in detail.model_dump_json()


def test_customer_detail_rejects_incomplete_message_instead_of_blank_body():
    backend = InMemoryCustomerBackend(_sample_tickets())
    backend.messages["t1"] = [
        {
            "id": "malformed-message",
            "senderRole": "staff",
            "createdAt": "2026-08-01T10:15:00Z",
        }
    ]

    with pytest.raises(ValueError, match="no recognized complete schema"):
        CustomerWorkflowService(backend).get_ticket_detail("cust_123", "t1")


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
    assert "[REDACTED]" in body["body"]
    assert "MyPassword123" not in body["body"]
    stored = backend.messages["t1"][-1]
    assert stored["authorId"] == "cust_123"
    assert stored["authorRole"] == "customer"
    assert stored["body"] == body["body"]
    assert stored["visibility"] == "participants"
    assert not ({"senderId", "senderRole", "text"} & stored.keys())


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

    detail = client.get(
        "/customer/tickets/t2",
        headers={"Authorization": "Bearer valid_customer_token"},
    )
    assert detail.status_code == 200
    assert detail.json()["feedback"] == {
        "rating": 5,
        "comments": "Great service, resolved quickly!",
        "submittedAt": backend.tickets["t2"]["feedback"]["submittedAt"],
    }


def test_customer_feedback_retry_is_idempotent_and_new_action_conflicts():
    backend = InMemoryCustomerBackend(_sample_tickets())
    client = TestClient(
        create_app(ticket_backend=FakeTicketBackend(), customer_backend=backend)
    )
    headers = {"Authorization": "Bearer valid_customer_token"}
    first_payload = {
        "rating": 5,
        "comments": "Original feedback.",
        "actionId": "feedback-retry-001",
    }

    first = client.post(
        "/customer/tickets/t2/feedback", json=first_payload, headers=headers
    )
    retry = client.post(
        "/customer/tickets/t2/feedback", json=first_payload, headers=headers
    )
    original_feedback = dict(backend.tickets["t2"]["feedback"])
    duplicate = client.post(
        "/customer/tickets/t2/feedback",
        json={
            "rating": 1,
            "comments": "Must not overwrite.",
            "actionId": "feedback-new-action-002",
        },
        headers=headers,
    )

    assert first.status_code == retry.status_code == 200
    assert retry.json() == first.json()
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "feedback_already_submitted"
    assert backend.tickets["t2"]["feedback"] == original_feedback
    assert backend.feedbacks["fb_t2"]["rating"] == 5
    assert backend.feedbacks["fb_t2"]["comments"] == "Original feedback."
    assert list(backend.actions) == [("t2", "feedback:feedback-retry-001")]


def test_cross_customer_cannot_submit_feedback():
    backend = InMemoryCustomerBackend(_sample_tickets())
    client = TestClient(
        create_app(ticket_backend=FakeTicketBackend(), customer_backend=backend)
    )

    response = client.post(
        "/customer/tickets/t2/feedback",
        json={"rating": 5, "comments": "Forbidden", "actionId": "feedback-owner"},
        headers={"Authorization": "Bearer customer_2_token"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ticket_not_found"
    assert backend.feedbacks == {}


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


def test_customer_list_projection_excludes_internal_fields():
    backend = InMemoryCustomerBackend(_valid_history_tickets())
    client = TestClient(create_app(ticket_backend=FakeTicketBackend(), customer_backend=backend))

    response = client.get(
        "/customer/tickets", headers={"Authorization": "Bearer valid_customer_token"}
    )

    assert response.status_code == 200
    allowed = {"complaintId", "status", "departmentId", "createdAt", "updatedAt", "resolvedAt"}
    for ticket in response.json()["tickets"]:
        assert set(ticket) == allowed
        assert not {"customerId", "assignedStaffId", "predictedDepartmentId",
                    "predictionConfidence", "routingSource"} & set(ticket)


def test_customer_detail_projects_messages_and_timeline_without_internal_data():
    backend = InMemoryCustomerBackend(_sample_tickets())
    backend.events["t1"] = [
        {"eventId": "model-event", "type": "model_prediction", "actorId": "trusted_ml_v1",
         "fromValue": None, "toValue": "transfer_payment", "createdAt": "2026-08-01T10:02:00Z",
         "predictionConfidence": 0.12, "routingSource": "model"},
        {"eventId": "status-event", "type": "status_transition", "actorId": "staff_999",
         "fromValue": "triaged", "toValue": "in_progress", "createdAt": "2026-08-01T10:10:00Z"},
        {"eventId": "manager-event", "type": "manager_override", "actorId": "manager_1",
         "fromValue": "transfer_payment", "toValue": "fraud_security", "reason": "private",
         "createdAt": "2026-08-01T10:20:00Z"},
        {"eventId": "unknown-event", "type": "internal_note", "actorId": "manager_1",
         "toValue": "private", "createdAt": "2026-08-01T10:21:00Z"},
        {"eventId": "malformed-event", "type": "status_transition", "toValue": "closed"},
    ]
    detail = CustomerWorkflowService(backend).get_ticket_detail("cust_123", "t1")
    payload = detail.model_dump(by_alias=True)

    assert set(payload) == {
        "id", "status", "complaintText", "inputLocale", "priority", "departmentId",
        "createdAt", "updatedAt", "resolvedAt", "messages", "timeline", "feedback",
    }
    assert {"customerId", "predictedDepartmentId", "predictionConfidence", "routingSource"}.isdisjoint(payload)
    assert all(set(message) == {"senderRole", "body", "createdAt"} for message in payload["messages"])
    assert payload["messages"][1]["senderRole"] == "support_team"
    assert all(set(item) <= {"type", "occurredAt", "departmentId"} for item in payload["timeline"])
    assert [item["type"] for item in payload["timeline"]] == [
        "complaint_received", "assigned_to_team", "customer_replied", "review_started",
        "team_replied", "assigned_to_team",
    ]
    assert "staff_999" not in str(payload)
    assert "manager_1" not in str(payload)
    assert "private" not in str(payload)
    assert "model_prediction" not in str(payload)


def test_customer_timeline_ignores_unknown_events_and_has_deterministic_ties():
    backend = InMemoryCustomerBackend(_sample_tickets())
    backend.messages["t1"] = []
    backend.events["t1"] = [
        {"type": "status_transition", "toValue": "resolved", "createdAt": "2026-08-01T10:00:00Z"},
        {"type": "status_transition", "toValue": "in_progress", "createdAt": "2026-08-01T10:00:00Z"},
        {"type": "status_transition", "toValue": "manager_override", "createdAt": "not-a-time"},
        {"type": "manager_override", "toValue": "private", "createdAt": "2026-08-01T10:01:00Z"},
    ]
    timeline = CustomerWorkflowService(backend).get_ticket_detail("cust_123", "t1").timeline
    assert [(item.type, item.occurred_at) for item in timeline] == [
        ("complaint_received", "2026-08-01T10:00:00Z"),
        ("review_started", "2026-08-01T10:00:00Z"),
        ("complaint_resolved", "2026-08-01T10:00:00Z"),
    ]


def test_customer_history_pages_with_stable_tie_break_and_cursor():
    tickets = _valid_history_tickets()
    tickets[0]["createdAt"] = "2026-08-01T10:00:00Z"
    tickets[1]["createdAt"] = "2026-08-01T10:00:00Z"
    tickets[1]["updatedAt"] = "2026-08-01T10:30:00Z"
    tickets[1]["resolvedAt"] = "2026-08-01T10:20:00Z"
    backend = InMemoryCustomerBackend(tickets)
    client = TestClient(create_app(ticket_backend=FakeTicketBackend(), customer_backend=backend))
    headers = {"Authorization": "Bearer valid_customer_token"}

    first = client.get("/customer/tickets?pageSize=1", headers=headers)
    assert first.status_code == 200
    first_page = first.json()
    assert first_page["tickets"][0]["complaintId"] == "ticket_" + "2" * 32
    assert first_page["hasMore"] is True

    second = client.get(
        f"/customer/tickets?pageSize=1&cursor={first_page['nextCursor']}",
        headers=headers,
    )
    assert second.status_code == 200
    second_page = second.json()
    assert second_page["tickets"][0]["complaintId"] == "ticket_" + "1" * 32
    assert second_page["hasMore"] is False
    assert second_page["nextCursor"] is None


def test_customer_history_empty_exact_boundary_and_read_bound():
    class RecordingBackend(InMemoryCustomerBackend):
        def __init__(self, initial_tickets: list[dict[str, Any]] | None = None) -> None:
            super().__init__(initial_tickets)
            self.requests: list[tuple[int, CustomerHistoryCursor | None]] = []

        def list_customer_tickets(
            self,
            customer_id: str,
            page_size: int,
            cursor: CustomerHistoryCursor | None,
        ) -> list[dict[str, Any]]:
            self.requests.append((page_size, cursor))
            return super().list_customer_tickets(customer_id, page_size, cursor)

    empty_backend = RecordingBackend()
    empty_client = TestClient(
        create_app(ticket_backend=FakeTicketBackend(), customer_backend=empty_backend)
    )
    empty = empty_client.get(
        "/customer/tickets?pageSize=1",
        headers={"Authorization": "Bearer valid_customer_token"},
    )
    assert empty.status_code == 200
    assert empty.json() == {"tickets": [], "nextCursor": None, "hasMore": False}
    assert empty_backend.requests == [(1, None)]

    exact_backend = RecordingBackend(_valid_history_tickets()[:2])
    exact_client = TestClient(
        create_app(ticket_backend=FakeTicketBackend(), customer_backend=exact_backend)
    )
    exact = exact_client.get(
        "/customer/tickets?pageSize=2",
        headers={"Authorization": "Bearer valid_customer_token"},
    )
    assert exact.status_code == 200
    assert len(exact.json()["tickets"]) == 2
    assert exact.json()["hasMore"] is False
    assert exact.json()["nextCursor"] is None
    assert exact_backend.requests == [(2, None)]


def test_customer_history_insertion_before_next_page_does_not_duplicate_or_skip():
    tickets = _valid_history_tickets()
    backend = InMemoryCustomerBackend(tickets)
    client = TestClient(create_app(ticket_backend=FakeTicketBackend(), customer_backend=backend))
    headers = {"Authorization": "Bearer valid_customer_token"}

    first = client.get("/customer/tickets?pageSize=1", headers=headers).json()
    backend.tickets["ticket_" + "9" * 32] = {
        **tickets[0],
        "id": "ticket_" + "9" * 32,
        "createdAt": "2026-08-03T00:00:00Z",
        "updatedAt": "2026-08-03T00:00:00Z",
    }
    second = client.get(
        f"/customer/tickets?pageSize=1&cursor={first['nextCursor']}",
        headers=headers,
    ).json()
    assert second["tickets"][0]["complaintId"] == "ticket_" + "2" * 32
    assert second["tickets"][0]["complaintId"] != first["tickets"][0]["complaintId"]


@pytest.mark.parametrize("query", [
    "status=submitted",
    "departmentId=card_atm",
    "createdFrom=2026-01-01T00:00:00Z",
    "createdTo=2026-01-01T00:00:00Z",
    "search=anything",
    "reference=ticket_" + "a" * 32,
    "sort=createdAt",
    "pageSize=1&pageSize=2",
])
def test_customer_history_rejects_unsupported_or_duplicate_query(query: str):
    backend = InMemoryCustomerBackend(_valid_history_tickets())
    client = TestClient(create_app(ticket_backend=FakeTicketBackend(), customer_backend=backend))
    response = client.get(
        f"/customer/tickets?{query}",
        headers={"Authorization": "Bearer valid_customer_token"},
    )
    assert response.status_code == 422


def test_customer_history_rejects_cursor_before_query_without_leaking_details():
    backend = InMemoryCustomerBackend(_valid_history_tickets())
    client = TestClient(create_app(ticket_backend=FakeTicketBackend(), customer_backend=backend))
    response = client.get(
        "/customer/tickets?cursor=not-a-cursor",
        headers={"Authorization": "Bearer invalid"},
    )
    assert response.status_code == 401
    assert "cursor" not in response.text.lower()


def test_customer_history_malformed_owned_ticket_fails_closed():
    tickets = _valid_history_tickets()
    tickets[0]["updatedAt"] = "not-a-timestamp"
    client = TestClient(
        create_app(
            ticket_backend=FakeTicketBackend(),
            customer_backend=InMemoryCustomerBackend(tickets),
        )
    )
    response = client.get(
        "/customer/tickets",
        headers={"Authorization": "Bearer valid_customer_token"},
    )
    assert response.status_code == 503
    assert "not-a-timestamp" not in response.text


def test_customer_history_cursor_has_stable_vectors_and_rejects_alternates():
    cursor = CustomerHistoryCursor(
        datetime.fromisoformat("2026-08-01T00:00:00+00:00"),
        "ticket_" + "a" * 32,
    )
    assert customer_history_binding("cust_123") == "fdf71536d14b5ecf4fe0d2557eba7923e51c564743fcedd36d9350fe1ff92d19"
    assert customer_history_contract_fingerprint() == "4ac5ad4a38cccd46411ad7c740dc66057e3bddae2e5cc3f86b6969f90ae0eeae"
    encoded = encode_customer_history_cursor(cursor, "cust_123")
    assert encoded == "eyJ2IjoxLCJjdXN0b21lckJpbmRpbmciOiJmZGY3MTUzNmQxNGI1ZWNmNGZlMGQyNTU3ZWJhNzkyM2U1MWM1NjQ3NDNmY2VkZDM2ZDkzNTBmZTFmZjkyZDE5IiwiY29udHJhY3QiOiI0YWM1YWQ0YTM4Y2NjZDQ2NDExYWQ3Yzc0MGRjNjYwNTdlM2JkZGFlMmU1Y2MzZjg2YjY5NjlmOTBhZTBlZWFlIiwiY3JlYXRlZEF0IjoiMjAyNi0wOC0wMVQwMDowMDowMFoiLCJjb21wbGFpbnRJZCI6InRpY2tldF9hYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYSJ9"
    assert decode_customer_history_cursor(encoded, "cust_123").complaint_id == cursor.complaint_id
    assert decode_customer_history_cursor(encoded, "cust_123").created_at == cursor.created_at
    for alternate in (encoded + "=", encoded.replace("A", " ", 1)):
        with pytest.raises(ValueError):
            decode_customer_history_cursor(alternate, "cust_123")
