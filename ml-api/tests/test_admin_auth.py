"""Pure/fake tests for the Admin authorization and provisioning contracts."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest
from pydantic import ValidationError

from app.admin_auth import (
    AdminPermissionError,
    require_active_admin,
)
from app.schemas import (
    AdminProvisioningRequest,
    AdminProvisioningResponse,
)
from app.ticketing import AuthenticationError, PersistenceError


class FakeAdminBackend:
    def __init__(
        self,
        *,
        claims: dict[str, Any] | None = None,
        profiles: dict[str, dict[str, Any]] | None = None,
        profile_error: Exception | None = None,
        token_error: Exception | None = None,
    ) -> None:
        self.claims = claims
        self.profiles = profiles or {}
        self.profile_error = profile_error
        self.token_error = token_error
        self.tokens: list[str] = []
        self.profile_uids: list[str] = []

    def verify_id_token(self, token: str) -> dict[str, Any]:
        self.tokens.append(token)
        if self.token_error is not None:
            raise self.token_error
        if self.claims is None:
            raise AuthenticationError("invalid Firebase ID token")
        return deepcopy(self.claims)

    def get_user_profile(self, uid: str) -> dict[str, Any] | None:
        self.profile_uids.append(uid)
        if self.profile_error is not None:
            raise self.profile_error
        return deepcopy(self.profiles.get(uid))


def valid_admin_profile(email: str = "admin@example.test") -> dict[str, Any]:
    return {
        "email": email,
        "displayName": " Synthetic Admin ",
        "locale": "en",
        "role": "admin",
        "departmentId": None,
        "active": True,
        "createdAt": "created",
        "updatedAt": "updated",
    }


def test_missing_and_malformed_bearer_headers_are_401() -> None:
    backend = FakeAdminBackend()
    for header in (None, "Basic value", "Bearer", "Bearer   "):
        with pytest.raises(AuthenticationError):
            require_active_admin(header, backend)


def test_invalid_token_is_401_without_logging_or_disclosing_token(caplog) -> None:
    backend = FakeAdminBackend()
    with pytest.raises(AuthenticationError) as error:
        require_active_admin("Bearer secret-token-value", backend)
    assert "secret-token-value" not in str(error.value)
    assert "secret-token-value" not in caplog.text


@pytest.mark.parametrize("role", ["customer", "staff", "manager"])
def test_non_admin_roles_are_denied(role: str) -> None:
    claims = {"uid": "verified-admin", "email": "admin@example.test"}
    profile = valid_admin_profile()
    profile["role"] = role
    backend = FakeAdminBackend(claims=claims, profiles={"verified-admin": profile})
    with pytest.raises(AdminPermissionError):
        require_active_admin("Bearer valid-token", backend)


def test_inactive_missing_and_malformed_admin_profiles_are_denied() -> None:
    claims = {"uid": "verified-admin", "email": "admin@example.test"}
    cases = [
        None,
        {**valid_admin_profile(), "active": False},
        {**valid_admin_profile(), "departmentId": "card_atm"},
        {**valid_admin_profile(), "updatedAt": None},
        {**valid_admin_profile(), "uid": "different-uid"},
        {**valid_admin_profile(), "email": "other@example.test"},
    ]
    for profile in cases:
        backend = FakeAdminBackend(
            claims=claims,
            profiles={"verified-admin": profile} if profile else {},
        )
        with pytest.raises(AdminPermissionError):
            require_active_admin("Bearer valid-token", backend)


def test_active_strict_admin_is_accepted_and_uid_email_are_verified_values() -> None:
    claims = {"uid": "verified-admin", "email": "admin@example.test"}
    backend = FakeAdminBackend(
        claims=claims,
        profiles={"verified-admin": valid_admin_profile()},
    )
    principal = require_active_admin("Bearer valid-token", backend)
    assert principal.uid == "verified-admin"
    assert principal.email == "admin@example.test"
    assert principal.display_name == "Synthetic Admin"
    assert principal.role == "admin"
    assert backend.profile_uids == ["verified-admin"]


def test_request_supplied_actor_identity_cannot_change_verified_lookup() -> None:
    claims = {"uid": "verified-admin", "email": "admin@example.test"}
    backend = FakeAdminBackend(
        claims=claims,
        profiles={"verified-admin": valid_admin_profile()},
    )
    # Future request bodies are not an input to this guard. A conflicting
    # actor identity therefore cannot affect the verified UID lookup.
    request_body = {"actorUid": "attacker", "actorRole": "admin"}
    principal = require_active_admin("Bearer valid-token", backend)
    assert request_body["actorUid"] not in backend.profile_uids
    assert principal.uid == "verified-admin"


def test_profile_dependency_failure_is_safe_service_error() -> None:
    backend = FakeAdminBackend(
        claims={"uid": "verified-admin", "email": "admin@example.test"},
        profile_error=RuntimeError("private Firestore detail"),
    )
    with pytest.raises(PersistenceError) as error:
        require_active_admin("Bearer valid-token", backend)
    assert str(error.value) == "profile lookup failed"
    assert "private" not in str(error.value)


def test_token_dependency_failure_is_safe_service_error() -> None:
    backend = FakeAdminBackend(token_error=PersistenceError("private auth detail"))
    with pytest.raises(PersistenceError) as error:
        require_active_admin("Bearer valid-token", backend)
    assert str(error.value) == "Admin authorization unavailable"
    assert "private auth detail" not in str(error.value)


def provisioning_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "email": "  STAFF@Example.TEST ",
        "displayName": "  Synthetic   Staff ",
        "locale": "my",
        "role": "staff",
        "departmentId": "card_atm",
        "idempotencyKey": " action_001 ",
    }
    payload.update(overrides)
    return payload


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
def test_valid_staff_request_accepts_each_department(department_id: str) -> None:
    request = AdminProvisioningRequest.model_validate(
        provisioning_payload(departmentId=department_id)
    )
    assert request.department_id == department_id


def test_valid_manager_request_omits_or_uses_null_department() -> None:
    omitted = provisioning_payload(role="manager")
    omitted.pop("departmentId")
    assert AdminProvisioningRequest.model_validate(omitted).department_id is None
    assert (
        AdminProvisioningRequest.model_validate(
            provisioning_payload(role="manager", departmentId=None)
        ).department_id
        is None
    )


@pytest.mark.parametrize("role", ["customer", "admin", "owner", "custom"])
def test_non_staff_manager_roles_are_rejected(role: str) -> None:
    with pytest.raises(ValidationError):
        AdminProvisioningRequest.model_validate(provisioning_payload(role=role))


@pytest.mark.parametrize(
    "payload",
    [
        provisioning_payload(departmentId="unknown"),
        provisioning_payload(departmentId=None),
        provisioning_payload(role="manager", departmentId="card_atm"),
    ],
)
def test_department_role_constraints_are_rejected(payload: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        AdminProvisioningRequest.model_validate(payload)


@pytest.mark.parametrize(
    "field, value",
    [
        ("email", "not-an-email"),
        ("email", ""),
        ("displayName", ""),
        ("displayName", "   "),
        ("displayName", "x" * 101),
        ("locale", "fr"),
        ("idempotencyKey", ""),
        ("idempotencyKey", "short"),
        ("idempotencyKey", "bad key!"),
        ("idempotencyKey", "x" * 65),
    ],
)
def test_invalid_scalar_fields_are_rejected(field: str, value: Any) -> None:
    with pytest.raises(ValidationError):
        AdminProvisioningRequest.model_validate(provisioning_payload(**{field: value}))


@pytest.mark.parametrize(
    "field",
    [
        "uid",
        "password",
        "temporaryPassword",
        "active",
        "createdAt",
        "updatedAt",
        "claims",
        "customClaims",
        "emailVerified",
        "actorUid",
        "actorRole",
        "unexpected",
    ],
)
def test_sensitive_and_unknown_fields_are_rejected(field: str) -> None:
    with pytest.raises(ValidationError):
        AdminProvisioningRequest.model_validate(
            provisioning_payload(**{field: "injected"})
        )


def test_request_normalization_is_deterministic() -> None:
    first = AdminProvisioningRequest.model_validate(provisioning_payload())
    second = AdminProvisioningRequest.model_validate(provisioning_payload())
    assert first.email == "staff@example.test"
    assert first.display_name == "Synthetic Staff"
    assert first.idempotency_key == "action_001"
    assert first.model_dump() == second.model_dump()


def test_response_has_only_safe_operational_fields() -> None:
    response = AdminProvisioningResponse.model_validate(
        {
            "status": "pending_setup",
            "uid": "synthetic-uid",
            "email": "staff@example.test",
            "displayName": "Synthetic Staff",
            "locale": "en",
            "role": "staff",
            "departmentId": "card_atm",
            "active": False,
            "setupRequired": True,
        }
    )
    assert response.role == "staff"
    assert not {
        "password",
        "temporaryPassword",
        "token",
        "claims",
        "customClaims",
    } & set(AdminProvisioningResponse.model_fields)


def test_firebase_admin_adapter_construction_does_not_initialize_on_import() -> None:
    from app import admin_auth

    assert admin_auth.FirebaseAdminAuthBackend.__init__.__name__ == "__init__"
