"""Integration tests for production Firestore adapters against the local emulator."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore

from app.customer_workflow import (
    CustomerWorkflowService,
    FirebaseAdminCustomerBackend,
    TicketNotFound,
)
from app.manager_workflow import (
    FirebaseAdminManagerBackend,
)
from app.manager_workflow import (
    TicketNotFound as ManagerTicketNotFound,
)
from app.schemas import CustomerFeedbackRequest, CustomerMessageRequest
from app.staff_workflow import (
    FirebaseAdminStaffBackend,
    InvalidTransition,
    StaffActor,
    StaffTicketNotFound,
)

pytestmark = pytest.mark.skipif(
    not os.getenv("FIRESTORE_EMULATOR_HOST"),
    reason="requires the local Firestore Emulator",
)


@pytest.fixture(scope="session")
def emulator_db():
    client = firestore.Client(
        project=os.getenv("GCLOUD_PROJECT", "demo-complaintguard"),
        credentials=AnonymousCredentials(),
    )
    try:
        yield client
    finally:
        client.close()


def ticket_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def base_ticket(*, customer_id: str, department_id: str | None, status: str) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "customerId": customer_id,
        "complaintText": "Synthetic emulator complaint",
        "inputLocale": "en",
        "departmentId": department_id,
        "assignedStaffId": None,
        "status": status,
        "priority": "normal",
        "predictedDepartmentId": None,
        "predictionConfidence": None,
        "routingSource": "pending" if department_id is None else "manual_review",
        "escalated": False,
        "resolutionSummary": None,
        "createdAt": now,
        "updatedAt": now,
        "resolvedAt": now if status == "resolved" else None,
    }


def test_customer_ownership_and_message_transaction_are_emulator_backed(emulator_db):
    owned_id = ticket_id("customer-owned")
    foreign_id = ticket_id("customer-foreign")
    emulator_db.collection("tickets").document(owned_id).set(
        base_ticket(
            customer_id="customer-a", department_id="card_atm", status="in_progress"
        )
    )
    emulator_db.collection("tickets").document(foreign_id).set(
        base_ticket(customer_id="customer-b", department_id=None, status="submitted")
    )
    backend = FirebaseAdminCustomerBackend(db=emulator_db)
    service = CustomerWorkflowService(backend)

    assert {item.id for item in service.list_tickets("customer-a")} == {owned_id}
    with pytest.raises(TicketNotFound):
        service.get_ticket_detail("customer-a", foreign_id)

    request = CustomerMessageRequest(
        messageText="Synthetic follow-up",
        actionId="customer-message-action",
    )
    first = service.send_message("customer-a", owned_id, request)
    second = service.send_message("customer-a", owned_id, request)
    assert first == second
    messages = list(
        emulator_db.collection("tickets")
        .document(owned_id)
        .collection("messages")
        .stream()
    )
    actions = list(
        emulator_db.collection("tickets")
        .document(owned_id)
        .collection("actions")
        .stream()
    )
    assert [item.id for item in messages] == ["customer-message-action"]
    assert [item.id for item in actions] == ["message_customer-message-action"]

    with pytest.raises(TicketNotFound):
        service.send_message("customer-b", owned_id, request)
    assert (
        len(
            list(
                emulator_db.collection("tickets")
                .document(owned_id)
                .collection("messages")
                .stream()
            )
        )
        == 1
    )


def test_customer_feedback_transaction_and_retry_are_emulator_backed(emulator_db):
    resolved_id = ticket_id("customer-resolved")
    emulator_db.collection("tickets").document(resolved_id).set(
        base_ticket(
            customer_id="customer-a", department_id="card_atm", status="resolved"
        )
    )
    service = CustomerWorkflowService(FirebaseAdminCustomerBackend(db=emulator_db))
    request = CustomerFeedbackRequest(
        rating=5,
        comments="Synthetic feedback",
        actionId="customer-feedback-action",
    )

    first = service.submit_feedback("customer-a", resolved_id, request)
    second = service.submit_feedback("customer-a", resolved_id, request)
    assert first == second
    feedback = emulator_db.collection("feedback").document(f"fb_{resolved_id}").get()
    ticket = emulator_db.collection("tickets").document(resolved_id).get()
    assert feedback.exists and feedback.get("rating") == 5
    assert ticket.get("feedback.rating") == 5
    actions = list(ticket.reference.collection("actions").stream())
    assert [item.id for item in actions] == ["feedback_customer-feedback-action"]


def test_staff_mutations_audit_retry_and_rollback_are_emulator_backed(emulator_db):
    reply_id = ticket_id("staff-reply")
    transition_id = ticket_id("staff-transition")
    request_id = ticket_id("staff-request")
    foreign_id = ticket_id("staff-foreign")
    tickets = emulator_db.collection("tickets")
    tickets.document(reply_id).set(
        base_ticket(
            customer_id="customer-a", department_id="card_atm", status="in_progress"
        )
    )
    tickets.document(transition_id).set(
        base_ticket(
            customer_id="customer-a", department_id="card_atm", status="triaged"
        )
    )
    tickets.document(request_id).set(
        base_ticket(
            customer_id="customer-a", department_id="card_atm", status="in_progress"
        )
    )
    tickets.document(foreign_id).set(
        base_ticket(
            customer_id="customer-b", department_id="loan_credit", status="in_progress"
        )
    )
    backend = FirebaseAdminStaffBackend(db=emulator_db)
    actor = StaffActor(uid="staff-card", department_id="card_atm")

    reply = backend.add_reply(
        ticket_id=reply_id,
        actor=actor,
        body="Synthetic staff reply",
        action_id="staff-reply-action",
    )
    duplicate_reply = backend.add_reply(
        ticket_id=reply_id,
        actor=actor,
        body="Synthetic staff reply",
        action_id="staff-reply-action",
    )
    assert reply.duplicate is False and duplicate_reply.duplicate is True
    assert (
        tickets.document(reply_id)
        .collection("messages")
        .document("staff-reply-action")
        .get()
        .exists
    )
    assert (
        tickets.document(reply_id)
        .collection("events")
        .document("reply_staff-reply-action")
        .get()
        .exists
    )

    transition = backend.transition_ticket(
        ticket_id=transition_id,
        actor=actor,
        to_status="in_progress",
        resolution_summary=None,
        action_id="staff-transition-action",
    )
    duplicate_transition = backend.transition_ticket(
        ticket_id=transition_id,
        actor=actor,
        to_status="in_progress",
        resolution_summary=None,
        action_id="staff-transition-action",
    )
    assert transition.duplicate is False and duplicate_transition.duplicate is True
    assert tickets.document(transition_id).get().get("status") == "in_progress"

    request = backend.request_action(
        ticket_id=request_id,
        actor=actor,
        request_type="request_escalation",
        reason="Synthetic escalation request",
        action_id="staff-request-action",
    )
    duplicate_request = backend.request_action(
        ticket_id=request_id,
        actor=actor,
        request_type="request_escalation",
        reason="Synthetic escalation request",
        action_id="staff-request-action",
    )
    assert request.duplicate is False and duplicate_request.duplicate is True

    with pytest.raises(StaffTicketNotFound):
        backend.add_reply(
            ticket_id=foreign_id,
            actor=actor,
            body="Must not persist",
            action_id="foreign-reply-action",
        )
    assert (
        not tickets.document(foreign_id)
        .collection("messages")
        .document("foreign-reply-action")
        .get()
        .exists
    )

    invalid_id = ticket_id("staff-invalid-transition")
    tickets.document(invalid_id).set(
        base_ticket(
            customer_id="customer-a", department_id="card_atm", status="triaged"
        )
    )
    with pytest.raises(InvalidTransition):
        backend.transition_ticket(
            ticket_id=invalid_id,
            actor=actor,
            to_status="resolved",
            resolution_summary="Must not persist",
            action_id="invalid-transition-action",
        )
    invalid_ticket = tickets.document(invalid_id).get()
    assert invalid_ticket.get("status") == "triaged"
    assert (
        not invalid_ticket.reference.collection("events")
        .document("invalid-transition-action")
        .get()
        .exists
    )


def test_manager_override_audit_retry_and_missing_ticket_rollback_are_emulator_backed(
    emulator_db,
):
    managed_id = ticket_id("manager-ticket")
    tickets = emulator_db.collection("tickets")
    tickets.document(managed_id).set(
        base_ticket(
            customer_id="customer-a", department_id="card_atm", status="triaged"
        )
    )
    backend = FirebaseAdminManagerBackend(db=emulator_db)
    kwargs = {
        "ticket_id": managed_id,
        "new_department_id": "fraud_security",
        "manager_id": "manager-a",
        "reason": "Synthetic reviewed override",
        "action_id": "manager-override-action",
    }
    first = backend.override_department(**kwargs)
    second = backend.override_department(**kwargs)
    assert first == second
    ticket = tickets.document(managed_id).get()
    assert ticket.get("departmentId") == "fraud_security"
    assert ticket.get("routingSource") == "manager_override"
    event = (
        ticket.reference.collection("events").document("manager-override-action").get()
    )
    assert event.exists
    assert event.get("fromValue") == "card_atm"
    assert event.get("toValue") == "fraud_security"
    assert len(list(ticket.reference.collection("events").stream())) == 1

    missing_id = ticket_id("manager-missing")
    with pytest.raises(ManagerTicketNotFound):
        backend.override_department(
            ticket_id=missing_id,
            new_department_id="loan_credit",
            manager_id="manager-a",
            reason="Must not persist",
            action_id="missing-manager-action",
        )
    missing_ref = tickets.document(missing_id)
    assert not missing_ref.get().exists
    assert (
        not missing_ref.collection("events")
        .document("missing-manager-action")
        .get()
        .exists
    )
