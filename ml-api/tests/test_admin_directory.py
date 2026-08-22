from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
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
        "createdAt": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "updatedAt": datetime(2026, 1, 2, tzinfo=timezone.utc),
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
        self.list_calls = 0
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
        self.list_calls += 1
        self.limit = limit
        if self.fail:
            raise PersistenceError("unavailable")
        return [(uid, deepcopy(value)) for uid, value in self.profiles.items()]


def client(backend: FakeDirectoryBackend) -> TestClient:
    return TestClient(create_app(model_loader=lambda *_args, **_kwargs: object(), admin_directory_backend=backend))


def test_directory_returns_all_roles_as_safe_rows_and_bounded_page() -> None:
    backend = FakeDirectoryBackend()
    response = client(backend).get("/admin/users?pageSize=2", headers={"Authorization": "Bearer admin-token"})
    assert response.status_code == 200
    body = response.json()
    assert [row["role"] for row in body["rows"]] == ["admin", "customer"]
    assert all(set(row) == {"email", "displayName", "locale", "role", "departmentId", "active", "setupStatus"} for row in body["rows"])
    assert backend.limit == 200


def test_all_role_rows_preserve_role_specific_department_contract() -> None:
    body = client(FakeDirectoryBackend()).get("/admin/users?pageSize=50", headers={"Authorization": "Bearer admin-token"}).json()
    rows = {row["role"]: row for row in body["rows"]}
    assert rows["customer"]["departmentId"] is None
    assert rows["staff"]["departmentId"] == "card_atm"
    assert rows["manager"]["departmentId"] is None
    assert rows["admin"]["departmentId"] is None
    assert all(row["setupStatus"] == ("active" if row["active"] else "pending_setup") for row in body["rows"])


@pytest.mark.parametrize("query", ["departmentId=unknown", "role=customer&departmentId=card_atm", "role=admin&departmentId=card_atm", "unknown=value", "pageSize=0", "pageSize=51"])
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


def test_unchanged_pagination_has_no_duplicates_or_omissions() -> None:
    backend = FakeDirectoryBackend()
    app_client = client(backend)
    cursor = None
    emails: list[str] = []
    for _ in range(5):
        query = "pageSize=2" + (f"&cursor={cursor}" if cursor else "")
        body = app_client.get(f"/admin/users?{query}", headers={"Authorization": "Bearer admin-token"}).json()
        emails.extend(row["email"] for row in body["rows"])
        cursor = body["nextCursor"]
        if not body["hasMore"]:
            break
    assert emails == sorted(emails)
    assert len(emails) == len(set(emails)) == 5
    assert cursor is None


@pytest.mark.parametrize("role", ["customer", "staff", "manager", "admin"])
def test_each_role_filter_returns_only_that_role(role: str) -> None:
    response = client(FakeDirectoryBackend()).get(f"/admin/users?role={role}", headers={"Authorization": "Bearer admin-token"})
    assert response.status_code == 200
    assert {row["role"] for row in response.json()["rows"]} == {role}


def test_cursor_is_bound_to_effective_filters() -> None:
    backend = FakeDirectoryBackend()
    first = client(backend).get("/admin/users?pageSize=1", headers={"Authorization": "Bearer admin-token"})
    cursor = first.json()["nextCursor"]
    assert cursor
    mismatched = client(backend).get(f"/admin/users?role=staff&cursor={cursor}", headers={"Authorization": "Bearer admin-token"})
    assert mismatched.status_code == 422


@pytest.mark.parametrize("headers,status", [(None, 401), ({"Authorization": "Bearer bad"}, 401)])
def test_directory_requires_valid_admin_token(headers: dict[str, str] | None, status: int) -> None:
    response = client(FakeDirectoryBackend()).get("/admin/users", headers=headers)
    assert response.status_code == status


@pytest.mark.parametrize("mode", ["mismatched_email", "missing_profile", "malformed_profile"])
def test_directory_denies_invalid_admin_profile_without_scanning(mode: str) -> None:
    backend = FakeDirectoryBackend()
    if mode == "mismatched_email":
        backend.verify_id_token = lambda _token: {"uid": "admin-actor", "email": "different@example.test"}  # type: ignore[method-assign]
    elif mode == "missing_profile":
        backend.get_user_profile = lambda _uid: None  # type: ignore[method-assign]
    else:
        backend.get_user_profile = lambda _uid: {"role": "admin"}  # type: ignore[method-assign]
    response = client(backend).get("/admin/users", headers={"Authorization": "Bearer admin-token"})
    assert response.status_code == 403
    assert backend.list_calls == 0


@pytest.mark.parametrize("role", ["customer", "staff", "manager", "admin"])
def test_directory_requires_active_strict_admin_before_profile_scan(role: str) -> None:
    backend = FakeDirectoryBackend()
    backend.get_user_profile = lambda _uid: profile("admin@example.test", role, None, role == "admin")  # type: ignore[method-assign]
    response = client(backend).get("/admin/users", headers={"Authorization": "Bearer admin-token"})
    assert response.status_code == (200 if role == "admin" else 403)
    assert backend.list_calls == (1 if role == "admin" else 0)


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


@pytest.mark.parametrize(
    "field,value",
    [
        ("departmentId", "card_atm"),
        ("active", 1),
        ("createdAt", None),
        ("updatedAt", None),
        ("createdAt", datetime(2026, 1, 1)),
        ("updatedAt", "malformed-timestamp"),
        ("email", " Manager@EXAMPLE.TEST "),
        ("displayName", "   "),
        ("locale", "fr"),
        ("role", "Staff"),
    ],
)
def test_role_profile_shape_and_required_fields_fail_closed(field: str, value: Any) -> None:
    backend = FakeDirectoryBackend()
    backend.profiles["manager-1"][field] = value
    response = client(backend).get("/admin/users", headers={"Authorization": "Bearer admin-token"})
    assert response.status_code == 503
    assert "manager@example.test" not in response.text


def test_cursor_is_bounded_versioned_encoding_and_tampering_is_rejected() -> None:
    encoded = encode_directory_cursor(MAX_DIRECTORY_SCAN, "0" * 64)
    assert decode_directory_cursor(encoded).offset == MAX_DIRECTORY_SCAN
    assert len(encoded) <= 128
    for cursor in ["not-a-cursor", encode_directory_cursor(0, "0" * 64)[:-1], "eyJ2IjoyLCJvZmZzZXQiOjB9"]:
        response = client(FakeDirectoryBackend()).get(
            f"/admin/users?cursor={cursor}",
            headers={"Authorization": "Bearer admin-token"},
        )
        assert response.status_code == 422
    with pytest.raises(ValueError):
        encode_directory_cursor(MAX_DIRECTORY_SCAN + 1, "0" * 64)


def test_cursor_filter_binding_has_stable_vector() -> None:
    from app.admin_directory import _filter_fingerprint
    from app.schemas import AdminDirectoryRequest

    assert _filter_fingerprint(AdminDirectoryRequest()) == "c6a84ae2a12f3481284c74849e3806462c4347928cf4776b3ed5e92e6aeb7a5a"


def test_duplicate_normalized_email_fails_closed() -> None:
    backend = FakeDirectoryBackend()
    backend.profiles["admin-1"]["email"] = "staff@example.test"
    response = client(backend).get("/admin/users", headers={"Authorization": "Bearer admin-token"})
    assert response.status_code == 503
    assert "staff@example.test" not in response.text
