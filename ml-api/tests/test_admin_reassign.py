"""Pure tests for the trusted Staff department reassignment workflow."""

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

import pytest

from app.admin_auth import AdminPrincipal
from app.admin_directory import AdminDirectoryRow, account_reference
from app.admin_lifecycle import (
    InMemoryLifecycleRepository,
    LifecycleActionService,
    LifecycleIdempotencyConflict,
)
from app.admin_reassign import (
    AdminReassignService,
    ReassignAssignedWork,
    ReassignSameDepartment,
)

NOW = datetime(2026, 8, 23, 10, 0, tzinfo=timezone.utc)


def _profile(department: str = "account_support") -> dict[str, Any]:
    return {
        "email": "staff@example.test",
        "displayName": "Synthetic Staff",
        "locale": "en",
        "role": "staff",
        "departmentId": department,
        "active": True,
        "accountState": "active",
        "createdAt": NOW,
        "updatedAt": NOW,
    }


class FakeReassignBackend(InMemoryLifecycleRepository):
    def __init__(self) -> None:
        super().__init__()
        self.profiles = {"staff-uid": _profile()}
        self.tickets: list[dict[str, Any]] = []

    def resolve_target(self, account_ref: str) -> tuple[str, AdminDirectoryRow]:
        value = self.profiles["staff-uid"]
        return "staff-uid", AdminDirectoryRow(
            email=value["email"],
            displayName=value["displayName"],
            locale=value["locale"],
            role="staff",
            departmentId=value["departmentId"],
            active=value["active"],
            accountState=value["accountState"],
            accountRef=account_ref,
        )

    def reassign_department(self, action_ref: str, *, expected_version: int, now: datetime):
        current = self.records[action_ref]
        if any(
            ticket.get("assignedStaffId") == current.target_uid
            and ticket.get("status") in {"submitted", "triaged", "in_progress", "awaiting_customer"}
            for ticket in self.tickets
        ):
            updated = super().transition(
                action_ref,
                expected_version=expected_version,
                to_state="conflict",
                result_code="assigned_unresolved_work",
                now=now,
            )
        else:
            self.profiles[current.target_uid]["departmentId"] = current.requested_department
            self.profiles[current.target_uid]["updatedAt"] = now
            updated = super().transition(
                action_ref,
                expected_version=expected_version,
                to_state="completed",
                result_code="completed",
                now=now,
            )
        LifecycleActionService(self, clock=lambda: now).append_transition_audit(
            updated, from_state=current.state
        )
        return updated


def _actor() -> AdminPrincipal:
    return AdminPrincipal(
        uid="admin-uid",
        email="admin@example.test",
        display_name="Synthetic Admin",
        locale="en",
    )


def _run(backend: FakeReassignBackend, key: str, department: str):
    return AdminReassignService(backend, clock=lambda: NOW).reassign(
        _actor(),
        account_ref=account_reference("staff-uid"),
        idempotency_key=key,
        department_id=department,
    )


@pytest.mark.parametrize(
    "department",
    ["transfer_payment", "account_support", "card_atm", "fraud_security", "loan_credit", "general_support"],
)
def test_reassignment_returns_only_safe_fields(department: str) -> None:
    backend = FakeReassignBackend()
    if department == "account_support":
        with pytest.raises(ReassignSameDepartment):
            _run(backend, "reassign_001", department)
        assert not backend.records
        return
    result = _run(backend, "reassign_001", department)
    assert result.model_dump(by_alias=True) == {
        "accountRef": account_reference("staff-uid"),
        "operation": "reassign_department",
        "status": "completed",
        "departmentId": department,
    }
    assert set(result.model_dump(by_alias=True)) == {"accountRef", "operation", "status", "departmentId"}


def test_assigned_unresolved_work_conflicts_without_profile_change_and_retry_is_possible() -> None:
    backend = FakeReassignBackend()
    before = deepcopy(backend.profiles["staff-uid"])
    backend.tickets = [{"assignedStaffId": "staff-uid", "status": "in_progress"}]
    with pytest.raises(ReassignAssignedWork):
        _run(backend, "reassign_001", "card_atm")
    assert backend.profiles["staff-uid"] == before
    backend.tickets.clear()
    result = _run(backend, "reassign_002", "card_atm")
    assert result.status == "completed"


def test_completed_retry_has_same_safe_result_without_new_action() -> None:
    backend = FakeReassignBackend()
    first = _run(backend, "reassign_001", "card_atm")
    count = len(backend.records)
    second = _run(backend, "reassign_001", "card_atm")
    assert second == first
    assert len(backend.records) == count


def test_completed_same_key_with_changed_department_conflicts() -> None:
    backend = FakeReassignBackend()
    _run(backend, "reassign_001", "card_atm")
    with pytest.raises(LifecycleIdempotencyConflict):
        _run(backend, "reassign_001", "fraud_security")
