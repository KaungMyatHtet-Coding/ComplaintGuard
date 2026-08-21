"""Pure/fake tests for pending Staff/Manager provisioning."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.admin_auth import AdminPrincipal
from app.admin_workflow import (
    ADMIN_PROVISIONING_ACTION_DOMAIN,
    AdminProvisioningService,
    AuthIdentity,
    ProvisioningEmailExists,
    ProvisioningIdempotencyConflict,
    ProvisioningIncomplete,
    ProvisioningProfileConflict,
    _action_id,
    idempotency_key_fingerprint,
    request_fingerprint,
)
from app.config import Settings
from app.main import create_app
from app.schemas import AdminProvisioningRequest
from app.ticketing import AuthenticationError


class FakeProvisioningBackend:
    server_timestamp = "SERVER_TIMESTAMP"

    def __init__(self, *, role: str = "admin", active: bool = True) -> None:
        self.role = role
        self.active = active
        self.actions: dict[str, dict[str, Any]] = {}
        self.identities: dict[str, AuthIdentity] = {}
        self.email_uids: dict[str, str] = {}
        self.profiles: dict[str, dict[str, Any]] = {}
        self.create_calls = 0
        self.fail_create = False
        self.fail_complete_once = False

    def verify_id_token(self, token: str) -> dict[str, Any]:
        if token != "admin-token":
            raise AuthenticationError("invalid Firebase ID token")
        return {"uid": "admin-uid", "email": "admin@example.test"}

    def get_user_profile(self, uid: str) -> dict[str, Any] | None:
        if uid != "admin-uid":
            return None
        return {
            "email": "admin@example.test",
            "displayName": "Synthetic Admin",
            "locale": "en",
            "role": self.role,
            "departmentId": None,
            "active": self.active,
            "createdAt": "created",
            "updatedAt": "updated",
        }

    def reserve_action(
        self,
        *,
        action_id: str,
        actor_uid: str,
        key_fingerprint: str,
        request_fingerprint: str,
    ) -> dict[str, Any] | None:
        existing = self.actions.get(action_id)
        if existing is not None:
            return deepcopy(existing)
        self.actions[action_id] = {
            "actorUid": actor_uid,
            "actionId": action_id,
            "idempotencyKeyFingerprint": key_fingerprint,
            "requestFingerprint": request_fingerprint,
            "operation": "create_pending_user",
            "targetUid": None,
            "status": "started",
            "resultCode": None,
            "createdAt": self.server_timestamp,
            "updatedAt": self.server_timestamp,
        }
        return None

    def create_disabled_auth(self, *, email: str, display_name: str) -> AuthIdentity:
        if self.fail_create:
            raise RuntimeError("synthetic Auth failure")
        if email in self.email_uids:
            raise ProvisioningEmailExists("target email already exists")
        self.create_calls += 1
        identity = AuthIdentity(
            uid=f"target-{self.create_calls}",
            email=email,
            display_name=display_name,
            disabled=True,
        )
        self.identities[identity.uid] = identity
        self.email_uids[email] = identity.uid
        return identity

    def get_auth_identity(self, uid: str) -> AuthIdentity:
        return self.identities[uid]

    def record_target(self, *, action_id: str, target_uid: str) -> None:
        current = self.actions[action_id].get("targetUid")
        if current is not None and current != target_uid:
            raise ProvisioningIdempotencyConflict("target conflict")
        self.actions[action_id]["targetUid"] = target_uid

    def complete_pending(
        self,
        *,
        action_id: str,
        identity: AuthIdentity,
        request: AdminProvisioningRequest,
    ) -> None:
        if self.fail_complete_once:
            self.fail_complete_once = False
            raise RuntimeError("synthetic profile failure")
        existing = self.profiles.get(identity.uid)
        expected = {
            "email": identity.email,
            "displayName": identity.display_name,
            "locale": request.locale,
            "role": request.role,
            "departmentId": request.department_id,
            "active": False,
        }
        if existing is not None:
            if any(existing.get(key) != value for key, value in expected.items()):
                raise ProvisioningProfileConflict("profile conflict")
        else:
            self.profiles[identity.uid] = {
                **expected,
                "createdAt": self.server_timestamp,
                "updatedAt": self.server_timestamp,
            }
        self.actions[action_id].update(
            status="pending_setup",
            resultCode="pending_setup",
            updatedAt=self.server_timestamp,
        )

    def mark_action_failed(self, *, action_id: str, code: str) -> None:
        self.actions[action_id].update(
            status="failed", resultCode=code, updatedAt=self.server_timestamp
        )


def request(**overrides: Any) -> AdminProvisioningRequest:
    payload = {
        "email": "staff@example.test",
        "displayName": "Synthetic Staff",
        "locale": "en",
        "role": "staff",
        "departmentId": "card_atm",
        "idempotencyKey": "action_001",
    }
    payload.update(overrides)
    return AdminProvisioningRequest.model_validate(payload)


def admin() -> AdminPrincipal:
    return AdminPrincipal(
        uid="admin-uid",
        email="admin@example.test",
        display_name="Synthetic Admin",
        locale="en",
    )


def test_action_id_is_deterministic_for_same_actor_and_normalized_key() -> None:
    normalized = request(idempotencyKey=" action_001 ").idempotency_key
    assert normalized == "action_001"
    assert _action_id("admin-uid", normalized) == _action_id(
        "admin-uid", "action_001"
    )


def test_action_id_changes_for_different_key_or_actor() -> None:
    assert _action_id("admin-uid", "action_001") != _action_id(
        "admin-uid", "action_002"
    )
    assert _action_id("other-admin", "action_001") != _action_id(
        "admin-uid", "action_001"
    )


def test_action_id_preimage_boundaries_are_unambiguous() -> None:
    assert _action_id("ab", "c") != _action_id("a", "bc")


def test_action_id_is_lowercase_sha256_hex_and_contains_no_raw_values() -> None:
    actor = "admin-uid"
    key = "action_001"
    action_id = _action_id(actor, key)
    assert len(action_id) == 64
    assert action_id == action_id.lower()
    assert all(character in "0123456789abcdef" for character in action_id)
    assert actor not in action_id
    assert key not in action_id


def test_action_id_has_stable_versioned_domain_vector() -> None:
    assert ADMIN_PROVISIONING_ACTION_DOMAIN == "complaintguard:admin-provisioning:v1"
    assert _action_id("admin-uid", "action_001") == (
        "b1eb299a79ce1b33c8bb26e1f95d1a2588bf29b5c2f554cb0ae1b0668fdbbe3f"
    )
    alternate = json.dumps(
        ["other-domain:v1", "admin-uid", "action_001"],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    assert _action_id("admin-uid", "action_001") != hashlib.sha256(
        alternate.encode("utf-8")
    ).hexdigest()


def test_unicode_key_policy_is_deterministic() -> None:
    unicode_key = " գործողություն_001"
    with pytest.raises(ValidationError) as first:
        request(idempotencyKey=unicode_key)
    with pytest.raises(ValidationError) as second:
        request(idempotencyKey=unicode_key)
    assert str(first.value) == str(second.value)


@pytest.mark.parametrize(
    "department_id",
    [
        "transfer_payment",
        "account_support",
        "card_atm",
        "fraud_security",
        "loan_credit",
        "general_support",
    ],
)
def test_admin_creates_pending_staff_for_each_department(department_id: str) -> None:
    backend = FakeProvisioningBackend()
    result = AdminProvisioningService(backend).provision(
        admin(), request(departmentId=department_id)
    )
    assert result.status == "pending_setup"
    assert result.created is True
    profile = backend.profiles[result.identity.uid]
    assert profile["role"] == "staff"
    assert profile["departmentId"] == department_id
    assert profile["active"] is False
    assert backend.create_calls == 1


def test_admin_creates_pending_manager_with_null_department() -> None:
    backend = FakeProvisioningBackend()
    manager_request = request(
        email="manager@example.test",
        displayName="Synthetic Manager",
        role="manager",
        departmentId=None,
    )
    result = AdminProvisioningService(backend).provision(admin(), manager_request)
    profile = backend.profiles[result.identity.uid]
    assert profile["role"] == "manager"
    assert profile["departmentId"] is None
    assert profile["active"] is False


def test_new_identity_is_disabled_and_no_credentials_are_passed() -> None:
    backend = FakeProvisioningBackend()
    result = AdminProvisioningService(backend).provision(admin(), request())
    assert result.identity.uid in backend.identities
    assert backend.actions
    assert not any(
        field.lower() in {"password", "temporarypassword", "claims", "customclaims"}
        for field in backend.actions[next(iter(backend.actions))]
    )


def test_same_request_replay_is_idempotent_and_returns_safe_pending_result() -> None:
    backend = FakeProvisioningBackend()
    service = AdminProvisioningService(backend)
    first = service.provision(admin(), request())
    second = service.provision(admin(), request())
    assert first.identity.uid == second.identity.uid
    assert second.created is False
    assert backend.create_calls == 1


def test_same_key_with_different_request_conflicts() -> None:
    backend = FakeProvisioningBackend()
    service = AdminProvisioningService(backend)
    service.provision(admin(), request())
    with pytest.raises(ProvisioningIdempotencyConflict):
        service.provision(admin(), request(displayName="Different Staff"))


def test_same_textual_key_for_different_admins_isolated() -> None:
    backend = FakeProvisioningBackend()
    service = AdminProvisioningService(backend)
    other = AdminPrincipal(
        uid="other-admin", email="other@example.test", display_name="Other", locale="en"
    )
    first = service.provision(admin(), request())
    second = service.provision(other, request(email="other-staff@example.test"))
    assert first.identity.uid != second.identity.uid
    assert len(backend.actions) == 2


def test_unrelated_duplicate_email_is_conflict_and_not_overwritten() -> None:
    backend = FakeProvisioningBackend()
    existing = backend.create_disabled_auth(
        email="staff@example.test", display_name="Existing"
    )
    with pytest.raises(ProvisioningEmailExists):
        AdminProvisioningService(backend).provision(admin(), request())
    assert backend.identities[existing.uid].display_name == "Existing"
    assert not backend.profiles


def test_existing_profile_conflict_is_preserved() -> None:
    backend = FakeProvisioningBackend()
    identity = backend.create_disabled_auth(
        email="staff@example.test", display_name="Existing"
    )
    backend.profiles[identity.uid] = {
        "email": "staff@example.test",
        "displayName": "Existing",
        "locale": "en",
        "role": "manager",
        "departmentId": None,
        "active": False,
        "createdAt": "old",
        "updatedAt": "old",
    }
    before = deepcopy(backend.profiles[identity.uid])
    pending_request = request()
    action_id = _action_id(admin().uid, pending_request.idempotency_key)
    backend.reserve_action(
        action_id=action_id,
        actor_uid=admin().uid,
        key_fingerprint=idempotency_key_fingerprint(pending_request.idempotency_key),
        request_fingerprint=request_fingerprint(pending_request),
    )
    backend.record_target(action_id=action_id, target_uid=identity.uid)
    with pytest.raises(ProvisioningProfileConflict):
        AdminProvisioningService(backend).provision(admin(), pending_request)
    assert backend.profiles[identity.uid] == before


def test_profile_failure_leaves_action_retryable_without_second_auth_identity() -> None:
    backend = FakeProvisioningBackend()
    backend.fail_complete_once = True
    service = AdminProvisioningService(backend)
    with pytest.raises(ProvisioningIncomplete):
        service.provision(admin(), request())
    assert backend.create_calls == 1
    target_uid = next(iter(backend.identities))
    assert backend.actions[next(iter(backend.actions))]["targetUid"] == target_uid
    result = service.provision(admin(), request())
    assert result.created is False
    assert backend.create_calls == 1
    assert backend.profiles[target_uid]["active"] is False


def test_auth_creation_failure_does_not_create_profile() -> None:
    backend = FakeProvisioningBackend()
    backend.fail_create = True
    with pytest.raises(ProvisioningIncomplete):
        AdminProvisioningService(backend).provision(admin(), request())
    assert not backend.identities
    assert not backend.profiles


def fake_loader(*_args: Any, **_kwargs: Any):
    class FakeClassifier:
        model_version = "v1"

    return FakeClassifier()


@pytest.fixture
def api_client() -> TestClient:
    backend = FakeProvisioningBackend()
    settings = Settings(model_path=Settings.default().model_path)
    with TestClient(
        create_app(
            settings=settings,
            model_loader=fake_loader,
            admin_provisioning_backend=backend,
        )
    ) as client:
        client.app.state.test_backend = backend
        yield client


def admin_payload() -> dict[str, Any]:
    return {
        "email": "staff@example.test",
        "displayName": "Synthetic Staff",
        "locale": "en",
        "role": "staff",
        "departmentId": "card_atm",
        "idempotencyKey": "action_001",
    }


def test_route_returns_safe_pending_response_and_replay_status(api_client: TestClient) -> None:
    first = api_client.post(
        "/admin/users", headers={"Authorization": "Bearer admin-token"}, json=admin_payload()
    )
    assert first.status_code == 201
    assert first.json()["status"] == "pending_setup"
    assert first.json()["active"] is False
    assert first.json()["setupRequired"] is True
    assert "password" not in first.text.lower()
    second = api_client.post(
        "/admin/users", headers={"Authorization": "Bearer admin-token"}, json=admin_payload()
    )
    assert second.status_code == 200
    assert second.json() == first.json()


@pytest.mark.parametrize(
    "headers, expected_status, expected_code",
    [
        ({}, 401, "authentication_required"),
        ({"Authorization": "Bearer invalid"}, 401, "authentication_required"),
    ],
)
def test_route_maps_authentication_failures(
    api_client: TestClient,
    headers: dict[str, str],
    expected_status: int,
    expected_code: str,
) -> None:
    response = api_client.post("/admin/users", headers=headers, json=admin_payload())
    assert response.status_code == expected_status
    assert response.json()["error"]["code"] == expected_code


@pytest.mark.parametrize("role", ["customer", "admin", "unknown"])
def test_route_rejects_non_provisionable_roles(api_client: TestClient, role: str) -> None:
    response = api_client.post(
        "/admin/users",
        headers={"Authorization": "Bearer admin-token"},
        json={**admin_payload(), "role": role},
    )
    assert response.status_code == 422


def test_route_rejects_sensitive_and_unknown_fields(api_client: TestClient) -> None:
    response = api_client.post(
        "/admin/users",
        headers={"Authorization": "Bearer admin-token"},
        json={**admin_payload(), "password": "never-accepted"},
    )
    assert response.status_code == 422
    assert "never-accepted" not in response.text


@pytest.mark.parametrize("role", ["customer", "staff", "manager"])
def test_route_requires_active_admin_profile(
    api_client: TestClient, role: str
) -> None:
    backend: FakeProvisioningBackend = api_client.app.state.test_backend
    backend.role = role
    response = api_client.post(
        "/admin/users", headers={"Authorization": "Bearer admin-token"}, json=admin_payload()
    )
    assert response.status_code == 403
    assert "role" not in response.text.lower()
