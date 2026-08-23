"""Pure tests for the actor-bound lifecycle recovery-status projection."""

from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.admin_auth import AdminPrincipal
from app.admin_directory import AdminDirectoryRow, account_reference
from app.admin_recovery_status import AdminLifecycleRecoveryStatusService
from app.config import Settings
from app.main import create_app
from app.schemas import AdminLifecycleRecoveryStatusResponse
from app.ticketing import AuthenticationError

NOW = datetime(2026, 8, 23, 10, 0, tzinfo=timezone.utc)
TARGET_REF = account_reference("target-uid")


def _profile(uid: str, role: str = "admin", active: bool = True) -> dict[str, Any]:
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


class FakeStatusBackend:
    def __init__(self) -> None:
        self.order: list[str] = []
        self.status: tuple[str, str | None, str | None] = ("none", None, None)
        self.original_actor = "admin-uid"
        self.profiles = {
            "admin-uid": _profile("admin-uid"),
            "other-admin": _profile("other-admin"),
            "target-uid": _profile("target-uid", role="customer", active=False),
        }

    def verify_id_token(self, token: str) -> dict[str, str]:
        self.order.append("verify")
        if token not in {"admin-token", "other-token"}:
            raise AuthenticationError("invalid token")
        uid = "other-admin" if token == "other-token" else "admin-uid"
        return {"uid": uid, "email": f"{uid}@example.test"}

    def get_user_profile(self, uid: str) -> dict[str, Any] | None:
        self.order.append("actor_profile")
        return self.profiles.get(uid)

    def resolve_target(self, account_ref: str) -> tuple[str, AdminDirectoryRow]:
        self.order.append("resolve")
        if account_ref != TARGET_REF:
            raise LookupError("not found")
        value = self.profiles["target-uid"]
        return "target-uid", AdminDirectoryRow(
            email=value["email"],
            displayName=value["displayName"],
            locale=value["locale"],
            role=value["role"],
            departmentId=value["departmentId"],
            active=value["active"],
            setupStatus="active" if value["active"] else "pending_setup",
            accountRef=TARGET_REF,
        )

    def recovery_status(self, **kwargs: Any) -> tuple[str, str | None, str | None]:
        self.order.append("recovery_status")
        if kwargs["actor_uid"] != self.original_actor:
            return "none", None, None
        return self.status


def _actor(uid: str = "admin-uid") -> AdminPrincipal:
    return AdminPrincipal(
        uid=uid,
        email=f"{uid}@example.test",
        display_name="Synthetic Admin",
        locale="en",
    )


def _app(backend: FakeStatusBackend):
    class FakeClassifier:
        model_version = "v1"

    return create_app(
        settings=Settings.default(),
        model_loader=lambda *_args, **_kwargs: FakeClassifier(),
        admin_recovery_status_backend=backend,
    )


@pytest.mark.parametrize(
    ("status", "operation", "department"),
    [
        ("none", None, None),
        ("recoverable", "disable", None),
        ("recoverable", "reactivate", None),
        ("recoverable", "reassign_department", "card_atm"),
        ("completed", "disable", None),
        ("completed", "reactivate", None),
        ("completed", "reassign_department", "fraud_security"),
        ("operator_required", None, None),
    ],
)
def test_projection_response_has_exact_safe_union(
    status: str, operation: str | None, department: str | None
) -> None:
    backend = FakeStatusBackend()
    backend.status = (status, operation, department)
    response = AdminLifecycleRecoveryStatusService(backend).status(
        _actor(), account_ref=TARGET_REF
    )
    assert response.model_dump(by_alias=True) == {
        "accountRef": TARGET_REF,
        "recoveryState": status,
        "operation": operation,
        "departmentId": department,
    }
    assert set(response.model_dump(by_alias=True)) == {
        "accountRef",
        "recoveryState",
        "operation",
        "departmentId",
    }


def test_authorization_precedes_target_and_recovery_lookup() -> None:
    backend = FakeStatusBackend()
    with TestClient(_app(backend)) as client:
        response = client.get(
            f"/admin/users/{TARGET_REF}/lifecycle-recovery-status",
            headers={"Authorization": "Bearer invalid"},
        )
    assert response.status_code == 401
    assert backend.order == ["verify"]


def test_malformed_account_reference_is_rejected_before_resolution() -> None:
    backend = FakeStatusBackend()
    with TestClient(_app(backend)) as client:
        response = client.get(
            "/admin/users/not-an-account/lifecycle-recovery-status",
            headers={"Authorization": "Bearer admin-token"},
        )
    assert response.status_code == 422
    assert backend.order == ["verify", "actor_profile"]


def test_unknown_target_is_safe_not_found() -> None:
    backend = FakeStatusBackend()
    with TestClient(_app(backend)) as client:
        response = client.get(
            "/admin/users/acct_v1_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/lifecycle-recovery-status",
            headers={"Authorization": "Bearer admin-token"},
        )
    assert response.status_code == 404
    assert "operation" not in response.text


def test_different_original_admin_receives_exact_none_shape() -> None:
    backend = FakeStatusBackend()
    backend.status = ("recoverable", "reassign_department", "card_atm")
    with TestClient(_app(backend)) as client:
        response = client.get(
            f"/admin/users/{TARGET_REF}/lifecycle-recovery-status",
            headers={"Authorization": "Bearer other-token"},
        )
    assert response.status_code == 200
    assert response.json() == {
        "accountRef": TARGET_REF,
        "recoveryState": "none",
        "operation": None,
        "departmentId": None,
    }


def test_admin_target_does_not_query_lifecycle_status() -> None:
    backend = FakeStatusBackend()
    backend.profiles["target-uid"] = _profile("target-uid", role="admin")
    with TestClient(_app(backend)) as client:
        response = client.get(
            f"/admin/users/{TARGET_REF}/lifecycle-recovery-status",
            headers={"Authorization": "Bearer admin-token"},
        )
    assert response.status_code == 200
    assert response.json()["recoveryState"] == "none"
    assert "recovery_status" not in backend.order


def test_self_target_projects_none_without_lifecycle_lookup() -> None:
    backend = FakeStatusBackend()
    response = AdminLifecycleRecoveryStatusService(backend).status(
        _actor("target-uid"), account_ref=TARGET_REF
    )
    assert response.model_dump(by_alias=True) == {
        "accountRef": TARGET_REF,
        "recoveryState": "none",
        "operation": None,
        "departmentId": None,
    }
    assert "recovery_status" not in backend.order


def test_no_guard_projection_has_exact_none_shape() -> None:
    backend = FakeStatusBackend()
    backend.status = ("none", None, None)
    response = AdminLifecycleRecoveryStatusService(backend).status(
        _actor(), account_ref=TARGET_REF
    )
    assert response.model_dump(by_alias=True) == {
        "accountRef": TARGET_REF,
        "recoveryState": "none",
        "operation": None,
        "departmentId": None,
    }


def test_response_model_rejects_invalid_public_combinations() -> None:
    with pytest.raises(ValueError):
        AdminLifecycleRecoveryStatusResponse(
            accountRef=TARGET_REF,
            recoveryState="none",
            operation="disable",
            departmentId=None,
        )
    with pytest.raises(ValueError):
        AdminLifecycleRecoveryStatusResponse(
            accountRef=TARGET_REF,
            recoveryState="operator_required",
            operation=None,
            departmentId="card_atm",
        )
    with pytest.raises(ValueError):
        AdminLifecycleRecoveryStatusResponse(
            accountRef=TARGET_REF,
            recoveryState="recoverable",
            operation="disable",
            departmentId="card_atm",
        )
