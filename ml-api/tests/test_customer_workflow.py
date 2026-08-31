"""Pytest suite for Day 15 Customer Workflow API and Backend Service."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.customer_workflow import (
    CUSTOMER_HISTORY_DEPARTMENTS,
    CUSTOMER_HISTORY_STATUSES,
    CustomerHistoryCursor,
    CustomerHistoryFilters,
    CustomerMessageIdempotencyConflict,
    CustomerWorkflowService,
    FirebaseAdminCustomerBackend,
    InMemoryCustomerBackend,
    customer_history_binding,
    customer_history_contract_fingerprint,
    decode_customer_history_cursor,
    encode_customer_history_cursor,
)
from app.main import create_app
from app.schemas import CustomerMessageRequest, CustomerTicketFeedback
from app.ticketing import PersistenceError

T1 = "ticket_" + "1" * 32
T2 = "ticket_" + "2" * 32
T3 = "ticket_" + "3" * 32


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
            "id": T1,
            "customerId": "cust_123",
            "status": "in_progress",
            "complaintText": "My money transfer failed card number 1234567890123456",
            "inputLocale": "en",
            "predictedDepartmentId": "transfer_payment",
            "assignedDepartmentId": "transfer_payment",
            "priority": "normal",
            "departmentId": "transfer_payment",
            "createdAt": "2026-08-01T10:00:00Z",
            "updatedAt": "2026-08-01T10:30:00Z",
            "resolvedAt": None,
            "messages": [
                {
                    "id": "msg_1",
                    "authorId": "cust_123",
                    "authorRole": "customer",
                    "body": "Please help check this transfer",
                    "visibility": "participants",
                    "createdAt": "2026-08-01T10:05:00Z",
                },
                {
                    "id": "msg_2",
                    "authorId": "staff_999",
                    "authorRole": "staff",
                    "body": "We are looking into it.",
                    "visibility": "participants",
                    "createdAt": "2026-08-01T10:15:00Z",
                },
            ],
        },
        {
            "id": T2,
            "customerId": "cust_123",
            "status": "resolved",
            "complaintText": "ATM swallowed my card",
            "inputLocale": "en",
            "predictedDepartmentId": "card_atm",
            "assignedDepartmentId": "card_atm",
            "priority": "high",
            "departmentId": "card_atm",
            "createdAt": "2026-07-28T09:00:00Z",
            "updatedAt": "2026-07-29T11:00:00Z",
            "resolvedAt": "2026-07-29T11:00:00Z",
            "messages": [],
        },
        {
            "id": T3,
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
        f"/customer/tickets/{T1}",
        headers={"Authorization": "Bearer valid_customer_token"},
    )
    assert res.status_code == 200
    detail = res.json()
    assert detail["id"] == T1
    assert detail["status"] == "in_progress"
    assert len(detail["messages"]) == 2


def test_customer_detail_maps_complete_canonical_staff_message_body():
    backend = InMemoryCustomerBackend(_sample_tickets())
    backend.messages[T1] = [
        {
            "id": "canonical-staff-message",
            "authorId": "staff_999",
            "authorRole": "staff",
            "body": "Complete canonical staff reply.",
            "visibility": "participants",
            "createdAt": "2026-08-01T10:15:00Z",
        }
    ]

    detail = CustomerWorkflowService(backend).get_ticket_detail("cust_123", T1)

    assert detail.messages[0].sender_role == "support_team"
    assert detail.messages[0].body == "Complete canonical staff reply."
    assert "staff_999" not in detail.model_dump_json()


def test_customer_detail_rejects_incomplete_message_instead_of_blank_body():
    backend = InMemoryCustomerBackend(_sample_tickets())
    backend.messages[T1] = [
        {
            "id": "malformed-message",
            "senderRole": "staff",
            "createdAt": "2026-08-01T10:15:00Z",
        }
    ]

    with pytest.raises(PersistenceError):
        CustomerWorkflowService(backend).get_ticket_detail("cust_123", T1)


def test_customer_detail_malformed_message_is_safe_503():
    backend = InMemoryCustomerBackend(_sample_tickets())
    backend.messages[T1] = [{"id": "malformed-message", "body": None}]
    client = TestClient(
        create_app(ticket_backend=FakeTicketBackend(), customer_backend=backend)
    )

    response = client.get(
        f"/customer/tickets/{T1}",
        headers={"Authorization": "Bearer valid_customer_token"},
    )

    assert response.status_code == 503
    assert "malformed-message" not in response.text


def test_cross_customer_ticket_does_not_leak_existence():
    backend = InMemoryCustomerBackend(_sample_tickets())
    app = create_app(
        ticket_backend=FakeTicketBackend(),
        customer_backend=backend,
    )
    client = TestClient(app)

    # Customer 1 trying to access Customer 2's ticket T3
    res = client.get(
        f"/customer/tickets/{T3}",
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
        f"/customer/tickets/{T1}/messages",
        json=payload,
        headers={"Authorization": "Bearer valid_customer_token"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["senderRole"] == "customer"
    assert "[REDACTED]" in body["body"]
    assert "MyPassword123" not in body["body"]
    stored = backend.messages[T1][-1]
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
        f"/customer/tickets/{T2}/feedback",
        json=payload,
        headers={"Authorization": "Bearer valid_customer_token"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "feedback_submitted"
    assert body["ticketId"] == T2

    detail = client.get(
        f"/customer/tickets/{T2}",
        headers={"Authorization": "Bearer valid_customer_token"},
    )
    assert detail.status_code == 200
    assert detail.json()["feedback"] == {
        "rating": 5,
        "comments": "Great service, resolved quickly!",
        "submittedAt": backend.tickets[T2]["feedback"]["submittedAt"],
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
        f"/customer/tickets/{T2}/feedback", json=first_payload, headers=headers
    )
    retry = client.post(
        f"/customer/tickets/{T2}/feedback", json=first_payload, headers=headers
    )
    original_feedback = dict(backend.tickets[T2]["feedback"])
    duplicate = client.post(
        f"/customer/tickets/{T2}/feedback",
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
    assert backend.tickets[T2]["feedback"] == original_feedback
    assert backend.feedbacks[f"fb_{T2}"]["rating"] == 5
    assert backend.feedbacks[f"fb_{T2}"]["comments"] == "Original feedback."
    assert list(backend.actions) == [(T2, "feedback:feedback-retry-001")]


def test_cross_customer_cannot_submit_feedback():
    backend = InMemoryCustomerBackend(_sample_tickets())
    client = TestClient(
        create_app(ticket_backend=FakeTicketBackend(), customer_backend=backend)
    )

    response = client.post(
        f"/customer/tickets/{T2}/feedback",
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

    # Ticket T1 is in_progress, not resolved
    payload = {
        "rating": 4,
        "comments": "Not yet resolved",
        "actionId": "feedback-action-002",
    }
    res = client.post(
        f"/customer/tickets/{T1}/feedback",
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

    first = client.post(f"/customer/tickets/{T1}/messages", json=payload, headers=headers)
    second = client.post(f"/customer/tickets/{T1}/messages", json=payload, headers=headers)

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert len(backend.messages[T1]) == 3


def test_message_body_is_not_validated_before_authentication():
    backend = InMemoryCustomerBackend(_sample_tickets())
    client = TestClient(
        create_app(ticket_backend=FakeTicketBackend(), customer_backend=backend)
    )

    response = client.post(
        f"/customer/tickets/{T1}/messages",
        json={"text": None, "actionId": "bad"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_required"


def test_message_body_is_not_validated_before_owned_ticket_resolution():
    backend = InMemoryCustomerBackend(_sample_tickets())
    client = TestClient(
        create_app(ticket_backend=FakeTicketBackend(), customer_backend=backend)
    )

    response = client.post(
        f"/customer/tickets/{T3}/messages",
        json={"text": None, "actionId": "bad"},
        headers={"Authorization": "Bearer valid_customer_token"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ticket_not_found"


def test_message_fingerprint_binds_original_normalized_text_before_redaction():
    backend = InMemoryCustomerBackend(_sample_tickets())
    service = CustomerWorkflowService(backend)
    first = service.send_message(
        "cust_123",
        T1,
        CustomerMessageRequest(
            messageText="password: first-secret", actionId="message-redact-001"
        ),
    )
    assert first["body"] == "password [REDACTED]"

    with pytest.raises(CustomerMessageIdempotencyConflict):
        service.send_message(
            "cust_123",
            T1,
            CustomerMessageRequest(
                messageText="password: second-secret", actionId="message-redact-001"
            ),
        )
    assert len(backend.messages[T1]) == 3


def test_message_action_and_message_must_exist_as_an_atomic_pair():
    backend = InMemoryCustomerBackend(_sample_tickets())
    service = CustomerWorkflowService(backend)
    request = CustomerMessageRequest(
        messageText="Persist exactly once", actionId="message-pair-001"
    )
    service.send_message("cust_123", T1, request)
    backend.messages[T1] = [
        item for item in backend.messages[T1] if item["id"] != request.action_id
    ]

    with pytest.raises(PersistenceError):
        service.send_message("cust_123", T1, request)


def test_customer_message_action_reuse_conflicts_across_text_and_ticket():
    backend = InMemoryCustomerBackend(_sample_tickets())
    client = TestClient(
        create_app(ticket_backend=FakeTicketBackend(), customer_backend=backend)
    )
    headers = {"Authorization": "Bearer valid_customer_token"}
    payload = {"messageText": "First message", "actionId": "message-context-001"}

    assert client.post(f"/customer/tickets/{T1}/messages", json=payload, headers=headers).status_code == 200
    changed = client.post(
        f"/customer/tickets/{T1}/messages",
        json={**payload, "messageText": "Changed message"},
        headers=headers,
    )
    other_ticket = client.post(
        f"/customer/tickets/{T2}/messages", json=payload, headers=headers
    )

    assert changed.status_code == other_ticket.status_code == 409
    assert changed.json()["error"]["code"] == "idempotency_conflict"
    assert other_ticket.json()["error"]["code"] == "idempotency_conflict"
    assert len(backend.messages[T1]) == 3
    assert backend.messages[T2] == []


def test_customer_message_rejects_text_alias_and_malformed_action_record():
    backend = InMemoryCustomerBackend(_sample_tickets())
    client = TestClient(
        create_app(ticket_backend=FakeTicketBackend(), customer_backend=backend)
    )
    headers = {"Authorization": "Bearer valid_customer_token"}
    alias = client.post(
        f"/customer/tickets/{T1}/messages",
        json={"text": "Not accepted", "actionId": "message-alias-001"},
        headers=headers,
    )
    assert alias.status_code == 422

    backend.message_actions["message-corrupt-001"] = {
        "type": "customer_message",
        "fingerprint": "not-a-fingerprint",
        "result": {"senderRole": "customer", "body": "x", "createdAt": "2026-08-01T00:00:00Z"},
    }
    corrupt = client.post(
        f"/customer/tickets/{T1}/messages",
        json={"messageText": "Retry", "actionId": "message-corrupt-001"},
        headers=headers,
    )
    assert corrupt.status_code == 503
    assert len(backend.messages[T1]) == 2


def test_customer_message_read_is_bounded_and_tie_breaks_by_message_id():
    backend = InMemoryCustomerBackend(_sample_tickets())
    backend.messages[T1] = [
        {
            "id": f"message-{index:03d}",
            "authorId": "cust_123",
            "authorRole": "customer",
            "body": f"Message {index}",
            "visibility": "participants",
            "createdAt": "2026-08-01T10:00:00Z",
        }
        for index in range(100)
    ]
    detail = CustomerWorkflowService(backend).get_ticket_detail("cust_123", T1)
    assert len(detail.messages) == 100
    assert detail.messages[0].body == "Message 0"

    backend.messages[T1].append(dict(backend.messages[T1][0], id="message-100"))
    with pytest.raises(PersistenceError):
        CustomerWorkflowService(backend).get_ticket_detail("cust_123", T1)


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
        f"/customer/tickets/{T1}/messages",
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
    assert backend.messages[T1] == _sample_tickets()[0]["messages"]


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
    backend.events[T1] = [
        {"eventId": "model-event", "type": "model_prediction", "actorId": "trusted_ml_v1",
         "actorRole": "system",
         "fromValue": None, "toValue": "transfer_payment", "createdAt": "2026-08-01T10:02:00Z",
         "predictionConfidence": 0.12, "routingSource": "model"},
        {"eventId": "status-event", "type": "status_transition", "actorId": "staff_999",
         "actorRole": "staff",
         "fromValue": "triaged", "toValue": "in_progress", "createdAt": "2026-08-01T10:10:00Z"},
        {"eventId": "manager-event", "type": "manager_override", "actorId": "manager_1",
         "actorRole": "manager",
         "fromValue": "transfer_payment", "toValue": "fraud_security", "reason": "private",
         "createdAt": "2026-08-01T10:20:00Z"},
    ]
    detail = CustomerWorkflowService(backend).get_ticket_detail("cust_123", T1)
    payload = detail.model_dump(by_alias=True)

    assert set(payload) == {
        "id", "status", "complaintText", "inputLocale", "departmentId",
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


def test_customer_detail_fails_closed_for_malformed_ticket_and_feedback():
    backend = InMemoryCustomerBackend(_sample_tickets())
    backend.tickets[T1]["updatedAt"] = "2026-08-01T10:30:00+00:00"
    service = CustomerWorkflowService(backend)
    with pytest.raises(PersistenceError):
        service.get_ticket_detail("cust_123", T1)

    backend = InMemoryCustomerBackend(_sample_tickets())
    backend.tickets[T2]["feedback"] = {
        "rating": True,
        "comments": "Unsafe",
        "submittedAt": "2026-07-29T11:00:00Z",
    }
    with pytest.raises(PersistenceError):
        CustomerWorkflowService(backend).get_ticket_detail("cust_123", T2)


def test_customer_detail_rejects_invalid_known_internal_persistence_fields():
    backend = InMemoryCustomerBackend(_sample_tickets())
    backend.tickets[T1]["predictionConfidence"] = True
    with pytest.raises(PersistenceError):
        CustomerWorkflowService(backend).get_ticket_detail("cust_123", T1)

    backend = InMemoryCustomerBackend(_sample_tickets())
    backend.events[T1] = [{
        "type": "model_prediction", "actorId": "trusted_ml_v1", "actorRole": "system",
        "fromValue": None, "toValue": "transfer_payment", "createdAt": "2026-08-01T10:02:00Z",
        "predictionConfidence": True,
    }]
    with pytest.raises(PersistenceError):
        CustomerWorkflowService(backend).get_ticket_detail("cust_123", T1)


def test_customer_detail_feedback_response_model_rejects_coercible_ratings():
    base = {
        "comments": None,
        "submittedAt": "2026-07-29T11:00:00Z",
    }
    for rating in (True, 1.0, "1"):
        with pytest.raises(ValueError):
            CustomerTicketFeedback.model_validate({**base, "rating": rating})


def test_customer_detail_rejects_event_ticket_binding_mismatch():
    backend = InMemoryCustomerBackend(_sample_tickets())
    backend.events[T1] = [{
        "ticketId": T2,
        "type": "status_transition",
        "actorId": "staff_999",
        "actorRole": "staff",
        "fromValue": "triaged",
        "toValue": "in_progress",
        "createdAt": "2026-08-01T10:10:00Z",
    }]
    with pytest.raises(PersistenceError):
        CustomerWorkflowService(backend).get_ticket_detail("cust_123", T1)


def test_customer_detail_accepts_manual_review_prediction_without_assignment():
    backend = InMemoryCustomerBackend(_sample_tickets())
    backend.events[T1] = [{
        "type": "model_prediction", "actorId": "trusted_ml_v1", "actorRole": "system",
        "fromValue": None, "toValue": None, "predictedDepartmentId": "transfer_payment",
        "predictionConfidence": 0.12, "routingSource": "manual_review",
        "createdAt": "2026-08-01T10:02:00Z",
    }]
    detail = CustomerWorkflowService(backend).get_ticket_detail("cust_123", T1)
    assert detail.timeline[0].type == "complaint_received"
    assert "assigned_to_team" not in {item.type for item in detail.timeline}


def test_customer_detail_accepts_myanmar_language_metadata_for_manual_review():
    backend = InMemoryCustomerBackend(_sample_tickets())
    backend.tickets[T1].update(
        {
            "inputLocale": "my",
            "detectedLanguage": "my",
            "routingSource": "manual_review",
            "departmentId": None,
            "status": "submitted",
        }
    )
    detail = CustomerWorkflowService(backend).get_ticket_detail("cust_123", T1)
    assert detail.input_locale == "my"
    assert detail.department_id is None


def test_customer_timeline_rejects_unknown_or_malformed_events():
    backend = InMemoryCustomerBackend(_sample_tickets())
    backend.messages[T1] = []
    backend.events[T1] = [
        {"type": "status_transition", "toValue": "resolved", "createdAt": "2026-08-01T10:00:00Z"},
        {"type": "status_transition", "toValue": "in_progress", "createdAt": "2026-08-01T10:00:00Z"},
        {"type": "status_transition", "toValue": "manager_override", "createdAt": "not-a-time"},
        {"type": "manager_override", "toValue": "private", "createdAt": "2026-08-01T10:01:00Z"},
    ]
    with pytest.raises(PersistenceError):
        CustomerWorkflowService(backend).get_ticket_detail("cust_123", T1)


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
            filters: CustomerHistoryFilters,
        ) -> list[dict[str, Any]]:
            self.requests.append((page_size, cursor))
            return super().list_customer_tickets(customer_id, page_size, cursor, filters)

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
    "status=unknown",
    "departmentId=unknown",
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


@pytest.mark.parametrize("query", [
    "status=",
    "departmentId=",
    "status= submitted",
    "status=SUBMITTED",
    "status=submitted,status=closed",
    "departmentId=card_atm&departmentId=card_atm",
    "pageSize=01",
    "pageSize=+1",
])
def test_customer_history_rejects_invalid_filter_and_numeric_forms(query: str):
    client = TestClient(create_app(ticket_backend=FakeTicketBackend(), customer_backend=InMemoryCustomerBackend(_valid_history_tickets())))
    response = client.get(f"/customer/tickets?{query}", headers={"Authorization": "Bearer valid_customer_token"})
    assert response.status_code == 422


@pytest.mark.parametrize("query, expected", [
    ("status=in_progress", {"ticket_" + "1" * 32}),
    ("departmentId=card_atm", {"ticket_" + "2" * 32}),
    ("status=resolved&departmentId=card_atm", {"ticket_" + "2" * 32}),
])
def test_customer_history_applies_server_side_filters(query: str, expected: set[str]):
    client = TestClient(create_app(ticket_backend=FakeTicketBackend(), customer_backend=InMemoryCustomerBackend(_valid_history_tickets())))
    response = client.get(f"/customer/tickets?{query}", headers={"Authorization": "Bearer valid_customer_token"})
    assert response.status_code == 200
    assert {row["complaintId"] for row in response.json()["tickets"]} == expected


@pytest.mark.parametrize("filters, expected_equalities", [
    (CustomerHistoryFilters(), [("customerId", "cust_123")]),
    (CustomerHistoryFilters(status="resolved"), [("customerId", "cust_123"), ("status", "resolved")]),
    (CustomerHistoryFilters(department_id="card_atm"), [("customerId", "cust_123"), ("departmentId", "card_atm")]),
    (CustomerHistoryFilters(status="resolved", department_id="card_atm"), [("customerId", "cust_123"), ("status", "resolved"), ("departmentId", "card_atm")]),
])
def test_firestore_customer_history_query_shape_is_bounded_and_server_side(
    filters: CustomerHistoryFilters,
    expected_equalities: list[tuple[str, str]],
):
    class Query:
        def __init__(self) -> None:
            self.where_calls: list[Any] = []
            self.order_calls: list[tuple[str, str]] = []
            self.limit_value: int | None = None

        def where(self, **kwargs: Any) -> Query:
            self.where_calls.append(kwargs["filter"])
            return self

        def order_by(self, field: str, *, direction: str) -> Query:
            self.order_calls.append((field, direction))
            return self

        def limit(self, value: int) -> Query:
            self.limit_value = value
            return self

        def stream(self) -> list[Any]:
            return []

    class Database:
        def __init__(self) -> None:
            self.query = Query()

        def collection(self, _name: str) -> Query:
            return self.query

    database = Database()
    FirebaseAdminCustomerBackend(db=database).list_customer_tickets("cust_123", 7, None, filters)
    assert [(item.field_path, item.value) for item in database.query.where_calls] == expected_equalities
    assert database.query.order_calls == [("createdAt", "DESCENDING"), ("__name__", "DESCENDING")]
    assert database.query.limit_value == 8


def test_customer_history_unauthorized_filter_is_not_inspected_or_queried():
    class NoQueryBackend(InMemoryCustomerBackend):
        def list_customer_tickets(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
            raise AssertionError("query must not execute")

    client = TestClient(create_app(ticket_backend=FakeTicketBackend(), customer_backend=NoQueryBackend(_valid_history_tickets())))
    response = client.get("/customer/tickets?status=bad", headers={"Authorization": "Bearer invalid"})
    assert response.status_code == 401


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
    filters = CustomerHistoryFilters(status="resolved", department_id="card_atm")
    cursor = CustomerHistoryCursor(
        datetime.fromisoformat("2026-08-01T00:00:00+00:00"),
        "ticket_" + "a" * 32,
        filters,
    )
    assert customer_history_binding("cust_123") == "e256a888d7815dc06eb189a24848b87f3f95755f48b76911da055cd487e8a377"
    assert customer_history_contract_fingerprint(CustomerHistoryFilters()) == "1869d2b3ae1a579d8346dda166a5d48da5f16b0ddb75ff3c9c709732d4de4c94"
    assert customer_history_contract_fingerprint(CustomerHistoryFilters(status="resolved")) == "f77494629c2766e4e9f8dc1d60f3b5f1bc6e5393a47ded64c9e6d0e48a548264"
    assert customer_history_contract_fingerprint(CustomerHistoryFilters(department_id="card_atm")) == "9acab90e393a7ea76983b1bfbe2c7159e76cb28fc0c9019995d73ada3fc28821"
    assert customer_history_contract_fingerprint(filters) == "4206abb38e2642d1e48d2f4b9a64592901a98ba638aaa165a0b21724af8ed43d"
    encoded = encode_customer_history_cursor(cursor, "cust_123", filters)
    assert encoded.startswith("eyJ2Ijoy")
    assert decode_customer_history_cursor(encoded, "cust_123", filters).complaint_id == cursor.complaint_id
    assert decode_customer_history_cursor(encoded, "cust_123", filters).created_at == cursor.created_at
    for alternate in (encoded + "=", encoded.replace("A", " ", 1)):
        with pytest.raises(ValueError):
            decode_customer_history_cursor(alternate, "cust_123", filters)
    with pytest.raises(ValueError):
        decode_customer_history_cursor(encoded, "cust_123", CustomerHistoryFilters())


def test_customer_history_contract_binds_all_49_exact_filter_states():
    filters = [CustomerHistoryFilters()]
    filters.extend(CustomerHistoryFilters(status=status) for status in CUSTOMER_HISTORY_STATUSES)
    filters.extend(CustomerHistoryFilters(department_id=department) for department in CUSTOMER_HISTORY_DEPARTMENTS)
    filters.extend(
        CustomerHistoryFilters(status=status, department_id=department)
        for status in CUSTOMER_HISTORY_STATUSES
        for department in CUSTOMER_HISTORY_DEPARTMENTS
    )
    fingerprints = [customer_history_contract_fingerprint(item) for item in filters]
    assert len(filters) == 49
    assert len(set(fingerprints)) == 49
    assert fingerprints == [customer_history_contract_fingerprint(item) for item in filters]
