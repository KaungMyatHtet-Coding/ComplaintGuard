"""Pure tests for continuation of existing lifecycle actions."""

from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.admin_auth import AdminPrincipal
from app.admin_directory import AdminDirectoryRow, account_reference
from app.admin_lifecycle import (
    InMemoryLifecycleRepository,
    LifecycleActionRecord,
    LifecycleActionService,
    LifecycleRecoveryActorMismatch,
    LifecycleTargetGuard,
)
from app.admin_recovery import (
    AdminLifecycleRecoveryService,
    RecoveryLifecycleConflict,
)
from app.config import Settings
from app.main import create_app
from app.ticketing import AuthenticationError

NOW = datetime(2026, 8, 23, 10, 0, tzinfo=timezone.utc)
TARGET_REF = account_reference("target-uid")


def _profile(active: bool = True, role: str = "customer") -> dict[str, Any]:
    return {
        "email": "target@example.test",
        "displayName": "Synthetic Target",
        "locale": "en",
        "role": role,
        "departmentId": "card_atm" if role == "staff" else None,
        "active": active,
        "createdAt": NOW,
        "updatedAt": NOW,
    }


def _actor(uid: str = "admin-uid") -> AdminPrincipal:
    return AdminPrincipal(
        uid=uid,
        email=f"{uid}@example.test",
        display_name="Synthetic Admin",
        locale="en",
    )


class FakeRecoveryBackend(InMemoryLifecycleRepository):
    def __init__(self, action: LifecycleActionRecord) -> None:
        super().__init__()
        self.records[action.action_ref] = action
        self.profiles = {"target-uid": _profile(active=action.operation != "reactivate")}
        self.action = action
        self.guard = LifecycleTargetGuard(
            guard_ref="a" * 64,
            target_uid="target-uid",
            action_ref=action.action_ref,
            operation=action.operation,
            state="inactive" if action.state in {"completed", "conflict"} else "active",
            version=action.version,
            created_at=NOW,
            updated_at=NOW,
        )
        self.order: list[str] = []
        self.auth_calls: list[str] = []
        self.reserve_called = False

    def verify_id_token(self, token: str) -> dict[str, str]:
        self.order.append("verify")
        if token != "admin-token":
            raise AuthenticationError("invalid token")
        return {"uid": "admin-uid", "email": "admin-uid@example.test"}

    def get_user_profile(self, uid: str) -> dict[str, Any] | None:
        self.order.append("actor_profile")
        if uid == "admin-uid":
            return {
                "uid": uid,
                "email": "admin-uid@example.test",
                "displayName": "Synthetic Admin",
                "locale": "en",
                "role": "admin",
                "departmentId": None,
                "active": True,
                "createdAt": NOW,
                "updatedAt": NOW,
            }
        return None

    def resolve_target(self, account_ref: str) -> tuple[str, AdminDirectoryRow]:
        self.order.append("resolve")
        return "target-uid", AdminDirectoryRow(
            email="target@example.test",
            displayName="Synthetic Target",
            locale="en",
            role=self.action.target_role,
            departmentId="card_atm" if self.action.target_role == "staff" else None,
            active=self.profiles["target-uid"]["active"],
            setupStatus="active",
            accountRef=account_ref,
        )

    def recover_existing_action(self, **kwargs: Any):
        self.order.append("discover")
        if kwargs["actor_uid"] != self.action.actor_uid:
            raise LifecycleRecoveryActorMismatch("actor mismatch")
        assert kwargs["target_uid"] == self.action.target_uid
        assert kwargs["account_ref"] == TARGET_REF
        assert kwargs["operation"] == self.action.operation
        return self.action, self.guard

    def reserve(self, record: LifecycleActionRecord) -> LifecycleActionRecord:
        self.reserve_called = True
        raise AssertionError("recovery must never reserve a new action")

    def transition(self, action_ref: str, **kwargs: Any) -> LifecycleActionRecord:
        self.order.append(f"transition:{kwargs['to_state']}")
        self.action = super().transition(
            action_ref,
            expected_version=kwargs["expected_version"],
            to_state=kwargs["to_state"],
            result_code=kwargs["result_code"],
            now=kwargs["now"],
        )
        return self.action

    def inactivate_profile(self, action_ref: str, *, now: datetime) -> LifecycleActionRecord:
        self.order.append("profile")
        if self.action.state == "reserved":
            self.action = super().transition(
                action_ref,
                expected_version=self.action.version,
                to_state="profile_inactivated",
                result_code="profile_inactivated",
                now=now,
            )
        return self.action

    def disable_auth_identity(self, target_uid: str) -> None:
        self.auth_calls.append("disable")

    def revoke_refresh_tokens(self, target_uid: str) -> None:
        self.auth_calls.append("revoke")

    def enable_auth_identity(self, target_uid: str) -> None:
        self.auth_calls.append("enable")

    def activate_profile(self, action_ref: str, *, expected_version: int, now: datetime) -> LifecycleActionRecord:
        self.order.append("activate")
        self.action = super().transition(
            action_ref,
            expected_version=expected_version,
            to_state="completed",
            result_code="completed",
            now=now,
        )
        return self.action

    def reassign_department(self, action_ref: str, *, expected_version: int, now: datetime) -> LifecycleActionRecord:
        self.order.append("reassign")
        self.action = super().transition(
            action_ref,
            expected_version=expected_version,
            to_state="completed",
            result_code="completed",
            now=now,
        )
        return self.action


def _new_action(operation: str, *, target_role: str = "customer", state: str = "reserved") -> LifecycleActionRecord:
    repository = InMemoryLifecycleRepository()
    action = LifecycleActionService(repository, clock=lambda: NOW).reserve(
        actor_uid="admin-uid",
        target_uid="target-uid",
        target_role=target_role,
        operation=operation,
        idempotency_key="original_1",
        account_ref=TARGET_REF,
        requested_department="card_atm" if operation == "reassign_department" else None,
    )
    current = action
    paths = {
        "profile_inactivated": [("profile_inactivated", "profile_inactivated")],
        "auth_disable_pending": [("profile_inactivated", "profile_inactivated"), ("auth_disable_pending", "auth_disable_pending")],
        "auth_enable_pending": [("auth_enable_pending", "auth_enable_pending")],
        "profile_activation_pending": [("auth_enable_pending", "auth_enable_pending"), ("profile_activation_pending", "profile_activation_pending")],
        "completed": {
            "disable": [
                ("profile_inactivated", "profile_inactivated"),
                ("auth_disable_pending", "auth_disable_pending"),
                ("completed", "completed"),
            ],
            "reactivate": [
                ("auth_enable_pending", "auth_enable_pending"),
                ("profile_activation_pending", "profile_activation_pending"),
                ("completed", "completed"),
            ],
            "reassign_department": [("completed", "completed")],
        },
        "conflict": [("conflict", "lifecycle_conflict")],
    }
    path = paths.get(state, [])
    if state == "completed":
        path = paths[state][operation]
    for next_state, result in path:
        current = repository.transition(
            current.action_ref,
            expected_version=current.version,
            to_state=next_state,  # type: ignore[arg-type]
            result_code=result,
            now=NOW,
        )
    return current


@pytest.mark.parametrize(
    ("operation", "state", "role"),
    [
        ("disable", "reserved", "customer"),
        ("disable", "profile_inactivated", "customer"),
        ("disable", "auth_disable_pending", "customer"),
        ("disable", "completed", "customer"),
        ("reactivate", "reserved", "customer"),
        ("reactivate", "auth_enable_pending", "customer"),
        ("reactivate", "profile_activation_pending", "customer"),
        ("reactivate", "completed", "customer"),
        ("reassign_department", "reserved", "staff"),
        ("reassign_department", "completed", "staff"),
        ("reassign_department", "conflict", "staff"),
    ],
)
def test_recovery_discovers_only_the_existing_action(operation: str, state: str, role: str) -> None:
    action = _new_action(operation, target_role=role, state=state)
    backend = FakeRecoveryBackend(action)
    if state == "conflict":
        with pytest.raises(RecoveryLifecycleConflict):
            AdminLifecycleRecoveryService(backend, clock=lambda: NOW).recover(
                _actor(), account_ref=TARGET_REF, operation=operation, department_id="card_atm" if role == "staff" else None
            )
    elif state == "completed":
        result = AdminLifecycleRecoveryService(backend, clock=lambda: NOW).recover(
            _actor(), account_ref=TARGET_REF, operation=operation, department_id="card_atm" if role == "staff" else None
        )
        assert result.status == "completed"
        assert backend.auth_calls == []
    else:
        result = AdminLifecycleRecoveryService(backend, clock=lambda: NOW).recover(
            _actor(), account_ref=TARGET_REF, operation=operation, department_id="card_atm" if role == "staff" else None
        )
        assert result.status == "completed"
    assert backend.reserve_called is False
    assert backend.order[:2] == ["resolve", "discover"]


def test_different_actor_is_rejected_before_continuation() -> None:
    action = _new_action("disable")
    backend = FakeRecoveryBackend(action)
    with pytest.raises(LifecycleRecoveryActorMismatch):
        AdminLifecycleRecoveryService(backend).recover(
            _actor("other-admin"), account_ref=TARGET_REF, operation="disable"
        )


def _fake_loader(*_args: Any, **_kwargs: Any):
    class FakeClassifier:
        model_version = "v1"

    return FakeClassifier()


def test_route_authorizes_before_recovery_lookup_and_rejects_idempotency_key() -> None:
    backend = _FakeRouteBackend()
    with TestClient(create_app(settings=Settings.default(), model_loader=_fake_loader, admin_recovery_backend=backend)) as client:
        denied = client.post(
            f"/admin/users/{TARGET_REF}/lifecycle-recovery",
            headers={"Authorization": "Bearer wrong-token"},
            json={"operation": "disable"},
        )
        malformed = client.post(
            f"/admin/users/{TARGET_REF}/lifecycle-recovery",
            headers={"Authorization": "Bearer admin-token"},
            json={"operation": "disable", "idempotencyKey": "lost-key"},
        )
    assert denied.status_code == 401
    assert malformed.status_code == 422
    assert backend.order == ["verify"]


class _FakeRouteBackend(FakeRecoveryBackend):
    def __init__(self) -> None:
        super().__init__(_new_action("disable"))


def test_completed_route_returns_exact_safe_response_without_continuation_writes() -> None:
    backend = _FakeRouteBackend()
    backend.action = _new_action("disable", state="completed")
    backend.records = {backend.action.action_ref: backend.action}
    backend.guard = LifecycleTargetGuard(
        guard_ref="a" * 64,
        target_uid="target-uid",
        action_ref=backend.action.action_ref,
        operation="disable",
        state="inactive",
        version=backend.action.version,
        created_at=NOW,
        updated_at=NOW,
    )
    with TestClient(create_app(settings=Settings.default(), model_loader=_fake_loader, admin_recovery_backend=backend)) as client:
        response = client.post(
            f"/admin/users/{TARGET_REF}/lifecycle-recovery",
            headers={"Authorization": "Bearer admin-token"},
            json={"operation": "disable"},
        )
    assert response.status_code == 200
    assert set(response.json()) == {"accountRef", "operation", "status", "profileState"}
    assert response.json()["operation"] == "disable"
    assert backend.auth_calls == []
