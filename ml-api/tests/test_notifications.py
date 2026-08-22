"""Pure and fake-backed tests for the R0.2B notification foundation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.notifications import (
    FirebaseAdminNotificationBackend,
    InMemoryNotificationBackend,
    NotificationConflictError,
    NotificationCreateRequest,
    NotificationNotFoundError,
    NotificationService,
    NotificationValidationError,
    decode_cursor,
    notification_reference,
)

NOW = datetime(2026, 8, 22, 10, 0, tzinfo=timezone.utc)


def request(
    *, recipient_uid: str = "cust-1", recipient_role: str = "customer", source: str = "ticket:1:reply", severity: str = "info"
) -> NotificationCreateRequest:
    return NotificationCreateRequest(
        recipient_uid=recipient_uid,
        recipient_role=recipient_role,
        type="staff_reply",
        severity=severity,
        category="response",
        title_key="notifications.staff_reply.title",
        body_key="notifications.staff_reply.body",
        source_key=source,
        related_ticket_ref="ticket_public_1",
        params={"ticketRef": "ticket_public_1"},
        navigation_target="customer_ticket",
    )


class FakeAuthBackend:
    def __init__(self) -> None:
        self.tokens = {
            "customer-token": "customer-1",
            "staff-token": "staff-1",
            "manager-token": "manager-1",
            "admin-token": "admin-1",
            "other-token": "customer-2",
            "inactive-token": "inactive-1",
            "malformed-token": "malformed-1",
            "conflicting-token": "conflicting-1",
        }
        def profile(role: str, *, department: str | None = None) -> dict[str, Any]:
            return {
                "email": f"{role}@example.test",
                "displayName": role.title(),
                "locale": "en",
                "role": role,
                "departmentId": department,
                "active": True,
                "createdAt": "created",
                "updatedAt": "updated",
            }
        self.profiles = {
            "customer-1": profile("customer"),
            "customer-2": profile("customer"),
            "staff-1": profile("staff", department="transfer_payment"),
            "manager-1": profile("manager"),
            "admin-1": profile("admin"),
            "inactive-1": {**profile("customer"), "active": False},
            "malformed-1": {"role": "customer", "active": True},
            "conflicting-1": {**profile("customer"), "uid": "different-uid"},
        }

    def verify_id_token(self, token: str) -> str:
        if token not in self.tokens:
            raise RuntimeError("invalid token")
        return self.tokens[token]

    def get_user_profile(self, uid: str) -> dict[str, Any] | None:
        return self.profiles.get(uid)


def service(backend: InMemoryNotificationBackend | None = None) -> NotificationService:
    return NotificationService(backend or InMemoryNotificationBackend(), clock=lambda: NOW)


def test_hash_vector_is_stable_and_opaque() -> None:
    value = notification_reference(request())
    assert value == "e70d9a22f432d3521a984249a458add72ef83b101b39611abdf4aa895d3e1c84"
    assert len(value) == 64
    assert value == value.lower()
    assert "cust-1" not in value
    assert "ticket:1:reply" not in value
    assert value == notification_reference(
        request(recipient_uid=" cust-1 ", source=" ticket:1:reply ")
    )


def test_creation_is_idempotent_and_conflicts_are_safe() -> None:
    backend = InMemoryNotificationBackend()
    notification_service = service(backend)
    first = notification_service.create(request())
    replay = notification_service.create(request())
    assert replay == first
    with pytest.raises(NotificationConflictError):
        notification_service.create(request(severity="urgent"))


def test_invalid_contract_values_are_rejected() -> None:
    with pytest.raises(NotificationValidationError):
        service().create(request(recipient_role="manager"))
    with pytest.raises(NotificationValidationError):
        service().create(
            NotificationCreateRequest(
                **{**request().__dict__, "title_key": "notifications.staff_reply.title", "params": {"message": "private narrative"}}
            )
        )
    with pytest.raises(NotificationValidationError):
        service().create(
            NotificationCreateRequest(
                **{**request().__dict__, "navigation_target": "https://example.test"}
            )
        )


def test_retention_cursor_ordering_unread_and_safe_expiry() -> None:
    backend = InMemoryNotificationBackend()
    notification_service = service(backend)
    notification_service.create(request(source="ticket:1:first"))
    notification_service.create(request(source="ticket:1:second"))
    expired = notification_service.create(request(source="ticket:1:expired"))
    backend.records[expired.notification_ref] = expired.__class__(**{**expired.__dict__, "expires_at": NOW - timedelta(seconds=1)})
    page = notification_service.list("cust-1", unread_only=True, cursor=None, page_size=1)
    assert len(page.records) == 1
    assert page.next_cursor
    assert decode_cursor(page.next_cursor, unread_only=True) is not None
    with pytest.raises(NotificationValidationError):
        decode_cursor(page.next_cursor, unread_only=False)
    next_page = notification_service.list("cust-1", unread_only=True, cursor=page.next_cursor, page_size=50)
    assert len(next_page.records) == 1
    assert notification_service.unread_count("cust-1") == 2


def test_identical_timestamp_pages_use_the_opaque_reference_boundary() -> None:
    backend = InMemoryNotificationBackend()
    notification_service = service(backend)
    for index in range(4):
        notification_service.create(request(source=f"ticket:identical:{index}"))

    def collect(*, unread_only: bool, page_size: int) -> tuple[list[str], list[str | None]]:
        cursor = None
        refs: list[str] = []
        cursors: list[str | None] = []
        while True:
            page = notification_service.list(
                "cust-1", unread_only=unread_only, cursor=cursor, page_size=page_size
            )
            refs.extend(record.notification_ref for record in page.records)
            cursors.append(page.next_cursor)
            if page.next_cursor is None:
                return refs, cursors
            cursor = page.next_cursor

    for page_size in (1, 2):
        first, first_cursors = collect(unread_only=False, page_size=page_size)
        second, _ = collect(unread_only=False, page_size=page_size)
        assert first == second
        assert len(first) == len(set(first)) == 4
        assert first_cursors[-1] is None

    marked = notification_service.mark_read("cust-1", first[0])
    assert marked.read_at == NOW
    unread, unread_cursors = collect(unread_only=True, page_size=1)
    assert unread == first[1:]
    assert len(unread) == len(set(unread)) == 3
    assert unread_cursors[-1] is None


def test_firestore_query_orders_and_starts_after_document_reference() -> None:
    class Query:
        def __init__(self) -> None:
            self.orders: list[tuple[str, str]] = []
            self.cursor = None

        def where(self, **_kwargs: Any) -> Query:
            return self

        def order_by(self, field: str, *, direction: str) -> Query:
            self.orders.append((field, direction))
            return self

        def start_after(self, cursor: tuple[datetime, datetime, str]) -> Query:
            self.cursor = cursor
            return self

    class Database:
        def __init__(self) -> None:
            self.query = Query()

        def collection(self, _name: str) -> Query:
            return self.query

    database = Database()
    firebase_backend = FirebaseAdminNotificationBackend(db=database, server_timestamp="server")
    cursor = (NOW + timedelta(days=90), NOW, "a" * 64)
    query = firebase_backend._query(
        "cust-1", unread_only=True, now=NOW, cursor=cursor
    )
    assert query.orders == [
        ("expiresAt", "DESCENDING"),
        ("createdAt", "DESCENDING"),
        ("__name__", "DESCENDING"),
    ]
    assert query.cursor == cursor


def test_expiry_boundary_and_naive_clock_are_safe() -> None:
    backend = InMemoryNotificationBackend()
    notification_service = service(backend)
    record = notification_service.create(request())
    backend.records[record.notification_ref] = record.__class__(
        **{**record.__dict__, "expires_at": NOW}
    )
    assert notification_service.list("cust-1", unread_only=False, cursor=None, page_size=50).records == []
    assert notification_service.unread_count("cust-1") == 0
    with pytest.raises(NotificationValidationError):
        NotificationService(backend, clock=lambda: NOW.replace(tzinfo=None)).list(
            "cust-1", unread_only=False, cursor=None, page_size=50
        )


def test_malformed_cursor_version_and_reference_are_rejected() -> None:
    import base64
    import json

    malformed = base64.urlsafe_b64encode(
        json.dumps({"v": 2, "createdAt": NOW.isoformat(), "ref": "0" * 64}).encode()
    ).decode().rstrip("=")
    with pytest.raises(NotificationValidationError):
        service().list("cust-1", unread_only=False, cursor=malformed, page_size=1)
    with pytest.raises(NotificationValidationError):
        service().mark_read("cust-1", "not-a-reference")


def test_mark_read_is_idempotent_and_read_all_is_recipient_scoped() -> None:
    backend = InMemoryNotificationBackend()
    notification_service = service(backend)
    own = notification_service.create(request())
    other = service(backend).create(request(recipient_uid="customer-2", source="other"))
    read = notification_service.mark_read("cust-1", own.notification_ref)
    assert read.read_at == NOW
    assert notification_service.mark_read("cust-1", own.notification_ref) == read
    with pytest.raises(NotificationNotFoundError):
        notification_service.mark_read("cust-1", other.notification_ref)
    assert notification_service.mark_all_read("cust-1") == 0
    assert backend.records[other.notification_ref].read_at is None


def test_read_all_is_explicitly_bounded_to_one_safe_batch() -> None:
    backend = InMemoryNotificationBackend()
    notification_service = service(backend)
    for index in range(151):
        notification_service.create(request(source=f"ticket:batch:{index}"))
    assert notification_service.mark_all_read("cust-1") == 150
    assert notification_service.unread_count("cust-1") == 1


def _client(notification_backend: InMemoryNotificationBackend) -> TestClient:
    auth = FakeAuthBackend()
    app = create_app(
        model_loader=lambda *_args, **_kwargs: object(),
        ticket_backend=auth,
        notification_backend=notification_backend,
    )
    return TestClient(app)


def test_all_active_roles_can_read_only_their_own_notifications() -> None:
    backend = InMemoryNotificationBackend()
    notification_service = service(backend)
    notification_service.create(request())
    for role, uid, token, kind in [
        ("staff", "staff-1", "staff-token", "ticket_assigned"),
        ("manager", "manager-1", "manager-token", "manual_review_required"),
        ("admin", "admin-1", "admin-token", "system_operational_alert"),
    ]:
        kwargs = {**request(recipient_uid=uid, recipient_role=role, source=f"{role}:1").__dict__, "type": kind,
                  "title_key": f"notifications.{kind}.title", "body_key": f"notifications.{kind}.body",
                  "category": "system" if role == "admin" else "assignment", "navigation_target": "notifications",
                  "related_ticket_ref": None, "params": {}}
        notification_service.create(NotificationCreateRequest(**kwargs))
        response = _client(backend).get("/notifications", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert all("recipientUid" not in item for item in response.json()["notifications"])


def test_api_auth_read_mark_and_no_creation_route() -> None:
    backend = InMemoryNotificationBackend()
    notification_service = service(backend)
    own = notification_service.create(request(recipient_uid="customer-1"))
    other = notification_service.create(request(recipient_uid="customer-2", source="other"))
    client = _client(backend)
    assert client.get("/notifications").status_code == 401
    assert client.get("/notifications", headers={"Authorization": "Bearer inactive-token"}).status_code == 403
    assert client.get("/notifications", headers={"Authorization": "Bearer customer-token"}).status_code == 200
    assert client.post(f"/notifications/{other.notification_ref}/read", headers={"Authorization": "Bearer customer-token"}).status_code == 404
    read = client.post(f"/notifications/{own.notification_ref}/read", headers={"Authorization": "Bearer customer-token"})
    assert read.status_code == 200
    assert read.json()["unread"] is False
    assert client.post("/notifications/read-all", headers={"Authorization": "Bearer customer-token"}).status_code == 200
    assert not any(route.path == "/notifications" and "POST" in route.methods for route in client.app.routes)


def test_malformed_and_conflicting_profiles_are_denied() -> None:
    client = _client(InMemoryNotificationBackend())
    for token in ("malformed-token", "conflicting-token"):
        response = client.get("/notifications", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 403


def test_api_rejects_unbounded_page_size_and_returns_safe_count() -> None:
    client = _client(InMemoryNotificationBackend())
    response = client.get("/notifications?pageSize=51", headers={"Authorization": "Bearer customer-token"})
    assert response.status_code == 422
    count = client.get("/notifications/unread-count", headers={"Authorization": "Bearer customer-token"})
    assert count.status_code == 200
    assert count.json() == {"unreadCount": 0}
