"""Pure/fake tests for the recoverable Admin disable workflow."""

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
from app.admin_disable import (
    AdminDisableService,
    DisableAdminTarget,
    DisableAlreadyInactive,
    DisableAuthIdentityMissing,
    DisableIncomplete,
)
from app.admin_lifecycle import (
    InMemoryLifecycleRepository,
    LifecycleActionService,
    LifecycleStateConflict,
    LifecycleValidationError,
)
from app.config import Settings
from app.main import create_app
from app.ticketing import AuthenticationError, PersistenceError

NOW = datetime(2026, 8, 23, 10, 0, tzinfo=timezone.utc)


def profile(uid: str, role: str, *, active: bool = True) -> dict[str, Any]:
    return {
        "email": f"{uid}@example.test",
        "displayName": f"Synthetic {uid}",
        "locale": "en",
        "role": role,
        "departmentId": "card_atm" if role == "staff" else None,
        "active": active,
        "createdAt": NOW,
        "updatedAt": NOW,
    }


class FakeDisableBackend(InMemoryLifecycleRepository):
    def __init__(self, *, target_role: str = "customer", target_active: bool = True) -> None:
        super().__init__()
        self.profiles = {
            "admin-uid": profile("admin-uid", "admin"),
            "target-uid": profile("target-uid", target_role, active=target_active),
        }
        self.auth_calls: list[tuple[str, str]] = []
        self.order: list[str] = []
        self.fail_profile = False
        self.fail_disable = False
        self.fail_revoke = False
        self.fail_completion_once = False
        self.missing_auth = False

    def verify_id_token(self, token: str) -> dict[str, Any]:
        self.order.append("verify")
        if token != "admin-token":
            raise AuthenticationError("invalid Firebase ID token")
        return {"uid": "admin-uid", "email": "admin-uid@example.test"}

    def get_user_profile(self, uid: str) -> dict[str, Any] | None:
        self.order.append("actor_profile")
        return self.profiles.get(uid)

    def resolve_target(self, account_ref: str) -> tuple[str, AdminDirectoryRow]:
        self.order.append("resolve")
        validate_account_reference(account_ref)
        for uid, value in self.profiles.items():
            if account_reference(uid) == account_ref:
                try:
                    return uid, AdminDirectoryRow(
                        email=value["email"],
                        displayName=value["displayName"],
                        locale=value["locale"],
                        role=value["role"],
                        departmentId=value["departmentId"],
                        active=value["active"],
                        setupStatus="active" if value["active"] else "pending_setup",
                        accountRef=account_ref,
                    )
                except Exception as exc:
                    raise LifecycleValidationError("target profile is invalid") from exc
        raise LookupError("account reference not found")

    def inactivate_profile(self, action_ref: str, *, now: datetime):
        self.order.append("profile_transaction")
        if self.fail_profile:
            raise PersistenceError("synthetic profile transaction failure")
        before_records = deepcopy(self.records)
        before_active = deepcopy(self._active_target_actions)
        before_audit = deepcopy(self.audit_events)
        before_profile = deepcopy(self.profiles["target-uid"])
        try:
            current = self.records[action_ref]
            if current.state != "reserved":
                return current
            if self.profiles[current.target_uid]["active"] is not True:
                raise LifecycleStateConflict("profile state is inconsistent")
            self.profiles[current.target_uid]["active"] = False
            self.profiles[current.target_uid]["updatedAt"] = now
            updated = super().transition(
                action_ref,
                expected_version=current.version,
                to_state="profile_inactivated",
                result_code="profile_inactivated",
                now=now,
            )
            LifecycleActionService(self, clock=lambda: now).append_transition_audit(
                updated, from_state=current.state
            )
            return updated
        except Exception:
            self.records = before_records
            self._active_target_actions = before_active
            self.audit_events = before_audit
            self.profiles["target-uid"] = before_profile
            raise

    def transition(self, action_ref: str, *, expected_version: int, to_state: Any, result_code: str | None, now: datetime):
        self.order.append(f"transition:{to_state}")
        if to_state == "completed" and self.fail_completion_once:
            self.fail_completion_once = False
            raise PersistenceError("synthetic completion failure")
        current = self.records[action_ref]
        updated = super().transition(
            action_ref,
            expected_version=expected_version,
            to_state=to_state,
            result_code=result_code,
            now=now,
        )
        if updated != current:
            LifecycleActionService(self, clock=lambda: now).append_transition_audit(
                updated, from_state=current.state
            )
        return updated

    def disable_auth_identity(self, target_uid: str) -> None:
        self.order.append("auth_disable")
        self.auth_calls.append(("disable", target_uid))
        if self.missing_auth:
            raise DisableAuthIdentityMissing("synthetic missing identity")
        if self.fail_disable:
            raise DisableIncomplete("synthetic Auth disable failure")

    def revoke_refresh_tokens(self, target_uid: str) -> None:
        self.order.append("auth_revoke")
        self.auth_calls.append(("revoke", target_uid))
        if self.fail_revoke:
            raise DisableIncomplete("synthetic revocation failure")


def actor() -> AdminPrincipal:
    return AdminPrincipal(
        uid="admin-uid",
        email="admin-uid@example.test",
        display_name="Synthetic admin-uid",
        locale="en",
    )


def disable(backend: FakeDisableBackend, key: str = "disable_001"):
    return AdminDisableService(backend, clock=lambda: NOW).disable(
        actor(), account_ref=account_reference("target-uid"), idempotency_key=key
    )


@pytest.mark.parametrize("role", ["customer", "staff", "manager"])
def test_customer_staff_manager_disable_success(role: str) -> None:
    backend = FakeDisableBackend(target_role=role)
    result = disable(backend)
    assert result.model_dump(by_alias=True) == {
        "accountRef": account_reference("target-uid"),
        "operation": "disable",
        "status": "completed",
        "profileState": "inactive",
    }
    assert backend.profiles["target-uid"]["active"] is False
    assert backend.auth_calls == [("disable", "target-uid"), ("revoke", "target-uid")]
    assert backend.records[next(iter(backend.records))].state == "completed"
    assert len(backend.audit_events) == 3


def test_admin_target_is_deferred_without_writes() -> None:
    backend = FakeDisableBackend(target_role="admin")
    backend.profiles["target-uid"]["email"] = "other-admin@example.test"
    with pytest.raises(DisableAdminTarget):
        disable(backend)
    assert not backend.records
    assert not backend.audit_events
    assert backend.auth_calls == []


def test_inactive_target_rejected_without_writes() -> None:
    backend = FakeDisableBackend(target_active=False)
    with pytest.raises(DisableAlreadyInactive):
        disable(backend)
    assert not backend.records and not backend.audit_events and backend.auth_calls == []


def test_profile_transaction_preserves_all_fields_and_no_auth_on_failure() -> None:
    backend = FakeDisableBackend()
    before = deepcopy(backend.profiles["target-uid"])
    backend.fail_profile = True
    with pytest.raises(PersistenceError):
        disable(backend)
    assert backend.profiles["target-uid"] == before
    assert backend.auth_calls == []
    action = next(iter(backend.records.values()))
    assert action.state == "reserved"
    assert backend._active_target_actions["target-uid"] == action.action_ref
    assert not backend.audit_events


def test_denied_request_performs_no_target_or_lifecycle_access() -> None:
    backend = FakeDisableBackend()
    with TestClient(
        create_app(
            settings=Settings(model_path=Settings.default().model_path),
            model_loader=fake_loader,
            admin_disable_backend=backend,
        )
    ) as client:
        response = client.post(
            f"/admin/users/{account_reference('target-uid')}/disable",
            headers={"Authorization": "Bearer wrong-token"},
            json={"idempotencyKey": "disable_001"},
        )
    assert response.status_code == 401
    assert backend.order == ["verify"]
    assert not backend.records and not backend.audit_events and backend.auth_calls == []


def test_auth_failure_retains_recovery_state_and_retry_completes() -> None:
    backend = FakeDisableBackend()
    backend.fail_disable = True
    with pytest.raises(DisableIncomplete):
        disable(backend)
    action = next(iter(backend.records.values()))
    assert action.state == "auth_disable_pending"
    assert backend.profiles["target-uid"]["active"] is False
    assert backend._active_target_actions["target-uid"] == action.action_ref
    assert backend.auth_calls == [("disable", "target-uid")]
    backend.fail_disable = False
    assert disable(backend).status == "completed"
    assert len(backend.audit_events) == 3
    assert "target-uid" not in backend._active_target_actions


def test_revocation_failure_calls_disable_first_and_retains_guard() -> None:
    backend = FakeDisableBackend()
    backend.fail_revoke = True
    with pytest.raises(DisableIncomplete):
        disable(backend)
    action = next(iter(backend.records.values()))
    assert action.state == "auth_disable_pending"
    assert backend.auth_calls == [("disable", "target-uid"), ("revoke", "target-uid")]


def test_completion_failure_retries_same_action_without_duplicate_profile_audit() -> None:
    backend = FakeDisableBackend()
    backend.fail_completion_once = True
    with pytest.raises(DisableIncomplete):
        disable(backend)
    action_ref = next(iter(backend.records))
    assert backend.records[action_ref].state == "auth_disable_pending"
    assert len(backend.audit_events) == 2
    assert disable(backend).status == "completed"
    assert len(backend.audit_events) == 3


def test_same_completed_retry_returns_safe_response_and_no_auth_repeat() -> None:
    backend = FakeDisableBackend()
    first = disable(backend)
    calls = list(backend.auth_calls)
    second = disable(backend)
    assert second == first
    assert backend.auth_calls == calls


def test_missing_auth_identity_never_creates_identity() -> None:
    backend = FakeDisableBackend()
    backend.missing_auth = True
    with pytest.raises(DisableIncomplete):
        disable(backend)
    assert backend.auth_calls == [("disable", "target-uid")]


def test_strict_profile_and_account_reference_validation() -> None:
    backend = FakeDisableBackend()
    backend.profiles["target-uid"]["departmentId"] = "wrong"
    with pytest.raises(LifecycleValidationError):
        disable(backend)
    with pytest.raises(ValueError):
        AdminDisableService(backend, clock=lambda: NOW).disable(
            actor(), account_ref="uid-target-uid", idempotency_key="disable_001"
        )


def fake_loader(*_args: Any, **_kwargs: Any):
    class FakeClassifier:
        model_version = "v1"

    return FakeClassifier()


def test_route_safe_mapping_and_no_frontend_control() -> None:
    backend = FakeDisableBackend()
    with TestClient(
        create_app(
            settings=Settings(model_path=Settings.default().model_path),
            model_loader=fake_loader,
            admin_disable_backend=backend,
        )
    ) as client:
        response = client.post(
            f"/admin/users/{account_reference('target-uid')}/disable",
            headers={"Authorization": "Bearer admin-token"},
            json={"idempotencyKey": "disable_001"},
        )
    assert response.status_code == 200
    assert set(response.json()) == {"accountRef", "operation", "status", "profileState"}
    assert "target-uid" not in response.text
    assert "actionRef" not in response.text
    assert "audit" not in response.text.lower()
    assert backend.order.index("verify") < backend.order.index("actor_profile") < backend.order.index("resolve")


def test_route_rejects_unknown_request_fields_and_bad_reference() -> None:
    backend = FakeDisableBackend()
    with TestClient(
        create_app(
            settings=Settings(model_path=Settings.default().model_path),
            model_loader=fake_loader,
            admin_disable_backend=backend,
        )
    ) as client:
        unknown = client.post(
            "/admin/users/acct_v1_" + "a" * 64 + "/disable",
            headers={"Authorization": "Bearer admin-token"},
            json={"idempotencyKey": "disable_001", "password": "secret"},
        )
        malformed = client.post(
            "/admin/users/not-an-account/disable",
            headers={"Authorization": "Bearer admin-token"},
            json={"idempotencyKey": "disable_001"},
        )
    assert unknown.status_code == 422
    assert "secret" not in unknown.text
    assert malformed.status_code == 422
