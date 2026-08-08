"""Integration tests for production Firestore adapters against the local emulator."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore

from app.config import MODEL_SHA256
from app.customer_workflow import (
    CustomerWorkflowService,
    FeedbackAlreadySubmitted,
    FirebaseAdminCustomerBackend,
    TicketNotFound,
)
from app.manager_workflow import (
    FirebaseAdminManagerBackend,
)
from app.manager_workflow import (
    TicketNotFound as ManagerTicketNotFound,
)
from app.model import FrozenDepartmentClassifier
from app.routing import RoutingPrediction, TrustedRoutingInference
from app.schemas import (
    CustomerFeedbackRequest,
    CustomerMessageRequest,
    StaffTicketDetail,
    SubmitComplaintRequest,
)
from app.staff_workflow import (
    FirebaseAdminStaffBackend,
    InvalidTransition,
    StaffActor,
    StaffTicketNotFound,
    StaffWorkflowService,
)
from app.ticketing import (
    ComplaintSubmissionService,
    FirebaseAdminTicketBackend,
    PersistenceError,
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
    with pytest.raises(FeedbackAlreadySubmitted):
        service.submit_feedback(
            "customer-a",
            resolved_id,
            CustomerFeedbackRequest(
                rating=1,
                comments="Must not overwrite",
                actionId="different-feedback-action",
            ),
        )
    feedback = emulator_db.collection("feedback").document(f"fb_{resolved_id}").get()
    ticket = emulator_db.collection("tickets").document(resolved_id).get()
    assert feedback.exists and feedback.get("rating") == 5
    assert feedback.get("comments") == "Synthetic feedback"
    assert ticket.get("feedback.rating") == 5
    assert ticket.get("feedback.comments") == "Synthetic feedback"
    actions = list(ticket.reference.collection("actions").stream())
    assert [item.id for item in actions] == ["feedback_customer-feedback-action"]


def test_cross_role_message_schema_and_retry_are_emulator_backed(emulator_db):
    current_id = ticket_id("cross-role-messages")
    ticket_ref = emulator_db.collection("tickets").document(current_id)
    ticket_ref.set(
        base_ticket(
            customer_id="customer-messages",
            department_id="card_atm",
            status="in_progress",
        )
    )
    staff_backend = FirebaseAdminStaffBackend(db=emulator_db)
    staff_actor = StaffActor(uid="staff-card", department_id="card_atm")
    staff_backend.add_reply(
        ticket_id=current_id,
        actor=staff_actor,
        body="Complete staff reply.",
        action_id="cross-role-staff-reply",
    )
    duplicate_staff = staff_backend.add_reply(
        ticket_id=current_id,
        actor=staff_actor,
        body="Complete staff reply.",
        action_id="cross-role-staff-reply",
    )
    assert duplicate_staff.duplicate is True

    customer_service = CustomerWorkflowService(
        FirebaseAdminCustomerBackend(db=emulator_db)
    )
    customer_detail = customer_service.get_ticket_detail(
        "customer-messages", current_id
    )
    assert [message.text for message in customer_detail.messages] == [
        "Complete staff reply."
    ]

    customer_time = datetime.now(timezone.utc) + timedelta(seconds=1)
    customer_request = CustomerMessageRequest(
        messageText="Complete customer reply.",
        actionId="cross-role-customer-reply",
    )
    first_customer = customer_service.send_message(
        "customer-messages", current_id, customer_request, now=customer_time
    )
    duplicate_customer = customer_service.send_message(
        "customer-messages", current_id, customer_request, now=customer_time
    )
    assert first_customer == duplicate_customer

    staff_detail = StaffTicketDetail.model_validate(
        StaffWorkflowService(staff_backend).detail(staff_actor, current_id)
    )
    assert [message.body for message in staff_detail.messages] == [
        "Complete staff reply.",
        "Complete customer reply.",
    ]

    staff_doc = (
        ticket_ref.collection("messages").document("cross-role-staff-reply").get()
    )
    customer_doc = (
        ticket_ref.collection("messages").document("cross-role-customer-reply").get()
    )
    for snapshot, role, body in (
        (staff_doc, "staff", "Complete staff reply."),
        (customer_doc, "customer", "Complete customer reply."),
    ):
        value = snapshot.to_dict()
        assert value["authorRole"] == role
        assert value["body"] == body
        assert value["visibility"] == "participants"
        assert "authorId" in value
        assert not ({"senderId", "senderRole", "text"} & value.keys())

    assert len(list(ticket_ref.collection("messages").stream())) == 2

    ticket_ref.collection("messages").document("legacy-customer-reply").set(
        {
            "senderId": "customer-messages",
            "senderRole": "customer",
            "text": "Existing legacy customer reply.",
            "createdAt": customer_time + timedelta(seconds=1),
        }
    )
    compatible_staff_detail = StaffTicketDetail.model_validate(
        StaffWorkflowService(staff_backend).detail(staff_actor, current_id)
    )
    assert [message.body for message in compatible_staff_detail.messages] == [
        "Complete staff reply.",
        "Complete customer reply.",
        "Existing legacy customer reply.",
    ]


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


def test_prediction_routing_transaction_and_staff_visibility_are_emulator_backed(
    emulator_db,
):
    high_id = ticket_id("routing-high")
    low_id = ticket_id("routing-low")
    failed_id = ticket_id("routing-failed")
    tickets = emulator_db.collection("tickets")
    for current_id in (high_id, low_id, failed_id):
        tickets.document(current_id).set(
            base_ticket(
                customer_id="customer-routing", department_id=None, status="submitted"
            )
        )

    backend = FirebaseAdminTicketBackend(db=emulator_db)
    high = RoutingPrediction(
        department_id="fraud_security",
        confidence=0.94,
        detected_language="en",
        requires_manual_review=False,
        manual_review_reason=None,
        model_version="v1",
    )
    low = RoutingPrediction(
        department_id="card_atm",
        confidence=0.41,
        detected_language="en",
        requires_manual_review=True,
        manual_review_reason="low_prediction_confidence",
        model_version="v1",
    )
    backend.persist_prediction(high_id, high)
    backend.persist_prediction(high_id, high)
    backend.persist_prediction(low_id, low)
    backend.persist_inference_failure(
        failed_id, code="classification_failed", detected_language="en"
    )

    high_doc = tickets.document(high_id).get()
    assert high_doc.get("departmentId") == "fraud_security"
    assert high_doc.get("predictedDepartmentId") == "fraud_security"
    assert high_doc.get("predictionConfidence") == 0.94
    assert high_doc.get("routingSource") == "model"
    assert high_doc.get("status") == "triaged"
    assert len(list(high_doc.reference.collection("events").stream())) == 1

    low_doc = tickets.document(low_id).get()
    assert low_doc.get("departmentId") is None
    assert low_doc.get("predictedDepartmentId") == "card_atm"
    assert low_doc.get("routingSource") == "manual_review"

    failed_doc = tickets.document(failed_id).get()
    assert failed_doc.get("departmentId") is None
    assert failed_doc.get("predictedDepartmentId") is None
    assert failed_doc.get("routingSource") == "manual_review"

    missing_id = ticket_id("routing-missing")
    with pytest.raises(PersistenceError):
        backend.persist_prediction(missing_id, high)
    missing_ref = tickets.document(missing_id)
    assert not missing_ref.get().exists
    assert (
        not missing_ref.collection("events").document("model_v1_routing").get().exists
    )
    assert (
        not missing_ref.collection("actions").document("model_v1_routing").get().exists
    )

    staff = FirebaseAdminStaffBackend(db=emulator_db)
    assert staff.get_department_ticket(high_id, "fraud_security") is not None
    assert staff.get_department_ticket(high_id, "card_atm") is None
    assert staff.get_department_ticket(low_id, "card_atm") is None
    assert staff.get_department_ticket(failed_id, "fraud_security") is None

    manager = FirebaseAdminManagerBackend(db=emulator_db)
    manager.override_department(
        ticket_id=low_id,
        new_department_id="card_atm",
        manager_id="manager-routing",
        reason="Approved after low-confidence review",
        action_id="manager-routing-approval",
    )
    assert staff.get_department_ticket(low_id, "card_atm") is not None
    assert (
        tickets.document(low_id)
        .collection("events")
        .document("manager-routing-approval")
        .get()
        .exists
    )


def test_real_classifier_submission_routes_through_firestore_adapter(emulator_db):
    artifact = (
        Path(__file__).resolve().parents[2]
        / "models"
        / "generated"
        / "cfpb_department_model_v1.joblib"
    )
    if not artifact.is_file():
        pytest.skip("ignored frozen model artifact is not installed")

    class EmulatorSubmissionBackend(FirebaseAdminTicketBackend):
        def verify_id_token(self, token: str) -> str:
            assert token == "emulator-token"
            return "customer-routing-e2e"

        def get_user_profile(self, uid: str) -> dict:
            assert uid == "customer-routing-e2e"
            return {"active": True, "role": "customer"}

    classifier = FrozenDepartmentClassifier.load(artifact, expected_sha256=MODEL_SHA256)
    service = ComplaintSubmissionService(
        EmulatorSubmissionBackend(db=emulator_db),
        TrustedRoutingInference(classifier, confidence_threshold=0.60),
    )
    result = service.submit(
        authorization="Bearer emulator-token",
        payload=SubmitComplaintRequest(
            complaintText="My credit report contains accounts caused by identity theft and fraud.",
            inputLocale="en",
            actionId="emulator-submission-001",
        ),
    )
    retry = service.submit(
        authorization="Bearer emulator-token",
        payload=SubmitComplaintRequest(
            complaintText="My credit report contains accounts caused by identity theft and fraud.",
            inputLocale="en",
            actionId="emulator-submission-001",
        ),
    )
    separate = service.submit(
        authorization="Bearer emulator-token",
        payload=SubmitComplaintRequest(
            complaintText="My credit report contains a second synthetic identity theft entry.",
            inputLocale="en",
            actionId="emulator-submission-002",
        ),
    )
    assert retry.complaint_id == result.complaint_id
    assert separate.complaint_id != result.complaint_id
    ticket = emulator_db.collection("tickets").document(result.complaint_id).get()
    assert ticket.get("customerId") == "customer-routing-e2e"
    assert ticket.get("predictedDepartmentId") == "fraud_security"
    assert ticket.get("predictionConfidence") > 0.60
    assert ticket.get("departmentId") == "fraud_security"
    assert ticket.get("routingSource") == "model"
    assert ticket.get("status") == "triaged"
    owned = list(
        emulator_db.collection("tickets")
        .where("customerId", "==", "customer-routing-e2e")
        .stream()
    )
    assert {item.id for item in owned} == {
        result.complaint_id,
        separate.complaint_id,
    }
