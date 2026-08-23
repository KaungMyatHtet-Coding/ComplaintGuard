"""Isolated Firebase Emulator integration coverage for Admin lifecycle routes.

This module never starts Firebase services and never uses Cloud credentials. It
is skipped unless both local emulator hosts are explicitly supplied; malformed
or non-local configuration fails closed in the fixture.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.admin_directory import account_reference
from app.admin_lifecycle import (
    LifecycleActionService,
    lifecycle_action_reference,
    lifecycle_audit_event_reference,
    lifecycle_target_guard_reference,
)
from app.admin_recovery import FirebaseAdminLifecycleRecoveryBackend
from app.config import Settings
from app.firebase_environment import validate_local_emulator_environment
from app.main import create_app
from app.ticketing import firebase_admin_clients

pytestmark = pytest.mark.skipif(
    not (
        os.getenv("FIRESTORE_EMULATOR_HOST")
        and os.getenv("FIREBASE_AUTH_EMULATOR_HOST")
    ),
    reason="requires explicitly configured local Auth and Firestore Emulators",
)

PROJECT_ID = "demo-complaintguard"
AUTH_API_KEY = "emulator-only"
NOW = datetime(2026, 8, 23, 10, 0, tzinfo=timezone.utc)
UNRESOLVED_STATUSES = {"submitted", "triaged", "in_progress", "awaiting_customer"}


def _fake_loader(*_args: Any, **_kwargs: Any):
    class FakeClassifier:
        model_version = "v1"

    return FakeClassifier()


def _auth_emulator_request(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    host = os.environ["FIREBASE_AUTH_EMULATOR_HOST"]
    request = urllib.request.Request(
        f"http://{host}/identitytoolkit.googleapis.com/v1/{path}?key={AUTH_API_KEY}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError) as exc:
        raise AssertionError("local Auth Emulator request failed") from exc


class EmulatorRun:
    def __init__(self) -> None:
        self.auth_client: Any = None
        self.db: Any = None
        self.timestamp: object = None
        self.identities: list[tuple[str, str]] = []
        self.emails: dict[str, str] = {}
        self.profile_uids: list[str] = []
        self.ticket_ids: list[str] = []
        self.action_refs: set[str] = set()
        self.guard_refs: set[str] = set()
        self.audit_refs: set[str] = set()

    def create_identity(self, label: str) -> tuple[str, str]:
        email = f"r2c7-{label}-{uuid4().hex}@complaintguard.test"
        password = f"Cg-r2c7-{uuid4().hex}!"
        result = _auth_emulator_request(
            "accounts:signUp",
            {"email": email, "password": password, "returnSecureToken": True},
        )
        uid = result["localId"]
        token = result["idToken"]
        self.identities.append((uid, email))
        self.emails[uid] = email
        return uid, token

    def set_profile(self, uid: str, *, role: str, active: bool = True, department: str | None = None) -> None:
        self.db.collection("users").document(uid).set(
            {
                "email": self.emails[uid],
                "displayName": f"R2C7 {role}",
                "locale": "en",
                "role": role,
                "departmentId": department,
                "active": active,
                "createdAt": NOW,
                "updatedAt": NOW,
            }
        )
        self.profile_uids.append(uid)

    def track_action(self, *, actor_uid: str, target_uid: str, key: str, operation: str) -> str:
        action_ref = lifecycle_action_reference(
            actor_uid=actor_uid,
            target_uid=target_uid,
            idempotency_key=key,
            operation=operation,
        )
        self.action_refs.add(action_ref)
        self.guard_refs.add(
            lifecycle_target_guard_reference(
                target_uid=target_uid,
                project_id=PROJECT_ID,
                environment="local-emulator",
            )
        )
        if operation == "disable":
            self.audit_refs.update(
                {
                    lifecycle_audit_event_reference(
                        action_ref=action_ref,
                        operation=operation,
                        from_state="reserved",
                        to_state="profile_inactivated",
                        result_code="profile_inactivated",
                        version=2,
                    ),
                    lifecycle_audit_event_reference(
                        action_ref=action_ref,
                        operation=operation,
                        from_state="profile_inactivated",
                        to_state="auth_disable_pending",
                        result_code="auth_disable_pending",
                        version=3,
                    ),
                    lifecycle_audit_event_reference(
                        action_ref=action_ref,
                        operation=operation,
                        from_state="auth_disable_pending",
                        to_state="completed",
                        result_code="completed",
                        version=4,
                    ),
                }
            )
        elif operation == "reactivate":
            self.audit_refs.update(
                {
                    lifecycle_audit_event_reference(
                        action_ref=action_ref,
                        operation=operation,
                        from_state="reserved",
                        to_state="auth_enable_pending",
                        result_code="auth_enable_pending",
                        version=2,
                    ),
                    lifecycle_audit_event_reference(
                        action_ref=action_ref,
                        operation=operation,
                        from_state="auth_enable_pending",
                        to_state="profile_activation_pending",
                        result_code="profile_activation_pending",
                        version=3,
                    ),
                    lifecycle_audit_event_reference(
                        action_ref=action_ref,
                        operation=operation,
                        from_state="profile_activation_pending",
                        to_state="completed",
                        result_code="completed",
                        version=4,
                    ),
                }
            )
        else:
            self.audit_refs.update(
                {
                    lifecycle_audit_event_reference(
                        action_ref=action_ref,
                        operation=operation,
                        from_state="reserved",
                        to_state="completed",
                        result_code="completed",
                        version=2,
                    ),
                    lifecycle_audit_event_reference(
                        action_ref=action_ref,
                        operation=operation,
                        from_state="reserved",
                        to_state="conflict",
                        result_code="assigned_unresolved_work",
                        version=2,
                    ),
                }
            )
        return action_ref

    def cleanup(self) -> None:
        cleanup_errors: list[str] = []

        def delete_exact(collection: str, document_id: str) -> None:
            if self.db is None:
                return
            try:
                self.db.collection(collection).document(document_id).delete()
            except Exception as exc:  # noqa: BLE001 - continue all owned cleanup
                cleanup_errors.append(type(exc).__name__)

        for ticket_id in self.ticket_ids:
            delete_exact("tickets", ticket_id)
        for action_ref in self.action_refs:
            delete_exact("adminAccountLifecycleActions", action_ref)
        for guard_ref in self.guard_refs:
            delete_exact("adminAccountLifecycleTargetGuards", guard_ref)
        for event_ref in self.audit_refs:
            delete_exact("adminAccountLifecycleAuditEvents", event_ref)
        for uid in self.profile_uids:
            delete_exact("users", uid)
        for uid, _email in self.identities:
            if self.auth_client is None:
                continue
            try:
                self.auth_client.delete_user(uid)
            except Exception as exc:  # noqa: BLE001 - continue all owned cleanup
                cleanup_errors.append(type(exc).__name__)
        if self.auth_client is not None:
            self.auth_client = None
        if self.db is not None:
            try:
                self.db.close()
            except Exception as exc:  # noqa: BLE001 - report after owned cleanup
                cleanup_errors.append(type(exc).__name__)
            self.db = None
        if cleanup_errors:
            raise AssertionError("owned emulator cleanup failed")


@pytest.fixture
def emulator_run() -> Any:
    environment = validate_local_emulator_environment()
    assert environment.project_id == PROJECT_ID
    run = EmulatorRun()
    try:
        run.auth_client, run.db, run.timestamp = firebase_admin_clients()
        yield run
    finally:
        run.cleanup()


@pytest.fixture
def lifecycle_app(emulator_run: EmulatorRun) -> tuple[EmulatorRun, TestClient, Any]:
    backend = FirebaseAdminLifecycleRecoveryBackend(
        clients=(emulator_run.auth_client, emulator_run.db, emulator_run.timestamp)
    )
    app = create_app(
        settings=Settings.default(),
        model_loader=_fake_loader,
        admin_directory_backend=backend,
        admin_disable_backend=backend,
        admin_reactivate_backend=backend,
        admin_reassign_backend=backend,
        admin_recovery_backend=backend,
    )
    with TestClient(app) as client:
        yield emulator_run, client, backend


def _profile(run: EmulatorRun, uid: str) -> dict[str, Any]:
    return run.db.collection("users").document(uid).get().to_dict() or {}


def _action(run: EmulatorRun, backend: Any, *, actor_uid: str, target_uid: str, key: str, operation: str, department: str | None = None):
    action_ref = run.track_action(
        actor_uid=actor_uid, target_uid=target_uid, key=key, operation=operation
    )
    return backend.get_action(action_ref), action_ref


def _audit_count(run: EmulatorRun, action_ref: str) -> int:
    return sum(
        1
        for event_ref in run.audit_refs
        if (
            (snapshot := run.db.collection("adminAccountLifecycleAuditEvents").document(event_ref).get()).exists
            and snapshot.to_dict().get("actionRef") == action_ref
        )
    )


def test_emulator_authorization_disable_reactivate_and_recovery(lifecycle_app) -> None:
    run, client, backend = lifecycle_app
    admin_uid, admin_token = run.create_identity("admin")
    other_admin_uid, other_admin_token = run.create_identity("other-admin")
    customer_uid, _customer_token = run.create_identity("customer")
    staff_uid, staff_token = run.create_identity("staff")
    manager_uid, manager_token = run.create_identity("manager")
    unproven_uid, _unproven_token = run.create_identity("unproven")
    inactive_admin_uid, inactive_admin_token = run.create_identity("inactive-admin")
    malformed_admin_uid, malformed_admin_token = run.create_identity("malformed-admin")
    run.set_profile(admin_uid, role="admin")
    run.set_profile(other_admin_uid, role="admin")
    run.set_profile(customer_uid, role="customer")
    run.set_profile(staff_uid, role="staff", department="card_atm")
    run.set_profile(manager_uid, role="manager")
    run.set_profile(unproven_uid, role="customer", active=False)
    run.set_profile(inactive_admin_uid, role="admin", active=False)
    customer_ref = account_reference(customer_uid)
    unproven_ref = account_reference(unproven_uid)
    denied = client.post(
        f"/admin/users/{customer_ref}/disable",
        headers={"Authorization": f"Bearer {(_customer_token or 'missing') }"},
        json={"idempotencyKey": "denied-001"},
    )
    assert denied.status_code == 401 or denied.status_code == 403
    for token in (staff_token, manager_token, inactive_admin_token):
        denied_role = client.post(
            f"/admin/users/{customer_ref}/disable",
            headers={"Authorization": f"Bearer {token}"},
            json={"idempotencyKey": "denied-role-001"},
        )
        assert denied_role.status_code in {401, 403}
    assert client.post(
        f"/admin/users/{customer_ref}/disable",
        json={"idempotencyKey": "missing-001"},
    ).status_code == 401
    initial_guard_ref = lifecycle_target_guard_reference(
        target_uid=customer_uid,
        project_id=PROJECT_ID,
        environment="local-emulator",
    )
    assert not run.db.collection("adminAccountLifecycleTargetGuards").document(
        initial_guard_ref
    ).get().exists

    run.track_action(
        actor_uid=admin_uid,
        target_uid=customer_uid,
        key="disable-customer-001",
        operation="disable",
    )
    disabled = client.post(
        f"/admin/users/{customer_ref}/disable",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"idempotencyKey": "disable-customer-001"},
    )
    assert disabled.status_code == 200
    assert set(disabled.json()) == {"accountRef", "operation", "status", "profileState"}
    assert _profile(run, customer_uid)["active"] is False
    assert backend._auth.get_user(customer_uid).disabled is True

    for uid, key in ((staff_uid, "disable-staff-001"), (manager_uid, "disable-manager-001")):
        run.track_action(
            actor_uid=admin_uid, target_uid=uid, key=key, operation="disable"
        )
        role_result = client.post(
            f"/admin/users/{account_reference(uid)}/disable",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"idempotencyKey": key},
        )
        assert role_result.status_code == 200
        assert _profile(run, uid)["active"] is False
        assert backend._auth.get_user(uid).disabled is True

    action, action_ref = _action(
        run,
        backend,
        actor_uid=admin_uid,
        target_uid=customer_uid,
        key="disable-customer-001",
        operation="disable",
    )
    assert action is not None and action.state == "completed"
    guard_ref = lifecycle_target_guard_reference(
        target_uid=customer_uid,
        project_id=PROJECT_ID,
        environment="local-emulator",
    )
    guard = run.db.collection("adminAccountLifecycleTargetGuards").document(guard_ref).get()
    assert guard.exists and guard.get("state") == "inactive"
    assert _audit_count(run, action_ref) == 3
    before_audits = _audit_count(run, action_ref)
    replay = client.post(
        f"/admin/users/{customer_ref}/disable",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"idempotencyKey": "disable-customer-001"},
    )
    assert replay.status_code == 200
    assert _audit_count(run, action_ref) == before_audits

    reactivated = client.post(
        f"/admin/users/{customer_ref}/reactivate",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"idempotencyKey": "reactivate-customer-001"},
    )
    assert reactivated.status_code == 200
    run.track_action(
        actor_uid=admin_uid,
        target_uid=customer_uid,
        key="reactivate-customer-001",
        operation="reactivate",
    )
    assert _profile(run, customer_uid)["active"] is True
    assert backend._auth.get_user(customer_uid).disabled is False
    recovered = client.post(
        f"/admin/users/{customer_ref}/lifecycle-recovery",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"operation": "reactivate"},
    )
    assert recovered.status_code == 200
    assert set(recovered.json()) == {"accountRef", "operation", "status", "profileState"}

    assert client.post(
        f"/admin/users/{unproven_ref}/reactivate",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"idempotencyKey": "unproven-001"},
    ).status_code == 409
    mismatch = client.post(
        f"/admin/users/{customer_ref}/lifecycle-recovery",
        headers={"Authorization": f"Bearer {other_admin_token}"},
        json={"operation": "disable"},
    )
    assert mismatch.status_code in {403, 404, 409}
    run.db.collection("users").document(malformed_admin_uid).set(
        {"email": run.emails[malformed_admin_uid], "role": "admin", "active": True}
    )
    run.profile_uids.append(malformed_admin_uid)
    malformed_denied = client.post(
        f"/admin/users/{customer_ref}/disable",
        headers={"Authorization": f"Bearer {malformed_admin_token}"},
        json={"idempotencyKey": "malformed-admin-001"},
    )
    assert malformed_denied.status_code in {401, 403, 503}
    assert other_admin_uid != admin_uid


def test_emulator_staff_reassignment_and_ticket_isolation(lifecycle_app) -> None:
    run, client, _backend = lifecycle_app
    admin_uid, admin_token = run.create_identity("admin-reassign")
    staff_uid, _staff_token = run.create_identity("staff-reassign")
    blocked_uid, _blocked_token = run.create_identity("staff-blocked")
    run.set_profile(admin_uid, role="admin")
    run.set_profile(staff_uid, role="staff", department="account_support")
    run.set_profile(blocked_uid, role="staff", department="account_support")
    staff_ref = account_reference(staff_uid)
    blocked_ref = account_reference(blocked_uid)

    unchanged = client.post(
        f"/admin/users/{staff_ref}/reassign-department",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"idempotencyKey": "same-department-1", "departmentId": "account_support"},
    )
    assert unchanged.status_code == 409

    ticket_id = f"r2c7-{uuid4().hex}"
    run.ticket_ids.append(ticket_id)
    ticket = {
        "customerId": f"r2c7-customer-{uuid4().hex}",
        "complaintText": "Synthetic emulator-only complaint",
        "inputLocale": "en",
        "departmentId": "account_support",
        "assignedStaffId": blocked_uid,
        "status": "in_progress",
        "priority": "normal",
        "predictedDepartmentId": None,
        "predictionConfidence": None,
        "routingSource": "manual_review",
        "escalated": False,
        "resolutionSummary": None,
        "createdAt": NOW,
        "updatedAt": NOW,
        "resolvedAt": None,
    }
    run.db.collection("tickets").document(ticket_id).set(ticket)
    run.track_action(
        actor_uid=admin_uid,
        target_uid=blocked_uid,
        key="blocked-reassign-1",
        operation="reassign_department",
    )
    blocked = client.post(
        f"/admin/users/{blocked_ref}/reassign-department",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"idempotencyKey": "blocked-reassign-1", "departmentId": "card_atm"},
    )
    assert blocked.status_code == 409
    assert _profile(run, blocked_uid)["departmentId"] == "account_support"
    assert run.db.collection("tickets").document(ticket_id).get().to_dict() == ticket

    run.db.collection("tickets").document(ticket_id).update({"status": "resolved"})
    recovered = client.post(
        f"/admin/users/{blocked_ref}/lifecycle-recovery",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"operation": "reassign_department", "departmentId": "card_atm"},
    )
    assert recovered.status_code in {404, 409}
    run.track_action(
        actor_uid=admin_uid,
        target_uid=blocked_uid,
        key="retry-reassign-1",
        operation="reassign_department",
    )
    successful = client.post(
        f"/admin/users/{blocked_ref}/reassign-department",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"idempotencyKey": "retry-reassign-1", "departmentId": "card_atm"},
    )
    assert successful.status_code == 200
    assert _profile(run, blocked_uid)["departmentId"] == "card_atm"
    assert run.db.collection("tickets").document(ticket_id).get().to_dict()["assignedStaffId"] == blocked_uid

    other_uid, _other_token = run.create_identity("staff-other")
    run.set_profile(other_uid, role="staff", department="fraud_security")
    unassigned_ticket_id = f"r2c7-{uuid4().hex}"
    other_ticket_id = f"r2c7-{uuid4().hex}"
    run.ticket_ids.extend([unassigned_ticket_id, other_ticket_id])
    for extra_id, assigned_uid in ((unassigned_ticket_id, None), (other_ticket_id, other_uid)):
        extra_ticket = dict(ticket)
        extra_ticket["assignedStaffId"] = assigned_uid
        extra_ticket["status"] = "triaged"
        run.db.collection("tickets").document(extra_id).set(extra_ticket)
    run.track_action(
        actor_uid=admin_uid,
        target_uid=staff_uid,
        key="reassign-unassigned-1",
        operation="reassign_department",
    )
    moved = client.post(
        f"/admin/users/{staff_ref}/reassign-department",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"idempotencyKey": "reassign-unassigned-1", "departmentId": "card_atm"},
    )
    assert moved.status_code == 200
    assert run.db.collection("tickets").document(unassigned_ticket_id).get().to_dict() == {
        **dict(ticket), "assignedStaffId": None, "status": "triaged"
    }
    assert run.db.collection("tickets").document(other_ticket_id).get().to_dict() == {
        **dict(ticket), "assignedStaffId": other_uid, "status": "triaged"
    }


def test_emulator_recovery_continues_reserved_and_pending_states(lifecycle_app) -> None:
    run, client, backend = lifecycle_app
    admin_uid, admin_token = run.create_identity("admin-recovery")
    disable_uid, _disable_token = run.create_identity("recovery-disable")
    reactivate_uid, _reactivate_token = run.create_identity("recovery-reactivate")
    reassign_uid, _reassign_token = run.create_identity("recovery-reassign")
    run.set_profile(admin_uid, role="admin")
    run.set_profile(disable_uid, role="customer")
    run.set_profile(reactivate_uid, role="customer")
    run.set_profile(reassign_uid, role="staff", department="account_support")
    headers = {"Authorization": f"Bearer {admin_token}"}

    disable_key = "recovery-disable-1"
    disable_action = LifecycleActionService(backend).reserve(
        actor_uid=admin_uid,
        target_uid=disable_uid,
        target_role="customer",
        operation="disable",
        idempotency_key=disable_key,
        account_ref=account_reference(disable_uid),
    )
    run.track_action(
        actor_uid=admin_uid,
        target_uid=disable_uid,
        key=disable_key,
        operation="disable",
    )
    mismatch = client.post(
        f"/admin/users/{account_reference(disable_uid)}/lifecycle-recovery",
        headers=headers,
        json={"operation": "reactivate"},
    )
    assert mismatch.status_code == 409
    disable_recovery = client.post(
        f"/admin/users/{account_reference(disable_uid)}/lifecycle-recovery",
        headers=headers,
        json={"operation": "disable"},
    )
    assert disable_recovery.status_code == 200
    assert backend.get_action(disable_action.action_ref).state == "completed"

    reactivate_key = "recovery-reactivate-1"
    run.track_action(
        actor_uid=admin_uid,
        target_uid=reactivate_uid,
        key="lineage-disable-1",
        operation="disable",
    )
    first_disable = client.post(
        f"/admin/users/{account_reference(reactivate_uid)}/disable",
        headers=headers,
        json={"idempotencyKey": "lineage-disable-1"},
    )
    assert first_disable.status_code == 200
    previous_ref = lifecycle_action_reference(
        actor_uid=admin_uid,
        target_uid=reactivate_uid,
        idempotency_key="lineage-disable-1",
        operation="disable",
    )
    reactivate_action = LifecycleActionService(backend).reserve(
        actor_uid=admin_uid,
        target_uid=reactivate_uid,
        target_role="customer",
        operation="reactivate",
        idempotency_key=reactivate_key,
        account_ref=account_reference(reactivate_uid),
        previous_action_ref=previous_ref,
    )
    backend._lifecycle.reserve_reactivation(reactivate_action)
    transition_now = datetime.now(timezone.utc)
    backend.transition(
        reactivate_action.action_ref,
        expected_version=reactivate_action.version,
        to_state="auth_enable_pending",
        result_code="auth_enable_pending",
        now=transition_now,
    )
    run.track_action(
        actor_uid=admin_uid,
        target_uid=reactivate_uid,
        key=reactivate_key,
        operation="reactivate",
    )
    reactivate_recovery = client.post(
        f"/admin/users/{account_reference(reactivate_uid)}/lifecycle-recovery",
        headers=headers,
        json={"operation": "reactivate"},
    )
    assert reactivate_recovery.status_code == 200
    assert _profile(run, reactivate_uid)["active"] is True

    reassign_key = "recovery-reassign-1"
    reassign_action = LifecycleActionService(backend).reserve(
        actor_uid=admin_uid,
        target_uid=reassign_uid,
        target_role="staff",
        operation="reassign_department",
        idempotency_key=reassign_key,
        account_ref=account_reference(reassign_uid),
        requested_department="card_atm",
    )
    run.track_action(
        actor_uid=admin_uid,
        target_uid=reassign_uid,
        key=reassign_key,
        operation="reassign_department",
    )
    department_mismatch = client.post(
        f"/admin/users/{account_reference(reassign_uid)}/lifecycle-recovery",
        headers=headers,
        json={"operation": "reassign_department", "departmentId": "fraud_security"},
    )
    assert department_mismatch.status_code == 409
    reassign_recovery = client.post(
        f"/admin/users/{account_reference(reassign_uid)}/lifecycle-recovery",
        headers=headers,
        json={"operation": "reassign_department", "departmentId": "card_atm"},
    )
    assert reassign_recovery.status_code == 200
    assert backend.get_action(reassign_action.action_ref).state == "completed"
    assert _profile(run, reassign_uid)["departmentId"] == "card_atm"

    failed_uid, _failed_token = run.create_identity("recovery-failed")
    run.set_profile(failed_uid, role="customer")
    failed_key = "recovery-failed-1"
    failed_action = LifecycleActionService(backend).reserve(
        actor_uid=admin_uid,
        target_uid=failed_uid,
        target_role="customer",
        operation="disable",
        idempotency_key=failed_key,
        account_ref=account_reference(failed_uid),
    )
    backend.transition(
        failed_action.action_ref,
        expected_version=failed_action.version,
        to_state="failed",
        result_code="service_unavailable",
        now=datetime.now(timezone.utc),
    )
    run.track_action(
        actor_uid=admin_uid,
        target_uid=failed_uid,
        key=failed_key,
        operation="disable",
    )
    run.audit_refs.add(
        lifecycle_audit_event_reference(
            action_ref=failed_action.action_ref,
            operation="disable",
            from_state="reserved",
            to_state="failed",
            result_code="service_unavailable",
            version=2,
        )
    )
    failed_recovery = client.post(
        f"/admin/users/{account_reference(failed_uid)}/lifecycle-recovery",
        headers=headers,
        json={"operation": "disable"},
    )
    assert failed_recovery.status_code == 409
    assert failed_recovery.json()["error"]["code"] == "operator_recovery_required"


def test_emulator_recovery_request_contract_and_collection_integrity(lifecycle_app) -> None:
    run, client, _backend = lifecycle_app
    admin_uid, admin_token = run.create_identity("admin-contract")
    staff_uid, _staff_token = run.create_identity("staff-contract")
    run.set_profile(admin_uid, role="admin")
    run.set_profile(staff_uid, role="staff", department="card_atm")
    staff_ref = account_reference(staff_uid)
    headers = {"Authorization": f"Bearer {admin_token}"}

    invalid_requests = [
        {},
        {"operation": "disable", "departmentId": "card_atm"},
        {"operation": "reactivate", "departmentId": "card_atm"},
        {"operation": "reassign_department"},
        {"operation": "reassign_department", "departmentId": None},
        {"operation": "disable", "idempotencyKey": "secret-key"},
        {"operation": "disable", "actionRef": "a" * 64},
    ]
    for payload in invalid_requests:
        response = client.post(
            f"/admin/users/{staff_ref}/lifecycle-recovery",
            headers=headers,
            json=payload,
        )
        assert response.status_code == 422

    eligibility = client.get(
        f"/admin/users/{staff_ref}/lifecycle-eligibility", headers=headers
    )
    assert eligibility.status_code == 200
    assert "actionRef" not in eligibility.text
    assert "guardRef" not in eligibility.text
    assert "auditRef" not in eligibility.text
