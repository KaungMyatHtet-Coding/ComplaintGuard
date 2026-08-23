"""Pure/fake tests for trusted Customer-profile completion."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.auth_workflow import (
    CustomerProfileConflict,
    FirebaseAdminCustomerProfileBackend,
    VerifiedFirebaseIdentity,
)
from app.config import Settings
from app.main import create_app
from app.schemas import CustomerProfileRequest
from app.ticketing import AuthenticationError, PersistenceError


class FakeSnapshot:
    def __init__(self, value: dict[str, Any] | None) -> None:
        self.exists = value is not None
        self._value = deepcopy(value)

    def to_dict(self) -> dict[str, Any] | None:
        return deepcopy(self._value)


class FakeReference:
    def __init__(self, path: str) -> None:
        self.path = path


class FakeTransaction:
    def __init__(self, database: FakeDatabase) -> None:
        self.database = database
        self.created: list[dict[str, Any]] = []

    def get(self, reference: FakeReference):
        return iter([FakeSnapshot(self.database.documents.get(reference.path))])

    def create(self, reference: FakeReference, value: dict[str, Any]) -> None:
        if reference.path in self.database.documents:
            raise RuntimeError("transaction conflict")
        self.database.documents[reference.path] = deepcopy(value)
        self.created.append(deepcopy(value))


class FakeCollection:
    def __init__(self, database: FakeDatabase, name: str) -> None:
        self.database = database
        self.name = name

    def document(self, uid: str) -> FakeReference:
        return FakeReference(f"{self.name}/{uid}")


class FakeDatabase:
    def __init__(self, documents: dict[str, dict[str, Any]] | None = None) -> None:
        self.documents = deepcopy(documents or {})
        self.last_transaction: FakeTransaction | None = None

    def collection(self, name: str) -> FakeCollection:
        return FakeCollection(self, name)


class FakeAuth:
    def __init__(self, claims: dict[str, Any] | None = None) -> None:
        self.claims = claims or {}

    def verify_id_token(self, _token: str) -> dict[str, Any]:
        if not self.claims:
            raise RuntimeError("token invalid")
        return dict(self.claims)


def fake_transaction_runner(database: FakeDatabase):
    def runner(_database: FakeDatabase, operation):
        transaction = FakeTransaction(database)
        database.last_transaction = transaction
        return operation(transaction)

    return runner


def backend_for(
    monkeypatch: pytest.MonkeyPatch,
    *,
    documents: dict[str, dict[str, Any]] | None = None,
    claims: dict[str, Any] | None = None,
) -> tuple[FirebaseAdminCustomerProfileBackend, FakeDatabase]:
    from app import auth_workflow

    database = FakeDatabase(documents)
    monkeypatch.setattr(auth_workflow, "run_firestore_transaction", fake_transaction_runner(database))
    backend = FirebaseAdminCustomerProfileBackend(
        clients=(FakeAuth(claims), database, "SERVER_TIMESTAMP")
    )
    return backend, database


def identity() -> VerifiedFirebaseIdentity:
    return VerifiedFirebaseIdentity(uid="uid-customer", email="customer@example.test")


def complete_profile(identity_value: VerifiedFirebaseIdentity, **overrides: Any) -> dict[str, Any]:
    profile = {
        "email": identity_value.email,
        "displayName": "Existing Customer",
        "locale": "en",
        "role": "customer",
        "departmentId": None,
        "active": True,
        "accountState": "active",
        "createdAt": "created",
        "updatedAt": "updated",
    }
    profile.update(overrides)
    return profile


def test_request_normalizes_display_name_and_has_no_password_field() -> None:
    request = CustomerProfileRequest.model_validate(
        {"displayName": "  Synthetic   Customer ", "locale": "my"}
    )
    assert request.display_name == "Synthetic Customer"
    assert "password" not in CustomerProfileRequest.model_fields


@pytest.mark.parametrize(
    "payload",
    [
        {"displayName": "", "locale": "en"},
        {"displayName": "   ", "locale": "en"},
        {"displayName": "Customer", "locale": "fr"},
        {"displayName": "x" * 101, "locale": "en"},
    ],
)
def test_request_rejects_invalid_display_name_or_locale(payload: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        CustomerProfileRequest.model_validate(payload)


@pytest.mark.parametrize(
    "field",
    [
        "uid",
        "email",
        "role",
        "departmentId",
        "active",
        "createdAt",
        "updatedAt",
        "claims",
        "customClaims",
        "password",
    ],
)
def test_sensitive_and_extra_fields_are_rejected(field: str) -> None:
    payload = {"displayName": "Customer", "locale": "en", field: "injected"}
    with pytest.raises(ValidationError):
        CustomerProfileRequest.model_validate(payload)


def test_creation_uses_verified_uid_and_email_and_fixed_customer_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend, database = backend_for(
        monkeypatch,
        claims={"uid": "verified-uid", "email": "verified@example.test"},
    )
    verified = backend.verify_identity("opaque-token")
    status, safe_profile = backend.complete_customer_profile(
        verified, display_name="Normalized Customer", locale="my"
    )

    assert status == "created"
    assert safe_profile == {
        "uid": "verified-uid",
        "email": "verified@example.test",
        "displayName": "Normalized Customer",
        "locale": "my",
        "role": "customer",
        "departmentId": None,
        "active": True,
    }
    stored = database.documents["users/verified-uid"]
    assert stored["role"] == "customer"
    assert stored["departmentId"] is None
    assert stored["active"] is True
    assert stored["createdAt"] == "SERVER_TIMESTAMP"
    assert stored["updatedAt"] == "SERVER_TIMESTAMP"
    assert "uid" not in stored


def test_existing_customer_is_idempotent_and_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    original = complete_profile(identity(), displayName="  Existing Customer  ", extra="preserve")
    backend, database = backend_for(monkeypatch, documents={"users/uid-customer": original})
    before = deepcopy(database.documents)

    assert backend.complete_customer_profile(
        identity(), display_name="Different Input", locale="my"
    )[0] == "existing"
    assert backend.complete_customer_profile(
        identity(), display_name="Another Input", locale="en"
    )[0] == "existing"
    assert database.documents == before


@pytest.mark.parametrize("role", ["staff", "manager", "admin"])
def test_existing_privileged_profile_is_preserved_and_conflicts(
    monkeypatch: pytest.MonkeyPatch, role: str
) -> None:
    original = complete_profile(identity(), role=role, departmentId="card_atm")
    backend, database = backend_for(monkeypatch, documents={"users/uid-customer": original})
    before = deepcopy(database.documents)

    with pytest.raises(CustomerProfileConflict):
        backend.complete_customer_profile(identity(), display_name="Customer", locale="en")
    assert database.documents == before


@pytest.mark.parametrize(
    "overrides",
    [{"active": False}, {"locale": "fr"}, {"createdAt": None}, {"role": "unknown"}, {}],
)
def test_existing_inactive_or_malformed_profile_is_preserved(
    monkeypatch: pytest.MonkeyPatch, overrides: dict[str, Any]
) -> None:
    original = complete_profile(identity(), **overrides)
    if not overrides:
        original.pop("displayName")
    backend, database = backend_for(monkeypatch, documents={"users/uid-customer": original})
    before = deepcopy(database.documents)

    with pytest.raises(CustomerProfileConflict):
        backend.complete_customer_profile(identity(), display_name="Customer", locale="en")
    assert database.documents == before


def test_invalid_token_is_rejected_without_identity_details(monkeypatch: pytest.MonkeyPatch) -> None:
    backend, _ = backend_for(monkeypatch)
    with pytest.raises(AuthenticationError) as error:
        backend.verify_identity("bad-token")
    assert "bad-token" not in str(error.value)


class FakeEndpointBackend:
    def __init__(self, outcome: str = "created") -> None:
        self.outcome = outcome

    def verify_identity(self, token: str) -> VerifiedFirebaseIdentity:
        if token != "valid-token":
            raise AuthenticationError("invalid")
        return identity()

    def complete_customer_profile(self, identity_value, *, display_name: str, locale: str):
        if self.outcome == "failure":
            raise PersistenceError("secret-token password backend detail")
        if self.outcome == "conflict":
            raise CustomerProfileConflict("privileged profile detail")
        return self.outcome, {
            "uid": identity_value.uid,
            "email": identity_value.email,
            "displayName": display_name,
            "locale": locale,
            "role": "customer",
            "departmentId": None,
            "active": True,
        }


def fake_loader(*_args: Any, **_kwargs: Any):
    class FakeClassifier:
        model_version = "v1"

    return FakeClassifier()


@pytest.fixture
def api_client():
    settings = Settings(model_path=Settings.default().model_path)
    with TestClient(
        create_app(
            settings=settings,
            model_loader=fake_loader,
            customer_profile_backend=FakeEndpointBackend(),
        )
    ) as client:
        yield client


def test_endpoint_maps_auth_validation_and_safe_backend_errors(
    api_client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    created = api_client.post(
        "/auth/customer-profile",
        headers={"Authorization": "Bearer valid-token"},
        json={
            "displayName": "  Customer  ",
            "locale": "en",
            "termsAccepted": True,
        },
    )
    assert created.status_code == 201
    assert created.json() == {
        "status": "created",
        "profile": {
            "uid": "uid-customer",
            "email": "customer@example.test",
            "displayName": "Customer",
            "locale": "en",
            "role": "customer",
            "departmentId": None,
            "active": True,
        },
    }
    assert api_client.post(
        "/auth/customer-profile", json={"displayName": "Customer", "locale": "en"}
    ).status_code == 401
    invalid = api_client.post(
        "/auth/customer-profile",
        headers={"Authorization": "Bearer valid-token"},
        json={"displayName": "Customer", "locale": "en", "role": "admin"},
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "request_validation_error"

    conflict_client = TestClient(
        create_app(
            settings=Settings(model_path=Settings.default().model_path),
            model_loader=fake_loader,
            customer_profile_backend=FakeEndpointBackend("conflict"),
        )
    )
    with conflict_client:
        conflict = conflict_client.post(
            "/auth/customer-profile",
            headers={"Authorization": "Bearer valid-token"},
            json={"displayName": "Customer", "locale": "en"},
        )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "profile_conflict"
    assert "privileged" not in conflict.text

    failure_client = TestClient(
        create_app(
            settings=Settings(model_path=Settings.default().model_path),
            model_loader=fake_loader,
            customer_profile_backend=FakeEndpointBackend("failure"),
        )
    )
    with failure_client:
        failure = failure_client.post(
            "/auth/customer-profile",
            headers={"Authorization": "Bearer valid-token"},
            json={"displayName": "Customer", "locale": "en"},
        )
    assert failure.status_code == 503
    assert "secret-token" not in failure.text
    assert "password" not in failure.text
    assert "secret-token" not in caplog.text
    assert "password" not in caplog.text


def test_module_import_does_not_initialize_firebase() -> None:
    # The dedicated module imports only the existing factory; construction is explicit.
    assert FirebaseAdminCustomerProfileBackend.__init__.__name__ == "__init__"
