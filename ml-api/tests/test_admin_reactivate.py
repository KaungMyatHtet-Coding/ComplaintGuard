"""Pure/fake tests for recoverable Admin reactivation."""

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.admin_auth import AdminPrincipal
from app.admin_directory import (
    AdminDirectoryRow,
    account_reference,
    validate_account_reference,
)
from app.admin_lifecycle import (
    InMemoryLifecycleRepository,
    LifecycleActionService,
    LifecycleAuditEvent,
    LifecycleReactivationNotEligible,
    LifecycleStateConflict,
    lifecycle_audit_event_reference,
)
from app.admin_reactivate import (
    AdminReactivateService,
    FirebaseAdminReactivationBackend,
    ReactivateAdminTarget,
    ReactivateAlreadyActive,
    ReactivateAuthIdentityMissing,
    ReactivateIncomplete,
    ReactivatePendingSetup,
)
from app.config import Settings
from app.main import create_app
from app.ticketing import AuthenticationError, PersistenceError

NOW = datetime(2026, 8, 23, 10, 0, tzinfo=timezone.utc)


def profile(uid: str, role: str, *, active: bool) -> dict[str, Any]:
    return {
        "email": f"{uid}@example.test",
        "displayName": f"Synthetic {uid}",
        "locale": "en",
        "role": role,
        "departmentId": "card_atm" if role == "staff" else None,
        "active": active,
        "accountState": "active" if active else "disabled",
        "createdAt": NOW,
        "updatedAt": NOW,
    }


class FakeReactivateBackend(InMemoryLifecycleRepository):
    def __init__(self, *, target_role: str = "customer", proven: bool = True) -> None:
        super().__init__()
        self.profiles = {
            "admin-uid": profile("admin-uid", "admin", active=True),
            "target-uid": profile("target-uid", target_role, active=False),
        }
        self.guards: dict[str, dict[str, Any]] = {}
        self.auth_calls: list[tuple[str, str]] = []
        self.order: list[str] = []
        self.fail_enable = False
        self.fail_profile = False
        self.fail_pending_transition = False
        self.fail_completion = False
        if proven:
            self._seed_completed_disable()

    def _seed_completed_disable(self) -> None:
        disabled = LifecycleActionService(self, clock=lambda: NOW).reserve(
            actor_uid="admin-uid",
            target_uid="target-uid",
            target_role=self.profiles["target-uid"]["role"],
            operation="disable",
            idempotency_key="disable_001",
            account_ref=account_reference("target-uid"),
        )
        current = disabled
        for state, result in (
            ("profile_inactivated", "profile_inactivated"),
            ("auth_disable_pending", "auth_disable_pending"),
            ("completed", "completed"),
        ):
            previous_state = current.state
            current = super().transition(
                current.action_ref,
                expected_version=current.version,
                to_state=state,
                result_code=result,
                now=NOW,
            )
            event_ref = lifecycle_audit_event_reference(
                action_ref=current.action_ref,
                operation="disable",
                from_state=previous_state,
                to_state=state,
                result_code=result,
                version=current.version,
            )
            self.audit_events[event_ref] = LifecycleAuditEvent(
                event_ref=event_ref,
                action_ref=current.action_ref,
                operation="disable",
                actor_uid=current.actor_uid,
                target_uid=current.target_uid,
                from_state=previous_state,
                to_state=state,
                result_code=result,
                version=current.version,
                created_at=NOW,
            )
        self.guards[current.target_uid] = {
            "action_ref": current.action_ref,
            "operation": "disable",
            "state": "inactive",
            "version": current.version,
        }

    def verify_id_token(self, token: str) -> dict[str, Any]:
        self.order.append("verify")
        if token != "admin-token":
            raise AuthenticationError("invalid token")
        return {"uid": "admin-uid", "email": "admin-uid@example.test"}

    def get_user_profile(self, uid: str) -> dict[str, Any] | None:
        self.order.append("actor_profile")
        return deepcopy(self.profiles.get(uid))

    def resolve_target(self, account_ref: str) -> tuple[str, AdminDirectoryRow]:
        self.order.append("resolve")
        validate_account_reference(account_ref)
        for uid, value in self.profiles.items():
            if account_reference(uid) == account_ref:
                return uid, AdminDirectoryRow(
                    email=value["email"],
                    displayName=value["displayName"],
                    locale=value["locale"],
                    role=value["role"],
                    departmentId=value["departmentId"],
                    active=value["active"],
                    accountState=value["accountState"],
                    accountRef=account_ref,
                )
        raise LookupError("account reference not found")

    def find_completed_disable_action(self, *, target_uid: str, account_ref: str, target_role: str):
        self.order.append("proof")
        guard = self.guards.get(target_uid)
        if not guard or guard["state"] != "inactive" or guard["operation"] != "disable":
            raise LifecycleReactivationNotEligible("proof missing")
        action = self.records[guard["action_ref"]]
        if action.state != "completed" or action.result_code != "completed" or action.account_ref != account_ref:
            raise LifecycleReactivationNotEligible("proof invalid")
        return action

    def reserve_reactivation(self, record):
        self.order.append("reserve_reactivate")
        existing = self.records.get(record.action_ref)
        if existing is not None:
            return existing
        guard = self.guards.get(record.target_uid)
        if not guard or guard["state"] != "inactive" or guard["action_ref"] != record.previous_action_ref:
            raise LifecycleStateConflict("guard proof invalid")
        self.records[record.action_ref] = record
        self.guards[record.target_uid] = {
            **guard,
            "action_ref": record.action_ref,
            "operation": "reactivate",
            "state": "active",
            "version": guard["version"] + 1,
        }
        self._active_target_actions[record.target_uid] = record.action_ref
        return record

    def transition(self, action_ref: str, *, expected_version: int, to_state: Any, result_code: str | None, now: datetime):
        self.order.append(f"transition:{to_state}")
        if to_state == "auth_enable_pending" and self.fail_pending_transition:
            raise PersistenceError("synthetic transition failure")
        if to_state == "profile_activation_pending" and self.fail_pending_transition:
            raise PersistenceError("synthetic transition failure")
        current = self.records[action_ref]
        updated = super().transition(
            action_ref,
            expected_version=expected_version,
            to_state=to_state,
            result_code=result_code,
            now=now,
        )
        if updated != current:
            self.guards[updated.target_uid]["state"] = "inactive" if to_state == "completed" else "active"
            self.guards[updated.target_uid]["version"] += 1
        return updated

    def enable_auth_identity(self, target_uid: str) -> None:
        self.order.append("auth_get")
        self.auth_calls.append(("get", target_uid))
        if self.fail_enable:
            raise ReactivateAuthIdentityMissing("synthetic missing identity")
        self.order.append("auth_enable")
        self.auth_calls.append(("enable", target_uid))

    def activate_profile(self, action_ref: str, *, expected_version: int, now: datetime):
        self.order.append("profile_activation_transaction")
        if self.fail_profile or self.fail_completion:
            raise PersistenceError("synthetic activation failure")
        current = self.records[action_ref]
        self.profiles[current.target_uid]["active"] = True
        self.profiles[current.target_uid]["updatedAt"] = now
        updated = super().transition(
            action_ref,
            expected_version=expected_version,
            to_state="completed",
            result_code="completed",
            now=now,
        )
        self.guards[current.target_uid]["state"] = "inactive"
        self.guards[current.target_uid]["version"] += 1
        return updated


def actor() -> AdminPrincipal:
    return AdminPrincipal(
        uid="admin-uid",
        email="admin-uid@example.test",
        display_name="Synthetic admin-uid",
        locale="en",
    )


def test_concrete_firebase_reactivation_backend_exposes_lifecycle_capabilities() -> None:
    class LifecycleSpy:
        def find_completed_disable_action(self, **kwargs: Any) -> str:
            assert kwargs["target_uid"] == "target-uid"
            return "completed-disable"

        def reserve_reactivation(self, record: object) -> object:
            return record

        def activate_profile(self, action_ref: str, *, expected_version: int, now: datetime) -> str:
            assert action_ref == "reactivate-action"
            assert expected_version == 3
            assert now == NOW
            return "completed"

    backend = object.__new__(FirebaseAdminReactivationBackend)
    backend._lifecycle = LifecycleSpy()
    record = object()

    assert backend.find_completed_disable_action(
        target_uid="target-uid",
        account_ref=account_reference("target-uid"),
        target_role="customer",
    ) == "completed-disable"
    assert backend.reserve_reactivation(record) is record
    assert backend.activate_profile(
        "reactivate-action", expected_version=3, now=NOW
    ) == "completed"


def reactivate(backend: FakeReactivateBackend, key: str = "reactivate_001"):
    return AdminReactivateService(backend, clock=lambda: NOW).reactivate(
        actor(), account_ref=account_reference("target-uid"), idempotency_key=key
    )


@pytest.mark.parametrize("role", ["customer", "staff", "manager"])
def test_customer_staff_manager_reactivation_success(role: str) -> None:
    backend = FakeReactivateBackend(target_role=role)
    result = reactivate(backend)
    assert result.model_dump(by_alias=True) == {
        "accountRef": account_reference("target-uid"),
        "operation": "reactivate",
        "status": "completed",
        "profileState": "active",
    }
    assert backend.profiles["target-uid"]["active"] is True
    assert backend.auth_calls == [("get", "target-uid"), ("enable", "target-uid")]
    assert backend.records[next(ref for ref, value in backend.records.items() if value.operation == "reactivate")].state == "completed"
    assert backend.guards["target-uid"]["state"] == "inactive"


def test_admin_target_rejected_without_writes() -> None:
    backend = FakeReactivateBackend(target_role="admin")
    with pytest.raises(ReactivateAdminTarget):
        reactivate(backend)
    assert not [record for record in backend.records.values() if record.operation == "reactivate"]
    assert backend.auth_calls == []


def test_pending_setup_and_unproven_inactive_rejected_without_writes() -> None:
    for proven in (False,):
        backend = FakeReactivateBackend(proven=proven)
        with pytest.raises(ReactivatePendingSetup):
            reactivate(backend)
        assert not [record for record in backend.records.values() if record.operation == "reactivate"]
        assert backend.auth_calls == []


def test_active_unrelated_target_rejected() -> None:
    backend = FakeReactivateBackend()
    backend.profiles["target-uid"]["active"] = True
    with pytest.raises(ReactivateAlreadyActive):
        reactivate(backend)


def test_auth_enable_failure_retains_pending_state_and_guard() -> None:
    backend = FakeReactivateBackend()
    backend.fail_enable = True
    with pytest.raises(ReactivateIncomplete):
        reactivate(backend)
    action = next(value for value in backend.records.values() if value.operation == "reactivate")
    assert action.state == "auth_enable_pending"
    assert backend.guards["target-uid"]["state"] == "active"
    assert backend.profiles["target-uid"]["active"] is False


def test_profile_activation_failure_keeps_access_denied_and_retries_same_action() -> None:
    backend = FakeReactivateBackend()
    backend.fail_profile = True
    with pytest.raises(ReactivateIncomplete):
        reactivate(backend)
    action = next(value for value in backend.records.values() if value.operation == "reactivate")
    assert action.state == "profile_activation_pending"
    assert backend.profiles["target-uid"]["active"] is False
    assert backend.guards["target-uid"]["state"] == "active"
    assert backend.auth_calls == [("get", "target-uid"), ("enable", "target-uid")]
    backend.fail_profile = False
    assert reactivate(backend).status == "completed"
    assert backend.auth_calls == [
        ("get", "target-uid"),
        ("enable", "target-uid"),
        ("get", "target-uid"),
        ("enable", "target-uid"),
    ]


def test_completed_retry_has_no_auth_or_profile_mutation() -> None:
    backend = FakeReactivateBackend()
    first = reactivate(backend)
    calls = list(backend.auth_calls)
    order_length = len(backend.order)
    assert reactivate(backend) == first
    assert backend.auth_calls == calls
    assert len(backend.order) == order_length + 2  # resolve and reservation validation


def test_authorization_precedes_resolution_and_auth_access() -> None:
    backend = FakeReactivateBackend()
    with TestClient(
        create_app(
            settings=Settings(model_path=Settings.default().model_path),
            model_loader=lambda *_args, **_kwargs: object(),
            admin_reactivate_backend=backend,
        )
    ) as client:
        response = client.post(
            f"/admin/users/{account_reference('target-uid')}/reactivate",
            headers={"Authorization": "Bearer invalid"},
            json={"idempotencyKey": "reactivate_001"},
        )
    assert response.status_code == 401
    assert backend.order == ["verify"]


def test_safe_route_response_and_strict_body() -> None:
    backend = FakeReactivateBackend()
    with TestClient(
        create_app(
            settings=Settings(model_path=Settings.default().model_path),
            model_loader=lambda *_args, **_kwargs: object(),
            admin_reactivate_backend=backend,
        )
    ) as client:
        response = client.post(
            f"/admin/users/{account_reference('target-uid')}/reactivate",
            headers={"Authorization": "Bearer admin-token"},
            json={"idempotencyKey": "reactivate_001", "password": "secret"},
        )
    assert response.status_code == 422
    assert "secret" not in response.text
