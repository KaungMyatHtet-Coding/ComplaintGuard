"""Pure transaction tests for N1A Customer notification workflow triggers."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from types import SimpleNamespace
from typing import Any

import pytest

from app.manager_workflow import FirebaseAdminManagerBackend
from app.notifications import (
    NotificationProfileError,
    NotificationRecord,
    NotificationValidationError,
    require_active_notification_profile,
)
from app.routing import RoutingPrediction
from app.staff_workflow import FirebaseAdminStaffBackend, StaffActor
from app.ticketing import FirebaseAdminTicketBackend, PersistenceError


class FakeSnapshot:
    def __init__(self, reference: "FakeReference", value: dict[str, Any] | None):
        self.reference = reference
        self.id = reference.path.rsplit("/", 1)[-1]
        self._value = deepcopy(value)
        self.exists = value is not None

    def to_dict(self) -> dict[str, Any] | None:
        return deepcopy(self._value)

    def get(self, key: str) -> Any:
        if self._value is None:
            return None
        return self._value.get(key)


class FakeReference:
    def __init__(self, db: "FakeDatabase", path: str):
        self.db = db
        self.path = path

    def collection(self, name: str) -> "FakeCollection":
        return FakeCollection(self.db, f"{self.path}/{name}")

    def get(self) -> FakeSnapshot:
        return FakeSnapshot(self, self.db.documents.get(self.path))


class FakeCollection:
    def __init__(self, db: "FakeDatabase", path: str):
        self.db = db
        self.path = path

    def document(self, document_id: str) -> FakeReference:
        return FakeReference(self.db, f"{self.path}/{document_id}")


class FakeDatabase:
    def __init__(self) -> None:
        self.documents: dict[str, dict[str, Any]] = {}

    def collection(self, name: str) -> FakeCollection:
        return FakeCollection(self, name)


class FakeTransaction:
    def __init__(self, db: FakeDatabase):
        self.db = db
        self.writes: dict[str, dict[str, Any]] = {}

    def _value(self, reference: FakeReference) -> dict[str, Any] | None:
        if reference.path in self.writes:
            return self.writes[reference.path]
        return self.db.documents.get(reference.path)

    def get(self, reference: FakeReference):
        yield FakeSnapshot(reference, self._value(reference))

    def set(self, reference: FakeReference, value: dict[str, Any], **_: Any) -> None:
        self.writes[reference.path] = deepcopy(value)

    def create(self, reference: FakeReference, value: dict[str, Any]) -> None:
        if self._value(reference) is not None:
            raise RuntimeError("already exists")
        self.writes[reference.path] = deepcopy(value)

    def update(self, reference: FakeReference, changes: dict[str, Any]) -> None:
        current = self._value(reference)
        if current is None:
            raise RuntimeError("missing update target")
        current = deepcopy(current)
        current.update(deepcopy(changes))
        self.writes[reference.path] = current

    def commit(self) -> None:
        self.db.documents.update(deepcopy(self.writes))


def run_fake_transaction(db: FakeDatabase, operation):
    transaction = FakeTransaction(db)
    result = operation(transaction)
    transaction.commit()
    return result


class RecordingNotificationWriter:
    """A transaction participant with the same create/conflict semantics."""

    def __init__(self, db: FakeDatabase):
        self.db = db

    def stage_create(self, transaction: FakeTransaction, request: Any) -> NotificationRecord:
        reference = sha256(request.source_key.encode("utf-8")).hexdigest()
        now = datetime(2026, 8, 22, tzinfo=timezone.utc)
        document = {
                "recipientUid": request.recipient_uid,
                "type": request.type,
                "severity": request.severity,
                "category": request.category,
                "relatedTicketRef": request.related_ticket_ref,
                "titleKey": request.title_key,
                "bodyKey": request.body_key,
                "params": dict(request.params),
                "navigationTarget": request.navigation_target,
                "createdAt": now,
                "readAt": None,
                "expiresAt": now + timedelta(days=90),
                "policyVersion": request.policy_version,
                "dedupeKeyHash": reference,
        }
        notification_ref = self.db.collection("notifications").document(reference)
        existing = transaction._value(notification_ref)
        if existing is None:
            transaction.create(notification_ref, document)
        elif existing != document:
            raise RuntimeError("notification conflict")
        return NotificationRecord(
            notification_ref=reference,
            recipient_uid=request.recipient_uid,
            type=request.type,
            severity=request.severity,
            category=request.category,
            title_key=request.title_key,
            body_key=request.body_key,
            params=dict(request.params),
            navigation_target=request.navigation_target,
            related_ticket_ref=request.related_ticket_ref,
            created_at=now,
            read_at=None,
            policy_version=request.policy_version,
            expires_at=now + timedelta(days=90),
            dedupe_key_hash=reference,
        )


class FailingNotificationWriter:
    def stage_create(self, transaction: FakeTransaction, request: Any):
        raise PersistenceError("notification staging failed")


def _profile(uid: str = "customer-1", *, active: bool = True) -> dict[str, Any]:
    now = datetime(2026, 8, 22, tzinfo=timezone.utc)
    return {
        "uid": uid,
        "role": "customer",
        "active": active,
        "accountState": "active" if active else "disabled",
        "displayName": "Customer One",
        "email": "customer@example.test",
        "locale": "en",
        "departmentId": None,
        "createdAt": now,
        "updatedAt": now,
    }


def _ticket(customer_id: str = "customer-1", *, department: str | None = "general_support"):
    now = datetime(2026, 8, 22, tzinfo=timezone.utc)
    return {
        "customerId": customer_id,
        "departmentId": department,
        "status": "triaged" if department else "submitted",
        "routingSource": "model" if department else "pending",
        "priority": "normal",
        "complaintText": "safe test complaint",
        "createdAt": now,
        "updatedAt": now,
    }


def _backend(db: FakeDatabase, monkeypatch: pytest.MonkeyPatch, writer: Any):
    monkeypatch.setattr("app.ticketing.run_firestore_transaction", lambda _db, op: run_fake_transaction(db, op))
    monkeypatch.setattr("app.staff_workflow.run_firestore_transaction", lambda _db, op: run_fake_transaction(db, op))
    return FirebaseAdminTicketBackend(db=db, notification_writer=writer)


def _add_profile(db: FakeDatabase, uid: str = "customer-1", *, active: bool = True):
    db.documents[f"users/{uid}"] = _profile(uid, active=active)


def _notifications(db: FakeDatabase) -> list[dict[str, Any]]:
    return [value for path, value in db.documents.items() if path.startswith("notifications/")]


def test_complaint_creation_is_atomic_and_retry_safe(monkeypatch):
    db = FakeDatabase()
    _add_profile(db)
    writer = RecordingNotificationWriter(db)
    backend = _backend(db, monkeypatch, writer)
    document = _ticket(department=None)
    document["customerId"] = "customer-1"

    ticket_id = backend.create_ticket(document, idempotency_key="action-1")
    assert backend.create_ticket(document, idempotency_key="action-1") == ticket_id
    assert len(_notifications(db)) == 1
    assert _notifications(db)[0]["type"] == "complaint_received"


def test_complaint_creation_rolls_back_for_invalid_recipient_or_notification_failure(monkeypatch):
    db = FakeDatabase()
    backend = _backend(db, monkeypatch, RecordingNotificationWriter(db))
    with pytest.raises(PersistenceError):
        backend.create_ticket(_ticket("missing", department=None), idempotency_key="bad")
    assert not any(path.startswith("tickets/") for path in db.documents)

    _add_profile(db)
    failing = _backend(db, monkeypatch, FailingNotificationWriter())
    with pytest.raises(PersistenceError):
        failing.create_ticket(_ticket(department=None), idempotency_key="failed")
    assert not any(path.endswith("failed") for path in db.documents)
    assert not any(path.startswith("tickets/") for path in db.documents)


def test_conflicting_retry_does_not_overwrite_notification_or_ticket(monkeypatch):
    db = FakeDatabase()
    _add_profile(db)
    writer = RecordingNotificationWriter(db)
    backend = _backend(db, monkeypatch, writer)
    document = _ticket(department=None)
    ticket_id = backend.create_ticket(document, idempotency_key="conflict")
    notification_path = next(path for path in db.documents if path.startswith("notifications/"))
    original_notification = deepcopy(db.documents[notification_path])
    db.documents[notification_path]["type"] = "status_changed"
    conflicting_notification = deepcopy(db.documents[notification_path])

    with pytest.raises(PersistenceError):
        backend.create_ticket(document, idempotency_key="conflict")

    assert db.documents[f"tickets/{ticket_id}"] == document
    assert db.documents[notification_path] == conflicting_notification
    assert conflicting_notification != original_notification


def test_model_assignment_is_safe_and_manual_review_is_silent(monkeypatch):
    db = FakeDatabase()
    _add_profile(db)
    writer = RecordingNotificationWriter(db)
    backend = _backend(db, monkeypatch, writer)
    ticket_id = backend.create_ticket(_ticket(department=None), idempotency_key="route")
    prediction = RoutingPrediction("fraud_security", 0.91, "en", False, None, "v1")
    backend.persist_prediction(ticket_id, prediction)
    backend.persist_prediction(ticket_id, prediction)
    assert len(_notifications(db)) == 2
    assignment = next(item for item in _notifications(db) if item["type"] == "department_assigned")
    assert assignment["params"] == {"ticketRef": ticket_id, "departmentKey": "fraud_security"}
    assert "confidence" not in str(assignment).lower()

    db2 = FakeDatabase()
    _add_profile(db2)
    backend2 = _backend(db2, monkeypatch, RecordingNotificationWriter(db2))
    pending_id = backend2.create_ticket(_ticket(department=None), idempotency_key="manual")
    backend2.persist_prediction(
        pending_id,
        RoutingPrediction("fraud_security", 0.41, "en", True, "low_confidence", "v1"),
    )
    assert len(_notifications(db2)) == 1


def test_manager_override_notifies_only_on_customer_visible_change(monkeypatch):
    db = FakeDatabase()
    _add_profile(db)
    db.documents["tickets/t-1"] = _ticket(department="general_support")
    writer = RecordingNotificationWriter(db)
    monkeypatch.setattr("app.ticketing.run_firestore_transaction", lambda _db, op: run_fake_transaction(db, op))
    backend = FirebaseAdminManagerBackend(db=db, notification_writer=writer)
    backend.override_department("t-1", "fraud_security", "manager-1", "private reason", "override-1")
    backend.override_department("t-1", "fraud_security", "manager-1", "private reason", "override-1")
    assert len(_notifications(db)) == 1
    item = _notifications(db)[0]
    assert item["type"] == "department_assigned"
    assert "private reason" not in str(item)
    assert "manager-1" not in str(item)


def test_staff_reply_and_transition_triggers_are_atomic_and_specific(monkeypatch):
    db = FakeDatabase()
    _add_profile(db)
    db.documents["tickets/t-1"] = _ticket()
    writer = RecordingNotificationWriter(db)
    monkeypatch.setattr("app.staff_workflow.run_firestore_transaction", lambda _db, op: run_fake_transaction(db, op))
    staff = FirebaseAdminStaffBackend(db=db, notification_writer=writer)
    actor = StaffActor(uid="staff-1", department_id="general_support")

    staff.add_reply(ticket_id="t-1", actor=actor, body="private reply body", action_id="reply-1")
    staff.add_reply(ticket_id="t-1", actor=actor, body="private reply body", action_id="reply-1")
    staff.transition_ticket(
        ticket_id="t-1", actor=actor, to_status="in_progress", resolution_summary=None, action_id="status-1"
    )
    staff.transition_ticket(
        ticket_id="t-1", actor=actor, to_status="awaiting_customer", resolution_summary=None, action_id="status-2"
    )
    staff.transition_ticket(
        ticket_id="t-1", actor=actor, to_status="in_progress", resolution_summary=None, action_id="status-3"
    )
    staff.transition_ticket(
        ticket_id="t-1", actor=actor, to_status="resolved", resolution_summary="private resolution", action_id="status-4"
    )
    values = _notifications(db)
    assert [item["type"] for item in values].count("staff_reply") == 1
    assert [item["type"] for item in values].count("information_requested") == 1
    assert [item["type"] for item in values].count("status_changed") == 2
    assert [item["type"] for item in values].count("complaint_resolved") == 1
    serialized = str(values)
    assert "private reply body" not in serialized
    assert "staff-1" not in serialized
    assert "private resolution" not in serialized


def test_inactive_customer_keeps_trusted_staff_work_and_read_authorization_denied(monkeypatch):
    db = FakeDatabase()
    _add_profile(db, active=False)
    db.documents["tickets/t-inactive"] = _ticket()
    writer = RecordingNotificationWriter(db)
    monkeypatch.setattr("app.staff_workflow.run_firestore_transaction", lambda _db, op: run_fake_transaction(db, op))
    staff = FirebaseAdminStaffBackend(db=db, notification_writer=writer)
    actor = StaffActor(uid="staff-1", department_id="general_support")

    staff.add_reply(ticket_id="t-inactive", actor=actor, body="reply", action_id="reply-inactive")
    staff.transition_ticket(
        ticket_id="t-inactive",
        actor=actor,
        to_status="in_progress",
        resolution_summary=None,
        action_id="status-inactive-1",
    )
    staff.transition_ticket(
        ticket_id="t-inactive",
        actor=actor,
        to_status="resolved",
        resolution_summary="resolved",
        action_id="status-inactive-2",
    )
    assert {item["type"] for item in _notifications(db)} == {
        "staff_reply",
        "status_changed",
        "complaint_resolved",
    }
    with pytest.raises(NotificationProfileError):
        require_active_notification_profile(
            "Bearer token", SimpleNamespace(
                verify_id_token=lambda token: "customer-1",
                get_user_profile=lambda uid: _profile(uid, active=False),
            )
        )


def test_inactive_customer_keeps_trusted_manager_assignment_work(monkeypatch):
    db = FakeDatabase()
    _add_profile(db, active=False)
    db.documents["tickets/t-inactive"] = _ticket()
    writer = RecordingNotificationWriter(db)
    monkeypatch.setattr("app.ticketing.run_firestore_transaction", lambda _db, op: run_fake_transaction(db, op))
    manager = FirebaseAdminManagerBackend(db=db, notification_writer=writer)
    manager.override_department(
        "t-inactive", "fraud_security", "manager-1", "private reason", "override-inactive"
    )
    assert len(_notifications(db)) == 1
    assert _notifications(db)[0]["recipientUid"] == "customer-1"


def test_invalid_ticket_customer_id_blocks_later_mutations(monkeypatch):
    db = FakeDatabase()
    writer = RecordingNotificationWriter(db)
    db.documents["tickets/t-invalid"] = _ticket(customer_id=" ")
    monkeypatch.setattr("app.staff_workflow.run_firestore_transaction", lambda _db, op: run_fake_transaction(db, op))
    staff = FirebaseAdminStaffBackend(db=db, notification_writer=writer)
    actor = StaffActor(uid="staff-1", department_id="general_support")
    before = deepcopy(db.documents)
    with pytest.raises(NotificationProfileError):
        staff.add_reply(ticket_id="t-invalid", actor=actor, body="reply", action_id="reply-invalid")
    assert db.documents == before


def test_staff_reply_and_transition_failures_leave_source_unchanged(monkeypatch):
    db = FakeDatabase()
    _add_profile(db)
    db.documents["tickets/t-1"] = _ticket()
    db_before = deepcopy(db.documents)
    monkeypatch.setattr("app.staff_workflow.run_firestore_transaction", lambda _db, op: run_fake_transaction(db, op))
    staff = FirebaseAdminStaffBackend(db=db, notification_writer=FailingNotificationWriter())
    actor = StaffActor(uid="staff-1", department_id="general_support")
    with pytest.raises(PersistenceError):
        staff.add_reply(ticket_id="t-1", actor=actor, body="reply", action_id="reply-1")
    assert db.documents == db_before
    with pytest.raises(PersistenceError):
        staff.transition_ticket(
            ticket_id="t-1", actor=actor, to_status="in_progress", resolution_summary=None, action_id="status-1"
        )
    assert db.documents == db_before


def test_customer_notification_contract_rejects_unsafe_shapes():
    from app.notifications import build_customer_notification_request

    with pytest.raises(NotificationValidationError):
        build_customer_notification_request(
            notification_type="department_assigned",
            recipient_uid="customer-1",
            ticket_ref="ticket-1",
            source_key="source",
        )
    with pytest.raises(NotificationValidationError):
        build_customer_notification_request(
            notification_type="status_changed",
            recipient_uid="customer-1",
            ticket_ref="ticket-1",
            source_key="source",
            status="internal_override",
        )


def test_invalid_customer_profile_is_not_redirected(monkeypatch):
    db = FakeDatabase()
    db.documents["users/customer-1"] = _profile(active=False)
    backend = _backend(db, monkeypatch, RecordingNotificationWriter(db))
    with pytest.raises(PersistenceError):
        backend.create_ticket(_ticket(), idempotency_key="inactive")
    assert not _notifications(db)
