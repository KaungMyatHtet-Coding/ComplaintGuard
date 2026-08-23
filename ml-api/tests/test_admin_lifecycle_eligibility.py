from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.admin_directory import (
    ACCOUNT_REFERENCE_DOMAIN,
    ACCOUNT_REFERENCE_PROJECT,
    account_reference,
    canonical_account_reference_input,
)
from app.main import create_app
from app.ticketing import AuthenticationError


def profile(email: str, role: str, department: str | None, active: bool = True) -> dict[str, Any]:
    return {
        "email": email,
        "displayName": role.title(),
        "locale": "en",
        "role": role,
        "departmentId": department,
        "active": active,
        "accountState": "active" if active else ("disabled" if role != "admin" else "inactive_unverified"),
        "createdAt": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "updatedAt": datetime(2026, 1, 2, tzinfo=timezone.utc),
    }


class FakeLifecycleBackend:
    def __init__(self) -> None:
        self.profiles = {
            "admin-actor": profile("admin@example.test", "admin", None),
            "admin-other": profile("other-admin@example.test", "admin", None),
            "customer-1": profile("customer@example.test", "customer", None),
            "staff-1": profile("staff@example.test", "staff", "card_atm"),
            "staff-inactive": profile("inactive-staff@example.test", "staff", "loan_credit", False),
            "manager-1": profile("manager@example.test", "manager", None),
        }
        self.tickets: list[dict[str, Any]] = []
        self.profile_scan_calls = 0
        self.ticket_scan_calls = 0

    def verify_id_token(self, token: str) -> dict[str, Any]:
        if token != "admin-token":
            raise AuthenticationError("invalid token")
        return {"uid": "admin-actor", "email": "admin@example.test"}

    def get_user_profile(self, uid: str) -> dict[str, Any] | None:
        return deepcopy(self.profiles.get(uid))

    def list_user_profiles(self, *, limit: int) -> list[tuple[str, dict[str, Any]]]:
        self.profile_scan_calls += 1
        return [(uid, deepcopy(value)) for uid, value in self.profiles.items()][:limit]

    def list_tickets(self, *, limit: int) -> list[dict[str, Any]]:
        self.ticket_scan_calls += 1
        return deepcopy(self.tickets[:limit])


def client(backend: FakeLifecycleBackend) -> TestClient:
    return TestClient(
        create_app(
            model_loader=lambda *_args, **_kwargs: object(),
            admin_directory_backend=backend,
        )
    )


def test_account_reference_vector_is_canonical_opaque_and_project_bound() -> None:
    assert ACCOUNT_REFERENCE_DOMAIN == "complaintguard:admin-account-ref:v1"
    assert canonical_account_reference_input(
        "admin-actor", project_domain=ACCOUNT_REFERENCE_PROJECT
    ) == '{"domain":"complaintguard:admin-account-ref:v1","project":"local-emulator:demo-complaintguard","uid":"admin-actor"}'
    reference = account_reference("admin-actor")
    assert reference == "acct_v1_2a72905deb3e42deb76854ccb076e941ab47ffa256a7cceaad1f0d82b959d8c2"
    assert len(reference) == 72
    assert reference == reference.lower()
    assert "admin-actor" not in reference
    assert account_reference("admin-actor", project_domain="other-project") != reference
    assert account_reference("other-admin") != reference
    with pytest.raises(ValueError):
        canonical_account_reference_input(" admin-actor ")


def test_unknown_or_malformed_reference_fails_before_target_scan() -> None:
    backend = FakeLifecycleBackend()
    app_client = client(backend)
    malformed = app_client.get(
        "/admin/users/not-an-account-ref/lifecycle-eligibility",
        headers={"Authorization": "Bearer admin-token"},
    )
    assert malformed.status_code == 422
    assert backend.profile_scan_calls == 0
    unknown = app_client.get(
        f"/admin/users/{account_reference('missing')}/lifecycle-eligibility",
        headers={"Authorization": "Bearer admin-token"},
    )
    assert unknown.status_code == 404
    assert "missing" not in unknown.text


def test_authorization_finishes_before_profile_scan() -> None:
    backend = FakeLifecycleBackend()
    response = client(backend).get(
        f"/admin/users/{account_reference('customer-1')}/lifecycle-eligibility",
        headers={"Authorization": "Bearer invalid"},
    )
    assert response.status_code == 401
    assert backend.profile_scan_calls == 0


def test_customer_and_admin_eligibility_is_advisory_only() -> None:
    backend = FakeLifecycleBackend()
    app_client = client(backend)
    customer = app_client.get(
        f"/admin/users/{account_reference('customer-1')}/lifecycle-eligibility",
        headers={"Authorization": "Bearer admin-token"},
    ).json()
    assert customer["operations"]["disable"] == {"eligible": True, "reason": None}
    assert customer["operations"]["reactivate"] == {"eligible": False, "reason": "already_active"}
    assert customer["operations"]["reassignDepartment"] == {"eligible": False, "reason": "role_not_reassignable"}

    self_target = app_client.get(
        f"/admin/users/{account_reference('admin-actor')}/lifecycle-eligibility",
        headers={"Authorization": "Bearer admin-token"},
    ).json()
    assert self_target["operations"]["disable"] == {"eligible": False, "reason": "self_target_forbidden"}
    assert self_target["operations"]["reactivate"] == {"eligible": False, "reason": "self_target_forbidden"}

    other_admin = app_client.get(
        f"/admin/users/{account_reference('admin-other')}/lifecycle-eligibility",
        headers={"Authorization": "Bearer admin-token"},
    ).json()
    assert other_admin["operations"]["disable"] == {"eligible": True, "reason": None}
    assert other_admin["operations"]["reactivate"] == {"eligible": False, "reason": "already_active"}

    manager = app_client.get(
        f"/admin/users/{account_reference('manager-1')}/lifecycle-eligibility",
        headers={"Authorization": "Bearer admin-token"},
    ).json()
    assert manager["operations"]["disable"] == {"eligible": True, "reason": None}
    assert manager["operations"]["reassignDepartment"] == {"eligible": False, "reason": "role_not_reassignable"}


def test_last_active_admin_is_not_advisory_eligible_for_disable() -> None:
    backend = FakeLifecycleBackend()
    del backend.profiles["admin-other"]
    response = client(backend).get(
        f"/admin/users/{account_reference('admin-actor')}/lifecycle-eligibility",
        headers={"Authorization": "Bearer admin-token"},
    )
    assert response.status_code == 200
    assert response.json()["operations"]["disable"] == {"eligible": False, "reason": "self_target_forbidden"}


def test_staff_assigned_unresolved_work_blocks_but_unassigned_work_does_not() -> None:
    backend = FakeLifecycleBackend()
    backend.tickets = [
        {"status": "in_progress", "assignedStaffId": None, "departmentId": "card_atm"},
        {"status": "triaged", "assignedStaffId": "other-staff", "departmentId": "card_atm"},
    ]
    unassigned = client(backend).get(
        f"/admin/users/{account_reference('staff-1')}/lifecycle-eligibility",
        headers={"Authorization": "Bearer admin-token"},
    )
    assert unassigned.status_code == 200
    assert unassigned.json()["operations"]["reassignDepartment"] == {"eligible": True, "reason": None}

    backend.tickets.append({"status": "awaiting_customer", "assignedStaffId": "staff-1"})
    assigned = client(backend).get(
        f"/admin/users/{account_reference('staff-1')}/lifecycle-eligibility",
        headers={"Authorization": "Bearer admin-token"},
    )
    assert assigned.status_code == 200
    assert assigned.json()["operations"]["reassignDepartment"] == {"eligible": False, "reason": "assigned_unresolved_work"}
    assert backend.ticket_scan_calls == 2


def test_inactive_profile_has_no_disable_eligibility_and_reactivation_is_advisory() -> None:
    backend = FakeLifecycleBackend()
    response = client(backend).get(
        f"/admin/users/{account_reference('staff-inactive')}/lifecycle-eligibility",
        headers={"Authorization": "Bearer admin-token"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["profileState"] == "inactive"
    assert body["operations"]["disable"] == {"eligible": False, "reason": "already_inactive"}
    assert body["operations"]["reactivate"] == {"eligible": False, "reason": "pending_setup_activation_forbidden"}


def test_trusted_completed_disable_proof_makes_reactivation_advisory_eligible() -> None:
    backend = FakeLifecycleBackend()

    def proof(**_kwargs: Any) -> str | None:
        return None

    backend.reactivation_eligibility_reason = proof  # type: ignore[attr-defined]
    response = client(backend).get(
        f"/admin/users/{account_reference('staff-inactive')}/lifecycle-eligibility",
        headers={"Authorization": "Bearer admin-token"},
    )
    assert response.status_code == 200
    assert response.json()["operations"]["reactivate"] == {"eligible": True, "reason": None}


def test_disable_route_exists_but_requires_strict_request_body() -> None:
    backend = FakeLifecycleBackend()
    response = client(backend).post(
        f"/admin/users/{account_reference('customer-1')}/disable",
        headers={"Authorization": "Bearer admin-token"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "request_validation_error"


def test_ticket_scan_over_bound_fails_closed() -> None:
    backend = FakeLifecycleBackend()
    backend.tickets = [{"status": "submitted", "assignedStaffId": None}] * 201
    response = client(backend).get(
        f"/admin/users/{account_reference('staff-1')}/lifecycle-eligibility",
        headers={"Authorization": "Bearer admin-token"},
    )
    assert response.status_code == 503
