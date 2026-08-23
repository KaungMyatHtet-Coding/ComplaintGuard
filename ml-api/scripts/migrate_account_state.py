"""Plan a bounded accountState backfill; never writes data in this slice."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.account_state import (
    PENDING_SETUP_ROLES,
    AccountStateValidationError,
    validate_account_state,
)

MAX_MIGRATION_PROFILES = 200
VALID_PROVISIONING_STATUSES = frozenset({"pending_setup"})
VALID_DISABLE_STATES = frozenset({"completed"})


class AccountStateMigrationError(ValueError):
    """The bounded migration input or trusted lineage is malformed."""


@dataclass(frozen=True)
class AccountStateMigrationUpdate:
    uid: str
    account_state: str


@dataclass(frozen=True)
class AccountStateMigrationPlan:
    updates: tuple[AccountStateMigrationUpdate, ...]
    unchanged: int
    inactive_unverified: int
    rejected: int

    def safe_summary(self) -> dict[str, int]:
        """Return counts only; no UID or lineage value is reportable."""

        return {
            "updates": len(self.updates),
            "unchanged": self.unchanged,
            "inactive_unverified": self.inactive_unverified,
            "rejected": self.rejected,
        }


def _profile_is_structurally_valid(profile: Mapping[str, Any]) -> bool:
    required = {
        "email",
        "displayName",
        "locale",
        "role",
        "departmentId",
        "active",
        "createdAt",
        "updatedAt",
    }
    if not (
        set(profile) == required or set(profile) == required | {"accountState"}
    ) or type(profile.get("active")) is not bool or profile.get("role") not in {
        "customer",
        "staff",
        "manager",
        "admin",
    }:
        return False
    role = profile["role"]
    if role == "staff" and not isinstance(profile.get("departmentId"), str):
        return False
    if role != "staff" and profile.get("departmentId") is not None:
        return False
    if not all(isinstance(profile.get(field), str) and profile[field] for field in ("email", "displayName", "locale")):
        return False
    if profile["locale"] not in {"en", "my"} or profile["createdAt"] is None or profile["updatedAt"] is None:
        return False
    if "accountState" in profile:
        try:
            validate_account_state(active=profile["active"], role=role, account_state=profile["accountState"])
        except AccountStateValidationError:
            return False
    return True


def _valid_provisioning_lineage(uid: str, role: str, lineage: Any) -> bool:
    return (
        role in PENDING_SETUP_ROLES
        and isinstance(lineage, Mapping)
        and lineage.get("targetUid") == uid
        and lineage.get("operation") == "create_pending_user"
        and lineage.get("status") in VALID_PROVISIONING_STATUSES
        and lineage.get("resultCode") == "pending_setup"
    )


def _valid_disable_lineage(uid: str, role: str, lineage: Any) -> bool:
    if role not in {"customer", "staff", "manager"} or not isinstance(lineage, Mapping):
        return False
    action = lineage.get("action")
    guard = lineage.get("guard")
    audit = lineage.get("audit")
    return (
        isinstance(action, Mapping)
        and isinstance(guard, Mapping)
        and isinstance(audit, Mapping)
        and isinstance(action.get("actionRef"), str)
        and action.get("targetUid") == uid
        and action.get("operation") == "disable"
        and action.get("state") == "completed"
        and action.get("resultCode") in VALID_DISABLE_STATES
        and guard.get("actionRef") == action.get("actionRef")
        and guard.get("targetUid") == uid
        and guard.get("operation") == "disable"
        and guard.get("state") == "inactive"
        and audit.get("actionRef") == action.get("actionRef")
        and audit.get("targetUid") == uid
        and audit.get("operation") == "disable"
        and audit.get("toState") == "completed"
        and audit.get("resultCode") == "completed"
    )


def _classify(profile: Mapping[str, Any], provisioning: Any, lifecycle: Any) -> str:
    active = profile["active"]
    role = profile["role"]
    if active is True:
        return "active"
    if _valid_provisioning_lineage(profile["uid"], role, provisioning):
        return "pending_setup"
    if _valid_disable_lineage(profile["uid"], role, lifecycle):
        return "disabled"
    return "inactive_unverified"


def build_account_state_migration_plan(
    profiles: Mapping[str, Mapping[str, Any]],
    *,
    provisioning_lineage: Mapping[str, Any],
    lifecycle_lineage: Mapping[str, Any],
    limit: int = MAX_MIGRATION_PROFILES,
    dry_run: bool = True,
) -> AccountStateMigrationPlan:
    """Build a deterministic, idempotent plan without applying any update."""

    if not dry_run:
        raise AccountStateMigrationError("non-dry-run migration is not available")
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= MAX_MIGRATION_PROFILES:
        raise AccountStateMigrationError("migration limit is invalid")
    if not isinstance(profiles, Mapping) or not isinstance(provisioning_lineage, Mapping) or not isinstance(lifecycle_lineage, Mapping):
        raise AccountStateMigrationError("migration inputs must be mappings")
    if len(profiles) > limit:
        raise AccountStateMigrationError("migration input exceeds bounded limit")
    if any(not isinstance(uid, str) or not uid for uid in profiles):
        raise AccountStateMigrationError("migration profile identifiers are invalid")

    updates: list[AccountStateMigrationUpdate] = []
    unchanged = 0
    inactive_unverified = 0
    rejected = 0
    for uid in sorted(profiles):
        profile = profiles[uid]
        if not isinstance(uid, str) or not uid or not isinstance(profile, Mapping):
            rejected += 1
            continue
        if not _profile_is_structurally_valid(profile):
            rejected += 1
            continue
        profile_with_uid = dict(profile)
        profile_with_uid["uid"] = uid
        try:
            state = _classify(
                profile_with_uid,
                provisioning_lineage.get(uid),
                lifecycle_lineage.get(uid),
            )
        except (KeyError, TypeError):
            rejected += 1
            continue
        if state == "inactive_unverified":
            inactive_unverified += 1
        if profile.get("accountState") == state:
            unchanged += 1
        else:
            updates.append(AccountStateMigrationUpdate(uid=uid, account_state=state))
    return AccountStateMigrationPlan(
        updates=tuple(updates),
        unchanged=unchanged,
        inactive_unverified=inactive_unverified,
        rejected=rejected,
    )


def validate_local_emulator_migration_boundary(
    *,
    project_id: str,
    environment: str,
    auth_emulator_host: str,
    firestore_emulator_host: str,
    write: bool = False,
    confirm: bool = False,
) -> None:
    """Reject every environment except the explicitly approved local boundary."""

    if (
        project_id != "demo-complaintguard"
        or environment != "local-emulator"
        or auth_emulator_host != "127.0.0.1:9099"
        or firestore_emulator_host != "127.0.0.1:8185"
    ):
        raise AccountStateMigrationError("migration requires the local Emulator boundary")
    if write or confirm:
        raise AccountStateMigrationError("migration writes are not available in this slice")
