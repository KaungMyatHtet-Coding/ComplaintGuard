"""Focused Phase 2 tests for the additive department/Staff foundation."""

import pytest

from app.admin_auth import AdminPrincipal
from app.v2_contracts import V1_CATEGORY_IDS, V1_TICKET_STATUSES
from app.v2_foundation import (
    DepartmentCreateRequest,
    DepartmentUpdateRequest,
    FoundationConflict,
    FoundationPageRequest,
    InMemoryFoundationBackend,
    StaffCreateRequest,
    StaffUpdateRequest,
    staff_is_eligible_for_assignment,
)

ACTOR = AdminPrincipal("admin-uid", "admin@example.test", "Admin", "en")
DEPARTMENTS = (
    "account_branch_services", "cards_atm_pos", "mobile_internet_banking",
    "transfers_payments_remittance", "loans_credit", "fraud_scam_unauthorized",
    "kyc_verification_restrictions", "general_complaints",
)


def department_request(department_id: str, key: str) -> DepartmentCreateRequest:
    return DepartmentCreateRequest(
        departmentId=department_id, nameEn=department_id.replace("_", " ").title(),
        nameMy="မြန်မာဌာန", description="Phase 2 workspace", isCustomerComplaintUnit=department_id == "general_complaints",
        routingEnabled=True, assignmentPolicy={"strategy": "priority_then_workload", "languagePreference": True, "allowManualClaim": False},
        defaultStaffCapacity=10, idempotencyKey=key,
    )


def staff_request(key: str, **changes: object) -> StaffCreateRequest:
    value = {"employeeCode": "AYA-001", "displayName": "Aye Aye", "workEmail": "aye@example.test", "departmentIds": [DEPARTMENTS[0]], "primaryDepartmentId": DEPARTMENTS[0], "position": "Customer Support Staff", "employmentState": "invited", "availabilityState": "offline", "capacity": 5, "languageSkills": ["en", "my"], "shift": "day", "idempotencyKey": key}
    value.update(changes)
    return StaffCreateRequest(**value)


def prepare() -> InMemoryFoundationBackend:
    backend = InMemoryFoundationBackend()
    for index, department_id in enumerate(DEPARTMENTS):
        backend.create_department(ACTOR, department_request(department_id, f"department-{index:02d}"))
    return backend


def test_v1_contracts_remain_unchanged() -> None:
    assert set(V1_CATEGORY_IDS) == {"transfer_payment", "account_support", "card_atm", "fraud_security", "loan_credit", "general_support"}
    assert "submitted" in V1_TICKET_STATUSES


def test_departments_are_idempotent_and_ids_are_stable() -> None:
    backend = InMemoryFoundationBackend()
    created = backend.create_department(ACTOR, department_request("general_complaints", "same-key-1"))
    replay = backend.create_department(ACTOR, department_request("general_complaints", "same-key-1"))
    assert created == replay
    updated = backend.update_department(ACTOR, "general_complaints", DepartmentUpdateRequest(nameEn="Edited", nameMy="ပြင်ပြီး", description="Edited", routingEnabled=True, assignmentPolicy={"strategy": "priority_then_workload", "languagePreference": True, "allowManualClaim": False}, defaultStaffCapacity=12, idempotencyKey="update-key-1"))
    assert updated["departmentId"] == "general_complaints"
    with pytest.raises(FoundationConflict):
        backend.create_department(ACTOR, department_request("general_complaints", "different-key"))


def test_staff_membership_identity_and_retry_are_preserved() -> None:
    backend = prepare()
    created = backend.create_staff(ACTOR, staff_request("staff-key-1"))
    assert backend.create_staff(ACTOR, staff_request("staff-key-1")) == created
    assert (DEPARTMENTS[0], created["staffId"]) in backend.memberships
    updated = backend.update_staff(ACTOR, created["staffId"], StaffUpdateRequest(displayName="Aye Updated", workEmail="aye@example.test", departmentIds=[DEPARTMENTS[1]], primaryDepartmentId=DEPARTMENTS[1], position="Senior Support", employmentState="departed", availabilityState="offline", capacity=6, activeWorkload=0, languageSkills=["my"], shift="day", loginEnabled=False, idempotencyKey="staff-update-1"))
    assert updated["departedAt"] is not None
    assert (DEPARTMENTS[0], created["staffId"]) not in backend.memberships
    assert (DEPARTMENTS[1], created["staffId"]) in backend.memberships
    assert len(backend.identities) == 2
    assert created["employeeCode"] == backend.identities[created["historicalIdentityId"]]["employeeCode"]
    assert backend.auth[created["uid"]]["disabled"] is True


def test_validation_rejects_duplicate_codes_bad_departments_and_bad_capacity() -> None:
    backend = prepare()
    backend.create_staff(ACTOR, staff_request("staff-key-2"))
    with pytest.raises(FoundationConflict):
        backend.create_staff(ACTOR, staff_request("staff-key-3", workEmail="other@example.test"))
    with pytest.raises(ValueError):
        backend.create_staff(ACTOR, staff_request("staff-key-4", departmentIds=["not-a-department"], primaryDepartmentId="not-a-department"))
    with pytest.raises(ValueError):
        staff_request("staff-key-5", capacity=0)


def test_bounded_pagination_and_safe_filters() -> None:
    backend = prepare()
    backend.create_staff(ACTOR, staff_request("staff-key-6"))
    page = backend.list_staff(FoundationPageRequest(pageSize=1, employmentState="invited"))
    assert len(page.staff) == 1
    assert page.has_more is False


def test_non_active_or_disabled_staff_are_not_future_assignment_eligible() -> None:
    backend = prepare()
    profile = backend.create_staff(ACTOR, staff_request("staff-key-7"))
    assert staff_is_eligible_for_assignment(profile) is False
    active = backend.update_staff(ACTOR, profile["staffId"], StaffUpdateRequest(displayName=profile["displayName"], workEmail=profile["workEmail"], departmentIds=profile["departmentIds"], primaryDepartmentId=profile["primaryDepartmentId"], position=profile["position"], employmentState="active", availabilityState="available", capacity=5, activeWorkload=0, languageSkills=["en"], shift=profile["shift"], loginEnabled=True, idempotencyKey="staff-update-7"))
    assert staff_is_eligible_for_assignment(active) is True
    suspended = backend.update_staff(ACTOR, profile["staffId"], StaffUpdateRequest(displayName=profile["displayName"], workEmail=profile["workEmail"], departmentIds=profile["departmentIds"], primaryDepartmentId=profile["primaryDepartmentId"], position=profile["position"], employmentState="suspended", availabilityState="offline", capacity=5, activeWorkload=0, languageSkills=["en"], shift=profile["shift"], loginEnabled=False, idempotencyKey="staff-update-8"))
    assert staff_is_eligible_for_assignment(suspended) is False
