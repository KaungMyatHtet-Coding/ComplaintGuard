from __future__ import annotations

import pytest

from scripts.migrate_account_state import (
    AccountStateMigrationError,
    build_account_state_migration_plan,
    validate_local_emulator_migration_boundary,
)


def profile(uid: str, *, active: bool, role: str = "customer", state: str | None = None) -> dict[str, object]:
    value: dict[str, object] = {
        "email": f"{uid}@example.test",
        "displayName": "Synthetic Profile",
        "locale": "en",
        "role": role,
        "departmentId": "card_atm" if role == "staff" else None,
        "active": active,
        "createdAt": "created",
        "updatedAt": "updated",
    }
    if state is not None:
        value["accountState"] = state
    return value


def test_migration_classifies_lineage_without_guessing_and_is_idempotent() -> None:
    profiles = {
        "z-active": profile("z-active", active=True),
        "b-pending": profile("b-pending", active=False, role="staff"),
        "c-disabled": profile("c-disabled", active=False),
        "d-unknown": profile("d-unknown", active=False, role="customer"),
    }
    plan = build_account_state_migration_plan(
        profiles,
        provisioning_lineage={"b-pending": {"targetUid": "b-pending", "operation": "create_pending_user", "status": "pending_setup", "resultCode": "pending_setup"}},
        lifecycle_lineage={
            "c-disabled": {
                "action": {"actionRef": "action-c", "targetUid": "c-disabled", "operation": "disable", "state": "completed", "resultCode": "completed"},
                "guard": {"actionRef": "action-c", "targetUid": "c-disabled", "operation": "disable", "state": "inactive"},
                "audit": {"actionRef": "action-c", "targetUid": "c-disabled", "operation": "disable", "toState": "completed", "resultCode": "completed"},
            }
        },
    )
    assert [(item.uid, item.account_state) for item in plan.updates] == [
        ("b-pending", "pending_setup"),
        ("c-disabled", "disabled"),
        ("d-unknown", "inactive_unverified"),
        ("z-active", "active"),
    ]
    assert plan.safe_summary() == {"updates": 4, "unchanged": 0, "inactive_unverified": 1, "rejected": 0}
    rerun = build_account_state_migration_plan(
        {uid: {**value, "accountState": state} for (uid, value), state in zip(profiles.items(), ["active", "pending_setup", "disabled", "inactive_unverified"])},
        provisioning_lineage={"b-pending": {"targetUid": "b-pending", "operation": "create_pending_user", "status": "pending_setup", "resultCode": "pending_setup"}},
        lifecycle_lineage={
            "c-disabled": {
                "action": {"actionRef": "action-c", "targetUid": "c-disabled", "operation": "disable", "state": "completed", "resultCode": "completed"},
                "guard": {"actionRef": "action-c", "targetUid": "c-disabled", "operation": "disable", "state": "inactive"},
                "audit": {"actionRef": "action-c", "targetUid": "c-disabled", "operation": "disable", "toState": "completed", "resultCode": "completed"},
            }
        },
    )
    assert rerun.updates == ()
    assert rerun.unchanged == 4


def test_migration_rejects_malformed_and_non_dry_run_inputs() -> None:
    plan = build_account_state_migration_plan(
        {"bad": {"active": False, "role": "customer"}},
        provisioning_lineage={},
        lifecycle_lineage={},
    )
    assert plan.rejected == 1
    with pytest.raises(AccountStateMigrationError):
        build_account_state_migration_plan({}, provisioning_lineage={}, lifecycle_lineage={}, dry_run=False)
    with pytest.raises(AccountStateMigrationError):
        validate_local_emulator_migration_boundary(project_id="complaintguard", environment="cloud-staging", auth_emulator_host="127.0.0.1:9099", firestore_emulator_host="127.0.0.1:8185")
    validate_local_emulator_migration_boundary(project_id="demo-complaintguard", environment="local-emulator", auth_emulator_host="127.0.0.1:9099", firestore_emulator_host="127.0.0.1:8185")
    with pytest.raises(AccountStateMigrationError):
        validate_local_emulator_migration_boundary(project_id="demo-complaintguard", environment="local-emulator", auth_emulator_host="0.0.0.0:9099", firestore_emulator_host="127.0.0.1:8185")
    with pytest.raises(AccountStateMigrationError):
        validate_local_emulator_migration_boundary(project_id="demo-complaintguard", environment="local-emulator", auth_emulator_host="127.0.0.1:9099", firestore_emulator_host="127.0.0.1:8185", write=True)
