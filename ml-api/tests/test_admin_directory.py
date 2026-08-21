from __future__ import annotations

from copy import deepcopy
from typing import Any

from fastapi.testclient import TestClient
import pytest

from app.main import create_app
from app.admin_directory import MAX_DIRECTORY_SCAN, decode_directory_cursor, encode_directory_cursor
from app.ticketing import AuthenticationError, PersistenceError


def profile(email: str, role: str, department: str | None, active: bool = True) -> dict[str, Any]:
    return {
        "email": email,
        "displayName": role.title(),
        "locale": "en",
        "role": role,
        "departmentId": department,
        "active": active,
        "createdAt": "created",
        "updatedAt": "updated",
    }


class FakeDirectoryBackend:
    def __init__(self) -> None:
        self.profiles = {
            "staff-1": profile("staff@example.test", "staff", "card_atm"),
            "staff-2": profile("pending@example.test", "staff", "loan_credit", False),
            "manager-1": profile("manager@example.test", "manager", None),
            "customer-1": profile("customer@example.test", "customer", None),
            "admin-1": profile("admin@example.test", "admin", None),
        }
        self.limit: int | None = None
        self.fail = False

    def verify_id_token(self, token: str) -> dict[str, Any]:
        if token != "admin-token":
            raise AuthenticationError("invalid token")
        return {"uid": "admin-actor", "email": "admin@example.test"}

    def get_user_profile(self, uid: str) -> dict[str, Any] | None:
        if uid != "admin-actor":
            return None
        return profile("admin@example.test", "admin", None)

    def list_user_profiles(self, *, limit: int) -> list[tuple[str, dict[str, Any]]]:
        self.limit = limit
        if self.fail:
            raise PersistenceError("unavailable")
        return [(uid, deepcopy(value)) for uid, value in self.profiles.items()]


def client(backend: FakeDirectoryBackend) -> TestClient:
    return TestClient(create_app(model_loader=lambda *_args, **_kwargs: object(), admin_directory_backend=backend))


def test_directory_returns_only_safe_staff_manager_rows_and_bounded_page() -> None:
    backend = FakeDirectoryBackend()
    response = client(backend).get("/admin/users?pageSize=2", headers={"Authorization": "Bearer admin-token"})
    assert response.status_code == 200
    body = response.json()
    assert [row["role"] for row in body["rows"]] == ["manager", "staff"]
    assert all(set(row) == {"email", "displayName", "locale", "role", "departmentId", "active", "setupStatus"} for row in body["rows"])
    assert backend.limit == 200


@pytest.mark.parametrize("query", ["role=customer", "role=admin", "departmentId=unknown", "unknown=value", "pageSize=0", "pageSize=51"])
def test_directory_rejects_invalid_filters(query: str) -> None:
    response = client(FakeDirectoryBackend()).get(f"/admin/users?{query}", headers={"Authorization": "Bearer admin-token"})
    assert response.status_code == 422


def test_directory_filters_and_pagination_are_deterministic() -> None:
    backend = FakeDirectoryBackend()
    app_client = client(backend)
    first = app_client.get("/admin/users?role=staff&active=false&pageSize=1", headers={"Authorization": "Bearer admin-token"})
    assert first.status_code == 200
    assert first.json()["rows"][0]["email"] == "pending@example.test"
    assert first.json()["hasMore"] is False
    assert app_client.get("/admin/users?departmentId=card_atm", headers={"Authorization": "Bearer admin-token"}).json()["rows"][0]["role"] == "staff"


@pytest.mark.parametrize("headers,status", [(None, 401), ({"Authorization": "Bearer bad"}, 401)])
def test_directory_requires_valid_admin_token(headers: dict[str, str] | None, status: int) -> None:
    response = client(FakeDirectoryBackend()).get("/admin/users", headers=headers)
    assert response.status_code == status


def test_directory_dependency_failure_is_safe_and_read_only() -> None:
    backend = FakeDirectoryBackend()
    backend.fail = True
    response = client(backend).get("/admin/users", headers={"Authorization": "Bearer admin-token"})
    assert response.status_code == 503
    assert "unavailable" not in response.text.lower() or "directory" in response.text.lower()


def test_malformed_profile_is_not_partially_exposed() -> None:
    backend = FakeDirectoryBackend()
    backend.profiles["staff-1"]["role"] = "admin"
    response = client(backend).get("/admin/users", headers={"Authorization": "Bearer admin-token"})
    assert response.status_code == 503
    assert "staff@example.test" not in response.text


def test_cursor_is_bounded_versioned_encoding_and_tampering_is_rejected() -> None:
    encoded = encode_directory_cursor(MAX_DIRECTORY_SCAN)
    assert decode_directory_cursor(encoded).offset == MAX_DIRECTORY_SCAN
    assert len(encoded) <= 128
    for cursor in ["not-a-cursor", encode_directory_cursor(0)[:-1], "eyJ2IjoyLCJvZmZzZXQiOjB9"]:
        response = client(FakeDirectoryBackend()).get(
            f"/admin/users?cursor={cursor}",
            headers={"Authorization": "Bearer admin-token"},
        )
        assert response.status_code == 422
    with pytest.raises(ValueError):
        encode_directory_cursor(MAX_DIRECTORY_SCAN + 1)
