"""Trusted, backend-only account-lifecycle coordination and disable phases.

This module deliberately has no HTTP route, Auth mutation, or import-time
client construction. It provides validated lifecycle records plus trusted
Firestore transactions for the recoverable profile-inactivation phase.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Literal, Protocol

from app.language import normalize_input
from app.ticketing import (
    DEPARTMENT_IDS,
    PersistenceError,
    firebase_admin_clients,
    run_firestore_transaction,
)

LifecycleOperation = Literal["disable", "reactivate", "reassign_department"]
LifecycleState = Literal[
    "reserved",
    "profile_inactivated",
    "auth_disable_pending",
    "auth_enable_pending",
    "profile_activation_pending",
    "completed",
    "conflict",
    "failed",
]

LIFECYCLE_ACTION_DOMAIN = "complaintguard:admin-lifecycle:v1"
LIFECYCLE_AUDIT_DOMAIN = "complaintguard:admin-lifecycle-audit:v1"
LIFECYCLE_TARGET_GUARD_DOMAIN = "complaintguard:admin-lifecycle-target-guard:v1"
LIFECYCLE_POLICY_VERSION = "r2c2a-v1"
LIFECYCLE_ACTIONS_COLLECTION = "adminAccountLifecycleActions"
LIFECYCLE_TARGET_GUARDS_COLLECTION = "adminAccountLifecycleTargetGuards"
LIFECYCLE_AUDIT_EVENTS_COLLECTION = "adminAccountLifecycleAuditEvents"
LIFECYCLE_ACTION_REF_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_UID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_IDEMPOTENCY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
_RESULT_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
MAX_ACTION_VERSION = 2_147_483_647
MAX_REASSIGNMENT_TICKET_SCAN = 200
LIFECYCLE_RESULT_CODES = frozenset(
    {
        "ok",
        "completed",
        "profile_inactivated",
        "auth_disable_pending",
        "auth_enable_pending",
        "profile_activation_pending",
        "idempotency_conflict",
        "lifecycle_conflict",
        "stale_version",
        "validation_failed",
        "service_unavailable",
        "assigned_unresolved_work",
        "last_active_admin",
        "self_target_forbidden",
        "pending_setup",
        "pending_setup_activation_forbidden",
    }
)
_ACTION_FIELDS = {
    "operation",
    "actorUid",
    "targetUid",
    "actionRef",
    "idempotencyKeyHash",
    "requestFingerprint",
    "state",
    "resultCode",
    "accountRef",
    "requestedDepartment",
    "targetRole",
    "version",
    "createdAt",
    "updatedAt",
    "completedAt",
    "previousActionRef",
}
_AUDIT_FIELDS = {
    "eventRef",
    "actionRef",
    "operation",
    "actorUid",
    "targetUid",
    "fromState",
    "toState",
    "resultCode",
    "version",
    "createdAt",
}
_GUARD_FIELDS = {
    "guardRef",
    "targetUid",
    "actionRef",
    "operation",
    "state",
    "version",
    "createdAt",
    "updatedAt",
}
_GUARD_STATES = frozenset({"active", "inactive", "blocked"})
_PROFILE_FIELDS = {
    "email",
    "displayName",
    "locale",
    "role",
    "departmentId",
    "active",
    "createdAt",
    "updatedAt",
}
_PROFILE_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PROFILE_ROLES = frozenset({"customer", "staff", "manager", "admin"})
_PROFILE_DEPARTMENTS = frozenset(DEPARTMENT_IDS)


def _guard_state_for_action(
    state: LifecycleState,
) -> Literal["active", "inactive", "blocked"]:
    if state == "failed":
        return "blocked"
    if state in {"completed", "conflict"}:
        return "inactive"
    return "active"


def _validate_disable_profile(document: Mapping[str, object], target_uid: str) -> dict[str, object]:
    """Strictly validate the profile shape used by the disable transaction."""

    if not isinstance(document, Mapping) or set(document) != _PROFILE_FIELDS:
        raise LifecycleValidationError("lifecycle target profile is invalid")
    email = document["email"]
    display_name = document["displayName"]
    role = document["role"]
    department = document["departmentId"]
    try:
        created_at = _aware(document["createdAt"], "createdAt")  # type: ignore[arg-type]
        updated_at = _aware(document["updatedAt"], "updatedAt")  # type: ignore[arg-type]
    except LifecycleValidationError:
        raise LifecycleValidationError("lifecycle target profile is invalid") from None
    if (
        not isinstance(email, str)
        or not _PROFILE_EMAIL_PATTERN.fullmatch(email)
        or email != email.strip().lower()
        or not isinstance(display_name, str)
        or display_name != normalize_input(display_name)
        or not display_name
        or document["locale"] not in {"en", "my"}
        or role not in _PROFILE_ROLES
        or type(document["active"]) is not bool
        or updated_at < created_at
        or (role == "staff" and department not in _PROFILE_DEPARTMENTS)
        or (role != "staff" and department is not None)
    ):
        raise LifecycleValidationError("lifecycle target profile is invalid")
    _require_uid(target_uid, "target UID")
    return dict(document)

# Same-state writes support recovery retries without inventing a new action.
ALLOWED_LIFECYCLE_TRANSITIONS: dict[LifecycleState, frozenset[LifecycleState]] = {
    "reserved": frozenset(
        {
            "reserved",
            "profile_inactivated",
            "auth_disable_pending",
            "auth_enable_pending",
            "profile_activation_pending",
            "completed",
            "conflict",
            "failed",
        }
    ),
    "profile_inactivated": frozenset(
        {"profile_inactivated", "auth_disable_pending", "completed", "failed"}
    ),
    "auth_disable_pending": frozenset(
        {"auth_disable_pending", "completed", "failed"}
    ),
    "auth_enable_pending": frozenset(
        {"auth_enable_pending", "profile_activation_pending", "failed"}
    ),
    "profile_activation_pending": frozenset(
        {"profile_activation_pending", "completed", "failed"}
    ),
    "completed": frozenset({"completed"}),
    "conflict": frozenset({"conflict"}),
    "failed": frozenset({"failed"}),
}

# The shared state set is intentionally constrained further by operation.  A
# disable action cannot enter an Auth-enable state, and a reassignment does
# not pass through Auth/profile recovery states.
ALLOWED_OPERATION_TRANSITIONS: dict[
    LifecycleOperation, dict[LifecycleState, frozenset[LifecycleState]]
] = {
    "disable": {
        "reserved": frozenset({"reserved", "profile_inactivated", "conflict", "failed"}),
        "profile_inactivated": frozenset({"profile_inactivated", "auth_disable_pending", "completed", "failed"}),
        "auth_disable_pending": frozenset({"auth_disable_pending", "completed", "failed"}),
        "completed": frozenset({"completed"}),
        "conflict": frozenset({"conflict"}),
        "failed": frozenset({"failed"}),
        "auth_enable_pending": frozenset(),
        "profile_activation_pending": frozenset(),
    },
    "reactivate": {
        "reserved": frozenset({"reserved", "auth_enable_pending", "conflict", "failed"}),
        "auth_enable_pending": frozenset({"auth_enable_pending", "profile_activation_pending", "failed"}),
        "profile_activation_pending": frozenset({"profile_activation_pending", "completed", "failed"}),
        "completed": frozenset({"completed"}),
        "conflict": frozenset({"conflict"}),
        "failed": frozenset({"failed"}),
        "profile_inactivated": frozenset(),
    },
    "reassign_department": {
        "reserved": frozenset({"reserved", "completed", "conflict", "failed"}),
        "completed": frozenset({"completed"}),
        "conflict": frozenset({"conflict"}),
        "failed": frozenset({"failed"}),
        "profile_inactivated": frozenset(),
        "auth_disable_pending": frozenset(),
        "auth_enable_pending": frozenset(),
        "profile_activation_pending": frozenset(),
    },
}


class LifecycleValidationError(ValueError):
    """A trusted caller supplied data outside the lifecycle contract."""


class LifecycleConflictError(RuntimeError):
    """The requested action cannot safely proceed or be reused."""


class LifecycleIdempotencyConflict(LifecycleConflictError):
    """An idempotency key is bound to a different request."""


class LifecycleStateConflict(LifecycleConflictError):
    """A state or optimistic-version transition is no longer valid."""


class LifecycleReactivationNotEligible(LifecycleStateConflict):
    """No trusted completed disable lineage authorizes reactivation."""


class LifecycleRecoveryNotFound(LookupError):
    """No recoverable lifecycle action is owned by the target guard."""


class LifecycleRecoveryActorMismatch(LifecycleConflictError):
    """The existing action belongs to a different Admin actor."""


class LifecycleRecoveryOperationMismatch(LifecycleConflictError):
    """The recovery request does not match the existing action intent."""


class LifecycleOperatorRecoveryRequired(LifecycleConflictError):
    """A failed action or blocked guard requires separate operator recovery."""


def _require_uid(value: str, field: str) -> str:
    if not isinstance(value, str) or not _UID_PATTERN.fullmatch(value):
        raise LifecycleValidationError(f"{field} is invalid")
    return value


def _require_hex(value: str, field: str) -> str:
    if not isinstance(value, str) or not _HASH_PATTERN.fullmatch(value):
        raise LifecycleValidationError(f"{field} is invalid")
    return value


def normalize_idempotency_key(value: str) -> str:
    if not isinstance(value, str):
        raise LifecycleValidationError("idempotency key is invalid")
    normalized = normalize_input(value)
    if not _IDEMPOTENCY_PATTERN.fullmatch(normalized):
        raise LifecycleValidationError("idempotency key is invalid")
    return normalized


def _require_operation(value: str) -> LifecycleOperation:
    if not isinstance(value, str) or value not in {"disable", "reactivate", "reassign_department"}:
        raise LifecycleValidationError("operation is invalid")
    return value  # type: ignore[return-value]


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def lifecycle_action_reference(
    *,
    actor_uid: str,
    target_uid: str,
    idempotency_key: str,
    operation: str,
    domain: str = LIFECYCLE_ACTION_DOMAIN,
    policy_version: str = LIFECYCLE_POLICY_VERSION,
) -> str:
    """Return the opaque deterministic action document reference."""

    actor = _require_uid(actor_uid, "actor UID")
    target = _require_uid(target_uid, "target UID")
    key = normalize_idempotency_key(idempotency_key)
    op = _require_operation(operation)
    if domain != LIFECYCLE_ACTION_DOMAIN or policy_version != LIFECYCLE_POLICY_VERSION:
        raise LifecycleValidationError("lifecycle hash contract is invalid")
    return _sha256(
        {
            "actorUid": actor,
            "domain": domain,
            "idempotencyKey": key,
            "operation": op,
            "policyVersion": policy_version,
            "targetUid": target,
        }
    )


def lifecycle_request_fingerprint(
    *,
    target_uid: str,
    operation: str,
    requested_department: str | None = None,
    policy_version: str = LIFECYCLE_POLICY_VERSION,
) -> str:
    """Hash only trusted mutation intent, never credentials or profile data."""

    target = _require_uid(target_uid, "target UID")
    op = _require_operation(operation)
    if policy_version != LIFECYCLE_POLICY_VERSION:
        raise LifecycleValidationError("lifecycle policy version is invalid")
    department = requested_department
    if op == "reassign_department":
        if department not in DEPARTMENT_IDS:
            raise LifecycleValidationError("department is invalid")
    elif department is not None:
        raise LifecycleValidationError("department is not valid for this operation")
    return _sha256(
        {
            "departmentId": department,
            "operation": op,
            "policyVersion": policy_version,
            "targetUid": target,
        }
    )


def lifecycle_audit_event_reference(
    *,
    action_ref: str,
    to_state: str,
    version: int,
    operation: str = "disable",
    from_state: str = "reserved",
    result_code: str | None = None,
) -> str:
    _require_hex(action_ref, "action reference")
    op = _require_operation(operation)
    if from_state not in ALLOWED_LIFECYCLE_TRANSITIONS:
        raise LifecycleValidationError("from state is invalid")
    if to_state not in ALLOWED_LIFECYCLE_TRANSITIONS:
        raise LifecycleValidationError("state is invalid")
    if type(version) is not int or version < 1:
        raise LifecycleValidationError("version is invalid")
    if result_code is not None and (
        not isinstance(result_code, str)
        or not _RESULT_CODE_PATTERN.fullmatch(result_code)
        or result_code not in LIFECYCLE_RESULT_CODES
    ):
        raise LifecycleValidationError("result code is invalid")
    return _sha256(
        {
            "actionRef": action_ref,
            "domain": LIFECYCLE_AUDIT_DOMAIN,
            "fromState": from_state,
            "operation": op,
            "policyVersion": LIFECYCLE_POLICY_VERSION,
            "resultCode": result_code,
            "toState": to_state,
            "version": version,
        }
    )


def lifecycle_target_guard_reference(
    *, target_uid: str, project_id: str, environment: str
) -> str:
    """Return an opaque target lock reference for one project boundary."""

    target = _require_uid(target_uid, "target UID")
    if not isinstance(project_id, str) or not project_id or len(project_id) > 128:
        raise LifecycleValidationError("project boundary is invalid")
    if not isinstance(environment, str) or not environment or len(environment) > 64:
        raise LifecycleValidationError("environment boundary is invalid")
    return _sha256(
        {
            "domain": LIFECYCLE_TARGET_GUARD_DOMAIN,
            "environment": environment,
            "policyVersion": LIFECYCLE_POLICY_VERSION,
            "projectId": project_id,
            "targetUid": target,
        }
    )


def _aware(value: datetime, field: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise LifecycleValidationError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class LifecycleActionRecord:
    operation: LifecycleOperation
    actor_uid: str
    target_uid: str
    action_ref: str
    idempotency_key_hash: str
    request_fingerprint: str
    state: LifecycleState
    result_code: str | None
    target_role: Literal["customer", "staff", "manager", "admin"]
    created_at: datetime
    updated_at: datetime
    version: int = 1
    account_ref: str | None = None
    requested_department: str | None = None
    completed_at: datetime | None = None
    previous_action_ref: str | None = None

    def __post_init__(self) -> None:
        _require_uid(self.actor_uid, "actor UID")
        _require_uid(self.target_uid, "target UID")
        if self.actor_uid == self.target_uid:
            raise LifecycleValidationError("actor and target must differ")
        _require_hex(self.action_ref, "action reference")
        _require_hex(self.idempotency_key_hash, "idempotency fingerprint")
        _require_hex(self.request_fingerprint, "request fingerprint")
        _require_operation(self.operation)
        if self.state not in ALLOWED_LIFECYCLE_TRANSITIONS:
            raise LifecycleValidationError("state is invalid")
        if self.target_role not in {"customer", "staff", "manager", "admin"}:
            raise LifecycleValidationError("target role is invalid")
        if type(self.version) is not int or not 1 <= self.version <= MAX_ACTION_VERSION:
            raise LifecycleValidationError("version is invalid")
        if self.result_code is not None and (
            not isinstance(self.result_code, str)
            or not _RESULT_CODE_PATTERN.fullmatch(self.result_code)
            or self.result_code not in LIFECYCLE_RESULT_CODES
        ):
            raise LifecycleValidationError("result code is invalid")
        if self.operation == "reassign_department":
            if self.target_role != "staff" or self.requested_department not in DEPARTMENT_IDS:
                raise LifecycleValidationError("reassignment fields are invalid")
        elif self.requested_department is not None:
            raise LifecycleValidationError("department is not valid for this operation")
        if self.account_ref is not None and (
            not isinstance(self.account_ref, str)
            or not re.fullmatch(r"^acct_v1_[0-9a-f]{64}$", self.account_ref)
        ):
            raise LifecycleValidationError("account reference is invalid")
        if self.previous_action_ref is not None:
            _require_hex(self.previous_action_ref, "previous action reference")
            if self.previous_action_ref == self.action_ref:
                raise LifecycleValidationError("previous action cannot self-reference")
            if self.operation != "reactivate":
                raise LifecycleValidationError("previous action is invalid")
        created_at = _aware(self.created_at, "createdAt")
        updated_at = _aware(self.updated_at, "updatedAt")
        if updated_at < created_at:
            raise LifecycleValidationError("updatedAt precedes createdAt")
        if self.completed_at is not None:
            completed_at = _aware(self.completed_at, "completedAt")
            if self.state != "completed" or completed_at < created_at:
                raise LifecycleValidationError("completedAt is invalid")
        elif self.state == "completed":
            raise LifecycleValidationError("completedAt is required for completion")

    def to_document(self) -> dict[str, object]:
        """Return the backend-only allowlisted persistence shape."""

        document: dict[str, object] = {
            "operation": self.operation,
            "actorUid": self.actor_uid,
            "targetUid": self.target_uid,
            "actionRef": self.action_ref,
            "idempotencyKeyHash": self.idempotency_key_hash,
            "requestFingerprint": self.request_fingerprint,
            "state": self.state,
            "resultCode": self.result_code,
            "targetRole": self.target_role,
            "version": self.version,
            "createdAt": _aware(self.created_at, "createdAt"),
            "updatedAt": _aware(self.updated_at, "updatedAt"),
        }
        if self.account_ref is not None:
            document["accountRef"] = self.account_ref
        if self.requested_department is not None:
            document["requestedDepartment"] = self.requested_department
        if self.completed_at is not None:
            document["completedAt"] = _aware(self.completed_at, "completedAt")
        if self.previous_action_ref is not None:
            document["previousActionRef"] = self.previous_action_ref
        return document


@dataclass(frozen=True)
class LifecycleAuditEvent:
    event_ref: str
    action_ref: str
    operation: LifecycleOperation
    actor_uid: str
    target_uid: str
    from_state: LifecycleState
    to_state: LifecycleState
    result_code: str | None
    version: int
    created_at: datetime

    def __post_init__(self) -> None:
        _require_hex(self.event_ref, "event reference")
        _require_hex(self.action_ref, "action reference")
        _require_uid(self.actor_uid, "actor UID")
        _require_uid(self.target_uid, "target UID")
        if self.actor_uid == self.target_uid:
            raise LifecycleValidationError("actor and target must differ")
        _require_operation(self.operation)
        if self.from_state not in ALLOWED_LIFECYCLE_TRANSITIONS or self.to_state not in ALLOWED_LIFECYCLE_TRANSITIONS:
            raise LifecycleValidationError("state is invalid")
        if self.to_state not in ALLOWED_OPERATION_TRANSITIONS[self.operation][self.from_state]:
            raise LifecycleValidationError("audit transition is invalid")
        if self.event_ref != lifecycle_audit_event_reference(
            action_ref=self.action_ref,
            from_state=self.from_state,
            operation=self.operation,
            result_code=self.result_code,
            to_state=self.to_state,
            version=self.version,
        ):
            raise LifecycleValidationError("event reference does not match transition")
        if type(self.version) is not int or not 1 <= self.version <= MAX_ACTION_VERSION:
            raise LifecycleValidationError("version is invalid")
        if self.result_code is not None and (
            not isinstance(self.result_code, str)
            or not _RESULT_CODE_PATTERN.fullmatch(self.result_code)
            or self.result_code not in LIFECYCLE_RESULT_CODES
        ):
            raise LifecycleValidationError("result code is invalid")
        _aware(self.created_at, "createdAt")

    def to_document(self) -> dict[str, object]:
        return {
            "eventRef": self.event_ref,
            "actionRef": self.action_ref,
            "operation": self.operation,
            "actorUid": self.actor_uid,
            "targetUid": self.target_uid,
            "fromState": self.from_state,
            "toState": self.to_state,
            "resultCode": self.result_code,
            "version": self.version,
            "createdAt": _aware(self.created_at, "createdAt"),
        }


@dataclass(frozen=True)
class LifecycleTargetGuard:
    guard_ref: str
    target_uid: str
    action_ref: str
    operation: LifecycleOperation
    state: Literal["active", "inactive", "blocked"]
    version: int
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        _require_hex(self.guard_ref, "target guard reference")
        _require_uid(self.target_uid, "target UID")
        _require_hex(self.action_ref, "action reference")
        _require_operation(self.operation)
        if self.state not in _GUARD_STATES:
            raise LifecycleValidationError("target guard state is invalid")
        if type(self.version) is not int or not 1 <= self.version <= MAX_ACTION_VERSION:
            raise LifecycleValidationError("target guard version is invalid")
        created = _aware(self.created_at, "createdAt")
        updated = _aware(self.updated_at, "updatedAt")
        if updated < created:
            raise LifecycleValidationError("target guard updatedAt precedes createdAt")

    def to_document(self) -> dict[str, object]:
        return {
            "guardRef": self.guard_ref,
            "targetUid": self.target_uid,
            "actionRef": self.action_ref,
            "operation": self.operation,
            "state": self.state,
            "version": self.version,
            "createdAt": _aware(self.created_at, "createdAt"),
            "updatedAt": _aware(self.updated_at, "updatedAt"),
        }


def validate_action_document(document: Mapping[str, object]) -> LifecycleActionRecord:
    """Strictly parse a trusted coordination snapshot before future updates."""

    if not isinstance(document, Mapping):
        raise LifecycleValidationError("lifecycle action document is invalid")
    required = _ACTION_FIELDS - {
        "accountRef",
        "requestedDepartment",
        "completedAt",
        "previousActionRef",
    }
    if set(document) - _ACTION_FIELDS or not required <= set(document):
        raise LifecycleValidationError("lifecycle action fields are invalid")
    if document.get("operation") == "reactivate" and not isinstance(document.get("previousActionRef"), str):
        raise LifecycleValidationError("reactivation lineage is invalid")
    if document.get("operation") != "reactivate" and "previousActionRef" in document:
        raise LifecycleValidationError("unexpected reactivation lineage")
    return LifecycleActionRecord(
        operation=document["operation"],  # type: ignore[arg-type]
        actor_uid=document["actorUid"],  # type: ignore[arg-type]
        target_uid=document["targetUid"],  # type: ignore[arg-type]
        action_ref=document["actionRef"],  # type: ignore[arg-type]
        idempotency_key_hash=document["idempotencyKeyHash"],  # type: ignore[arg-type]
        request_fingerprint=document["requestFingerprint"],  # type: ignore[arg-type]
        state=document["state"],  # type: ignore[arg-type]
        result_code=document["resultCode"],  # type: ignore[arg-type]
        target_role=document["targetRole"],  # type: ignore[arg-type]
        version=document["version"],  # type: ignore[arg-type]
        created_at=document["createdAt"],  # type: ignore[arg-type]
        updated_at=document["updatedAt"],  # type: ignore[arg-type]
        account_ref=document.get("accountRef"),  # type: ignore[arg-type]
        requested_department=document.get("requestedDepartment"),  # type: ignore[arg-type]
        completed_at=document.get("completedAt"),  # type: ignore[arg-type]
        previous_action_ref=document.get("previousActionRef"),  # type: ignore[arg-type]
    )


def validate_audit_document(document: Mapping[str, object]) -> LifecycleAuditEvent:
    """Strictly parse an immutable trusted audit snapshot."""

    if not isinstance(document, Mapping) or set(document) != _AUDIT_FIELDS:
        raise LifecycleValidationError("lifecycle audit fields are invalid")
    return LifecycleAuditEvent(
        event_ref=document["eventRef"],  # type: ignore[arg-type]
        action_ref=document["actionRef"],  # type: ignore[arg-type]
        operation=document["operation"],  # type: ignore[arg-type]
        actor_uid=document["actorUid"],  # type: ignore[arg-type]
        target_uid=document["targetUid"],  # type: ignore[arg-type]
        from_state=document["fromState"],  # type: ignore[arg-type]
        to_state=document["toState"],  # type: ignore[arg-type]
        result_code=document["resultCode"],  # type: ignore[arg-type]
        version=document["version"],  # type: ignore[arg-type]
        created_at=document["createdAt"],  # type: ignore[arg-type]
    )


def validate_target_guard_document(document: Mapping[str, object]) -> LifecycleTargetGuard:
    """Strictly parse a target serialization guard before use."""

    if not isinstance(document, Mapping) or set(document) != _GUARD_FIELDS:
        raise LifecycleValidationError("lifecycle target guard fields are invalid")
    return LifecycleTargetGuard(
        guard_ref=document["guardRef"],  # type: ignore[arg-type]
        target_uid=document["targetUid"],  # type: ignore[arg-type]
        action_ref=document["actionRef"],  # type: ignore[arg-type]
        operation=document["operation"],  # type: ignore[arg-type]
        state=document["state"],  # type: ignore[arg-type]
        version=document["version"],  # type: ignore[arg-type]
        created_at=document["createdAt"],  # type: ignore[arg-type]
        updated_at=document["updatedAt"],  # type: ignore[arg-type]
    )


def _validate_completed_disable_lineage(
    previous: LifecycleActionRecord,
    event: LifecycleAuditEvent,
    *,
    target_uid: str,
    account_ref: str,
    target_role: str,
) -> None:
    if (
        previous.operation != "disable"
        or previous.state != "completed"
        or previous.result_code != "completed"
        or previous.target_uid != target_uid
        or previous.account_ref != account_ref
        or previous.target_role != target_role
        or event.action_ref != previous.action_ref
        or event.actor_uid != previous.actor_uid
        or event.operation != "disable"
        or event.target_uid != target_uid
        or event.from_state != "auth_disable_pending"
        or event.to_state != "completed"
        or event.result_code != "completed"
        or event.version != previous.version
    ):
        raise LifecycleReactivationNotEligible("completed disable proof is invalid")


class FirebaseLifecycleRepository:
    """Trusted Admin-SDK lifecycle coordinator; construction is explicit."""

    def __init__(
        self,
        clients: tuple[object, Any, object] | None = None,
        *,
        project_id: str = "demo-complaintguard",
        environment: str = "local-emulator",
        transaction_runner: Callable[[Any, Any], Any] = run_firestore_transaction,
    ) -> None:
        if project_id != "demo-complaintguard" or environment != "local-emulator":
            raise PersistenceError("cloud_staging_not_adopted")
        try:
            _, self._db, _ = clients or firebase_admin_clients()
        except PersistenceError:
            raise
        except Exception as exc:
            raise PersistenceError("Firebase lifecycle repository is not configured") from exc
        self._project_id = project_id
        self._environment = environment
        self._run_transaction = transaction_runner

    def _action_reference(self, action_ref: str) -> Any:
        _require_hex(action_ref, "action reference")
        return self._db.collection(LIFECYCLE_ACTIONS_COLLECTION).document(action_ref)

    def _guard_reference(self, guard_ref: str) -> Any:
        _require_hex(guard_ref, "target guard reference")
        return self._db.collection(LIFECYCLE_TARGET_GUARDS_COLLECTION).document(guard_ref)

    def _audit_reference(self, event_ref: str) -> Any:
        _require_hex(event_ref, "event reference")
        return self._db.collection(LIFECYCLE_AUDIT_EVENTS_COLLECTION).document(event_ref)

    @staticmethod
    def _snapshot(transaction: Any, reference: Any) -> Any:
        return next(transaction.get(reference))

    def reserve(self, record: LifecycleActionRecord) -> LifecycleActionRecord:
        guard_ref = lifecycle_target_guard_reference(
            target_uid=record.target_uid,
            project_id=self._project_id,
            environment=self._environment,
        )
        action_reference = self._action_reference(record.action_ref)
        guard_reference = self._guard_reference(guard_ref)
        guard = LifecycleTargetGuard(
            guard_ref=guard_ref,
            target_uid=record.target_uid,
            action_ref=record.action_ref,
            operation=record.operation,
            state="active",
            version=record.version,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

        def operation(transaction: Any) -> LifecycleActionRecord:
            action_snapshot = self._snapshot(transaction, action_reference)
            guard_snapshot = self._snapshot(transaction, guard_reference)
            existing_action = (
                validate_action_document(action_snapshot.to_dict() or {})
                if action_snapshot.exists
                else None
            )
            existing_guard = (
                validate_target_guard_document(guard_snapshot.to_dict() or {})
                if guard_snapshot.exists
                else None
            )
            if existing_action is not None:
                if existing_action.action_ref != record.action_ref:
                    raise PersistenceError("lifecycle action reference mismatch")
                if not _same_request(existing_action, record):
                    raise LifecycleIdempotencyConflict("idempotency request conflict")
                if existing_guard is None or existing_guard.guard_ref != guard_ref or existing_guard.action_ref != record.action_ref:
                    raise PersistenceError("lifecycle action guard mismatch")
                if existing_guard.target_uid != record.target_uid or existing_guard.operation != record.operation:
                    raise PersistenceError("lifecycle target guard ownership mismatch")
                if existing_guard.state != _guard_state_for_action(existing_action.state):
                    raise PersistenceError("lifecycle action guard state mismatch")
                return existing_action
            if existing_guard is not None:
                if existing_guard.state == "active":
                    raise LifecycleStateConflict("target has an active lifecycle operation")
                if existing_guard.state == "blocked":
                    raise PersistenceError("blocked target guard requires operator recovery")
                owner_reference = self._action_reference(existing_guard.action_ref)
                owner_snapshot = self._snapshot(transaction, owner_reference)
                if not owner_snapshot.exists:
                    raise PersistenceError("lifecycle target guard owner missing")
                owner_action = validate_action_document(owner_snapshot.to_dict() or {})
                if (
                    owner_action.action_ref != existing_guard.action_ref
                    or owner_action.target_uid != existing_guard.target_uid
                    or owner_action.operation != existing_guard.operation
                    or owner_action.state not in {"completed", "conflict"}
                    or _guard_state_for_action(owner_action.state) != existing_guard.state
                ):
                    raise PersistenceError("lifecycle target guard owner mismatch")
                if existing_guard.version >= MAX_ACTION_VERSION:
                    raise LifecycleStateConflict("target guard version exhausted")
                replacement_guard = replace(
                    existing_guard,
                    action_ref=record.action_ref,
                    operation=record.operation,
                    state="active",
                    version=existing_guard.version + 1,
                    updated_at=record.updated_at,
                )
                # The action create and inactive-guard ownership transfer are
                # one transaction. The read above is the guard version
                # precondition; a concurrent owner cannot be overwritten.
                transaction.create(action_reference, record.to_document())
                transaction.update(guard_reference, replacement_guard.to_document())
                return record
            # Both reads precede both creates. The fake and the real SDK can
            # therefore abort without committing a partial reservation.
            transaction.create(action_reference, record.to_document())
            transaction.create(guard_reference, guard.to_document())
            return record

        try:
            return self._run_transaction(self._db, operation)
        except (LifecycleConflictError, LifecycleValidationError, PersistenceError):
            raise
        except Exception as exc:
            raise PersistenceError("lifecycle action reservation failed") from exc

    def get_action(self, action_ref: str) -> LifecycleActionRecord | None:
        reference = self._action_reference(action_ref)

        def operation(transaction: Any) -> LifecycleActionRecord | None:
            snapshot = self._snapshot(transaction, reference)
            if not snapshot.exists:
                return None
            action = validate_action_document(snapshot.to_dict() or {})
            if action.action_ref != action_ref:
                raise PersistenceError("lifecycle action reference mismatch")
            return action

        try:
            return self._run_transaction(self._db, operation)
        except (LifecycleValidationError, PersistenceError):
            raise
        except Exception as exc:
            raise PersistenceError("lifecycle action lookup failed") from exc

    def recover_existing_action(
        self,
        *,
        actor_uid: str,
        target_uid: str,
        account_ref: str,
        target_role: str,
        operation: LifecycleOperation,
        requested_department: str | None = None,
    ) -> tuple[LifecycleActionRecord, LifecycleTargetGuard]:
        """Discover and strictly validate the action currently owned by a guard.

        This is deliberately read-only. It never derives an action reference
        from a client key and never reserves or transfers a lifecycle action.
        """

        _require_uid(actor_uid, "actor UID")
        _require_uid(target_uid, "target UID")
        if not re.fullmatch(r"^acct_v1_[0-9a-f]{64}$", account_ref):
            raise LifecycleValidationError("account reference is invalid")
        if target_role not in _PROFILE_ROLES or target_role == "admin":
            raise LifecycleValidationError("target role is invalid")
        op = _require_operation(operation)
        if op == "reassign_department" and requested_department not in DEPARTMENT_IDS:
            raise LifecycleValidationError("department is invalid")
        if op != "reassign_department" and requested_department is not None:
            raise LifecycleValidationError("department is invalid for this operation")
        guard_ref = lifecycle_target_guard_reference(
            target_uid=target_uid,
            project_id=self._project_id,
            environment=self._environment,
        )
        guard_reference = self._guard_reference(guard_ref)
        profile_reference = self._db.collection("users").document(target_uid)

        def operation_fn(transaction: Any) -> tuple[LifecycleActionRecord, LifecycleTargetGuard]:
            guard_snapshot = self._snapshot(transaction, guard_reference)
            if not guard_snapshot.exists:
                raise LifecycleRecoveryNotFound("lifecycle recovery is not available")
            guard = validate_target_guard_document(guard_snapshot.to_dict() or {})
            if guard.guard_ref != guard_ref or guard.target_uid != target_uid:
                raise PersistenceError("lifecycle recovery guard ownership is invalid")
            action_reference = self._action_reference(guard.action_ref)
            action_snapshot = self._snapshot(transaction, action_reference)
            profile_snapshot = self._snapshot(transaction, profile_reference)
            if not action_snapshot.exists or not profile_snapshot.exists:
                raise PersistenceError("lifecycle recovery persistence is incomplete")
            action = validate_action_document(action_snapshot.to_dict() or {})
            profile = _validate_disable_profile(profile_snapshot.to_dict() or {}, target_uid)
            if action.actor_uid != actor_uid:
                raise LifecycleRecoveryActorMismatch("lifecycle recovery actor mismatch")
            if action.target_uid != target_uid or action.account_ref != account_ref:
                raise PersistenceError("lifecycle recovery target ownership is invalid")
            if action.target_role != target_role:
                raise PersistenceError("lifecycle recovery target role is inconsistent")
            if profile["role"] != target_role:
                raise PersistenceError("lifecycle recovery profile role is inconsistent")
            if action.operation != op:
                raise LifecycleRecoveryOperationMismatch("lifecycle recovery operation mismatch")
            expected_fingerprint = lifecycle_request_fingerprint(
                target_uid=target_uid,
                operation=op,
                requested_department=requested_department,
            )
            if action.request_fingerprint != expected_fingerprint:
                raise LifecycleRecoveryOperationMismatch("lifecycle recovery request mismatch")
            if op == "reassign_department" and action.requested_department != requested_department:
                raise LifecycleRecoveryOperationMismatch("lifecycle recovery department mismatch")
            if (
                guard.action_ref != action.action_ref
                or guard.operation != action.operation
                or guard.target_uid != action.target_uid
                or guard.version < action.version
                or guard.state != _guard_state_for_action(action.state)
            ):
                raise PersistenceError("lifecycle recovery action and guard disagree")
            if action.state == "failed" or guard.state == "blocked":
                raise LifecycleOperatorRecoveryRequired("operator recovery is required")

            if op == "reactivate":
                if action.previous_action_ref is None:
                    raise PersistenceError("reactivation recovery lineage is missing")
                previous_reference = self._action_reference(action.previous_action_ref)
                previous_snapshot = self._snapshot(transaction, previous_reference)
                # The previous action's version is required to derive its
                # immutable completion event, so the action read precedes the
                # event read and no write is possible in this method.
                if not previous_snapshot.exists:
                    raise PersistenceError("reactivation recovery lineage is incomplete")
                previous = validate_action_document(previous_snapshot.to_dict() or {})
                previous_event_ref = lifecycle_audit_event_reference(
                    action_ref=previous.action_ref,
                    operation="disable",
                    from_state="auth_disable_pending",
                    to_state="completed",
                    result_code="completed",
                    version=previous.version,
                )
                previous_event_snapshot = self._snapshot(
                    transaction, self._audit_reference(previous_event_ref)
                )
                if not previous_event_snapshot.exists:
                    raise PersistenceError("reactivation recovery audit is incomplete")
                previous_event = validate_audit_document(previous_event_snapshot.to_dict() or {})
                _validate_completed_disable_lineage(
                    previous,
                    previous_event,
                    target_uid=target_uid,
                    account_ref=account_ref,
                    target_role=action.target_role,
                )

            if action.state in {"profile_inactivated", "auth_disable_pending", "auth_enable_pending", "profile_activation_pending", "completed", "conflict"}:
                if action.state == "profile_inactivated":
                    from_state, result_code = "reserved", "profile_inactivated"
                    to_state = "profile_inactivated"
                elif action.state == "auth_disable_pending":
                    from_state, result_code = "profile_inactivated", "auth_disable_pending"
                    to_state = "auth_disable_pending"
                elif action.state == "auth_enable_pending":
                    from_state, result_code = "reserved", "auth_enable_pending"
                    to_state = "auth_enable_pending"
                elif action.state == "profile_activation_pending":
                    from_state, result_code = "auth_enable_pending", "profile_activation_pending"
                    to_state = "profile_activation_pending"
                elif action.state == "conflict":
                    from_state, result_code = "reserved", action.result_code
                    to_state = "conflict"
                elif op == "disable":
                    from_state, result_code = "auth_disable_pending", "completed"
                    to_state = "completed"
                elif op == "reactivate":
                    from_state, result_code = "profile_activation_pending", "completed"
                    to_state = "completed"
                else:
                    from_state, result_code = "reserved", "completed"
                    to_state = "completed"
                event_ref = lifecycle_audit_event_reference(
                    action_ref=action.action_ref,
                    operation=op,
                    from_state=from_state,
                    to_state=to_state,
                    result_code=result_code,
                    version=action.version,
                )
                event_snapshot = self._snapshot(transaction, self._audit_reference(event_ref))
                if action.state != "reserved" and not event_snapshot.exists:
                    raise PersistenceError("lifecycle recovery audit is incomplete")
                if event_snapshot.exists:
                    event = validate_audit_document(event_snapshot.to_dict() or {})
                    if (
                        event.action_ref != action.action_ref
                        or event.operation != op
                        or event.actor_uid != action.actor_uid
                        or event.target_uid != target_uid
                        or event.from_state != from_state
                        or event.to_state != to_state
                        or event.result_code != result_code
                        or event.version != action.version
                    ):
                        raise PersistenceError("lifecycle recovery audit is inconsistent")

            if action.state == "completed":
                if op == "disable" and profile["active"] is not False:
                    raise PersistenceError("completed disable profile is inconsistent")
                if op == "reactivate" and profile["active"] is not True:
                    raise PersistenceError("completed reactivation profile is inconsistent")
                if op == "reassign_department" and (
                    profile["role"] != "staff"
                    or profile["active"] is not True
                    or profile["departmentId"] != requested_department
                ):
                    raise PersistenceError("completed reassignment profile is inconsistent")
            return action, guard

        try:
            return self._run_transaction(self._db, operation_fn)
        except (
            LifecycleRecoveryNotFound,
            LifecycleRecoveryActorMismatch,
            LifecycleRecoveryOperationMismatch,
            LifecycleOperatorRecoveryRequired,
            LifecycleValidationError,
            PersistenceError,
        ):
            raise
        except Exception as exc:
            raise PersistenceError("lifecycle recovery lookup failed") from exc

    def recovery_status(
        self,
        *,
        actor_uid: str,
        target_uid: str,
        account_ref: str,
        target_role: str,
    ) -> tuple[str, LifecycleOperation | None, str | None]:
        """Project one actor-owned action without changing persistence."""

        _require_uid(actor_uid, "actor UID")
        _require_uid(target_uid, "target UID")
        if not re.fullmatch(r"^acct_v1_[0-9a-f]{64}$", account_ref):
            raise LifecycleValidationError("account reference is invalid")
        if target_role not in {"customer", "staff", "manager"}:
            raise LifecycleValidationError("target role is invalid")
        guard_ref = lifecycle_target_guard_reference(
            target_uid=target_uid,
            project_id=self._project_id,
            environment=self._environment,
        )
        guard_reference = self._guard_reference(guard_ref)
        profile_reference = self._db.collection("users").document(target_uid)

        def operation(transaction: Any) -> tuple[LifecycleActionRecord, LifecycleTargetGuard] | None:
            profile_snapshot = self._snapshot(transaction, profile_reference)
            if not profile_snapshot.exists:
                raise PersistenceError("lifecycle recovery profile is missing")
            profile = _validate_disable_profile(profile_snapshot.to_dict() or {}, target_uid)
            if profile["role"] != target_role:
                raise PersistenceError("lifecycle recovery profile role is inconsistent")
            guard_snapshot = self._snapshot(transaction, guard_reference)
            if not guard_snapshot.exists:
                return None
            guard = validate_target_guard_document(guard_snapshot.to_dict() or {})
            if guard.guard_ref != guard_ref or guard.target_uid != target_uid:
                raise PersistenceError("lifecycle recovery guard binding is invalid")
            action_reference = self._action_reference(guard.action_ref)
            action_snapshot = self._snapshot(transaction, action_reference)
            if not action_snapshot.exists:
                raise PersistenceError("lifecycle recovery action is missing")
            action = validate_action_document(action_snapshot.to_dict() or {})
            if (
                action.target_uid != target_uid
                or action.account_ref != account_ref
                or action.target_role != target_role
                or guard.action_ref != action.action_ref
                or guard.operation != action.operation
                or guard.state != _guard_state_for_action(action.state)
                or guard.version < action.version
            ):
                raise PersistenceError("lifecycle recovery action and guard are inconsistent")
            if action.actor_uid != actor_uid:
                return None
            if action.state == "failed" and guard.state == "blocked":
                failed_from_state = {
                    "disable": {
                        2: "reserved",
                        3: "profile_inactivated",
                        4: "auth_disable_pending",
                    },
                    "reactivate": {
                        2: "reserved",
                        3: "auth_enable_pending",
                        4: "profile_activation_pending",
                    },
                    "reassign_department": {2: "reserved"},
                }[action.operation].get(action.version)
                if failed_from_state is None:
                    raise PersistenceError("failed lifecycle version is invalid")
                failure_event_ref = lifecycle_audit_event_reference(
                    action_ref=action.action_ref,
                    operation=action.operation,
                    from_state=failed_from_state,
                    to_state="failed",
                    result_code=action.result_code,
                    version=action.version,
                )
                failure_event_snapshot = self._snapshot(
                    transaction, self._audit_reference(failure_event_ref)
                )
                if not failure_event_snapshot.exists:
                    raise PersistenceError("failed lifecycle audit is missing")
                failure_event = validate_audit_document(
                    failure_event_snapshot.to_dict() or {}
                )
                if (
                    failure_event.event_ref != failure_event_ref
                    or failure_event.action_ref != action.action_ref
                    or failure_event.operation != action.operation
                    or failure_event.actor_uid != action.actor_uid
                    or failure_event.target_uid != action.target_uid
                    or failure_event.from_state != failed_from_state
                    or failure_event.to_state != "failed"
                    or failure_event.result_code != action.result_code
                    or failure_event.version != action.version
                ):
                    raise PersistenceError("failed lifecycle audit is inconsistent")
                return action, guard
            if action.state == "failed" or guard.state == "blocked":
                raise PersistenceError("lifecycle recovery terminal state is inconsistent")
            if action.operation == "disable":
                if action.state == "reserved" and profile["active"] is not True:
                    raise PersistenceError("reserved disable profile is inconsistent")
                if action.state in {"profile_inactivated", "auth_disable_pending"} and profile["active"] is not False:
                    raise PersistenceError("in-progress disable profile is inconsistent")
            elif action.operation == "reactivate" and profile["active"] is not False:
                if action.state != "completed":
                    raise PersistenceError("in-progress reactivation profile is inconsistent")
            elif action.operation == "reassign_department" and (
                action.target_role != "staff"
                or profile["active"] is not True
                or action.requested_department not in DEPARTMENT_IDS
            ):
                raise PersistenceError("reassignment recovery profile is inconsistent")
            return action, guard

        try:
            discovered = self._run_transaction(self._db, operation)
        except PersistenceError:
            raise
        except Exception as exc:
            raise PersistenceError("lifecycle recovery status lookup failed") from exc
        if discovered is None:
            return "none", None, None
        action, guard = discovered
        if action.state == "failed" and guard.state == "blocked":
            return "operator_required", None, None
        requested_department = (
            action.requested_department if action.operation == "reassign_department" else None
        )
        # Reuse the established read-only validator for audit and reactivation
        # lineage proof. This performs direct lookups only and never writes.
        try:
            validated, _ = self.recover_existing_action(
                actor_uid=actor_uid,
                target_uid=target_uid,
                account_ref=account_ref,
                target_role=target_role,
                operation=action.operation,
                requested_department=requested_department,
            )
        except Exception as exc:
            raise PersistenceError("lifecycle recovery status persistence is invalid") from exc
        if validated.state == "conflict":
            return "none", None, None
        if validated.state == "completed":
            return "completed", validated.operation, requested_department
        supported = {
            "disable": {"reserved", "profile_inactivated", "auth_disable_pending"},
            "reactivate": {"reserved", "auth_enable_pending", "profile_activation_pending"},
            "reassign_department": {"reserved"},
        }
        if validated.state not in supported[validated.operation]:
            raise PersistenceError("lifecycle recovery state is not projectable")
        return "recoverable", validated.operation, requested_department

    def find_completed_disable_action(
        self,
        *,
        target_uid: str,
        account_ref: str,
        target_role: str,
    ) -> LifecycleActionRecord:
        """Read the durable proof required before acquiring a guard for reactivation."""

        _require_uid(target_uid, "target UID")
        if not re.fullmatch(r"^acct_v1_[0-9a-f]{64}$", account_ref):
            raise LifecycleValidationError("account reference is invalid")
        guard_ref = lifecycle_target_guard_reference(
            target_uid=target_uid,
            project_id=self._project_id,
            environment=self._environment,
        )
        guard_reference = self._guard_reference(guard_ref)
        profile_reference = self._db.collection("users").document(target_uid)

        def operation(transaction: Any) -> LifecycleActionRecord:
            guard_snapshot = self._snapshot(transaction, guard_reference)
            profile_snapshot = self._snapshot(transaction, profile_reference)
            if not guard_snapshot.exists or not profile_snapshot.exists:
                raise LifecycleReactivationNotEligible("completed disable proof is missing")
            guard = validate_target_guard_document(guard_snapshot.to_dict() or {})
            profile = _validate_disable_profile(profile_snapshot.to_dict() or {}, target_uid)
            if guard.guard_ref != guard_ref or guard.target_uid != target_uid or guard.state != "inactive":
                raise LifecycleReactivationNotEligible("target guard is not reusable")
            if profile["active"] is not False or profile["role"] != target_role:
                raise LifecycleReactivationNotEligible("target profile is not reactivatable")
            owner_reference = self._action_reference(guard.action_ref)
            owner_snapshot = self._snapshot(transaction, owner_reference)
            if not owner_snapshot.exists:
                raise LifecycleReactivationNotEligible("completed disable action is missing")
            previous = validate_action_document(owner_snapshot.to_dict() or {})
            event_ref = lifecycle_audit_event_reference(
                action_ref=previous.action_ref,
                operation="disable",
                from_state="auth_disable_pending",
                to_state="completed",
                result_code="completed",
                version=previous.version,
            )
            event_snapshot = self._snapshot(transaction, self._audit_reference(event_ref))
            if not event_snapshot.exists:
                raise LifecycleReactivationNotEligible("completed disable audit is missing")
            event = validate_audit_document(event_snapshot.to_dict() or {})
            _validate_completed_disable_lineage(
                previous,
                event,
                target_uid=target_uid,
                account_ref=account_ref,
                target_role=target_role,
            )
            if guard.action_ref != previous.action_ref or guard.operation != "disable":
                raise LifecycleReactivationNotEligible("target guard lineage is invalid")
            return previous

        try:
            return self._run_transaction(self._db, operation)
        except (LifecycleReactivationNotEligible, LifecycleValidationError, PersistenceError):
            raise
        except Exception as exc:
            raise PersistenceError("reactivation proof lookup failed") from exc

    def reactivation_eligibility_reason(
        self,
        *,
        target_uid: str,
        account_ref: str,
        target_role: str,
    ) -> str | None:
        try:
            self.find_completed_disable_action(
                target_uid=target_uid,
                account_ref=account_ref,
                target_role=target_role,
            )
        except LifecycleReactivationNotEligible:
            return "pending_setup_activation_forbidden"
        except LifecycleStateConflict:
            return "lifecycle_conflict"
        return None

    def reserve_reactivation(self, record: LifecycleActionRecord) -> LifecycleActionRecord:
        if record.operation != "reactivate" or record.previous_action_ref is None:
            raise LifecycleValidationError("reactivation lineage is required")
        guard_ref = lifecycle_target_guard_reference(
            target_uid=record.target_uid,
            project_id=self._project_id,
            environment=self._environment,
        )
        action_reference = self._action_reference(record.action_ref)
        guard_reference = self._guard_reference(guard_ref)
        profile_reference = self._db.collection("users").document(record.target_uid)
        previous_reference = self._action_reference(record.previous_action_ref)

        def operation(transaction: Any) -> LifecycleActionRecord:
            action_snapshot = self._snapshot(transaction, action_reference)
            guard_snapshot = self._snapshot(transaction, guard_reference)
            profile_snapshot = self._snapshot(transaction, profile_reference)
            previous_snapshot = self._snapshot(transaction, previous_reference)
            existing = (
                validate_action_document(action_snapshot.to_dict() or {})
                if action_snapshot.exists
                else None
            )
            guard = (
                validate_target_guard_document(guard_snapshot.to_dict() or {})
                if guard_snapshot.exists
                else None
            )
            if not profile_snapshot.exists or not previous_snapshot.exists:
                raise LifecycleReactivationNotEligible("completed disable proof is missing")
            profile = _validate_disable_profile(profile_snapshot.to_dict() or {}, record.target_uid)
            previous = validate_action_document(previous_snapshot.to_dict() or {})
            previous_event_ref = lifecycle_audit_event_reference(
                action_ref=previous.action_ref,
                operation="disable",
                from_state="auth_disable_pending",
                to_state="completed",
                result_code="completed",
                version=previous.version,
            )
            previous_event_snapshot = self._snapshot(transaction, self._audit_reference(previous_event_ref))
            if not previous_event_snapshot.exists:
                raise LifecycleReactivationNotEligible("completed disable proof is missing")
            previous_event = validate_audit_document(previous_event_snapshot.to_dict() or {})
            _validate_completed_disable_lineage(
                previous,
                previous_event,
                target_uid=record.target_uid,
                account_ref=record.account_ref or "",
                target_role=record.target_role,
            )
            if profile["role"] != record.target_role:
                raise LifecycleReactivationNotEligible("target profile is not reactivatable")
            if existing is not None:
                if not _same_request(existing, record):
                    raise LifecycleIdempotencyConflict("idempotency request conflict")
                if guard is None or guard.action_ref != existing.action_ref or guard.operation != existing.operation:
                    raise PersistenceError("reactivation guard ownership mismatch")
                expected_guard_state = _guard_state_for_action(existing.state)
                if guard.state != expected_guard_state:
                    raise PersistenceError("reactivation guard state mismatch")
                if existing.previous_action_ref != previous.action_ref:
                    raise LifecycleReactivationNotEligible("reactivation lineage mismatch")
                if existing.state == "completed":
                    final_event_ref = lifecycle_audit_event_reference(
                        action_ref=existing.action_ref,
                        operation="reactivate",
                        from_state="profile_activation_pending",
                        to_state="completed",
                        result_code="completed",
                        version=existing.version,
                    )
                    final_event_snapshot = self._snapshot(transaction, self._audit_reference(final_event_ref))
                    if not final_event_snapshot.exists:
                        raise PersistenceError("completed reactivation audit is missing")
                    final_event = validate_audit_document(final_event_snapshot.to_dict() or {})
                    expected_event = LifecycleAuditEvent(
                        event_ref=final_event_ref,
                        action_ref=existing.action_ref,
                        operation="reactivate",
                        actor_uid=existing.actor_uid,
                        target_uid=existing.target_uid,
                        from_state="profile_activation_pending",
                        to_state="completed",
                        result_code="completed",
                        version=existing.version,
                        created_at=final_event.created_at,
                    )
                    if final_event.to_document() != expected_event.to_document():
                        raise LifecycleConflictError("immutable audit event conflict")
                    if profile["active"] is not True or guard.state != "inactive":
                        raise LifecycleStateConflict("completed reactivation is inconsistent")
                elif profile["active"] is not False or guard.state != "active":
                    raise LifecycleStateConflict("reactivation recovery is inconsistent")
                return existing
            if profile["active"] is not False:
                raise LifecycleReactivationNotEligible("target profile is not reactivatable")
            if guard is None or guard.state != "inactive":
                raise LifecycleReactivationNotEligible("target guard is not reusable")
            if guard.action_ref != previous.action_ref or guard.operation != "disable":
                raise LifecycleReactivationNotEligible("target guard lineage is invalid")
            if guard.version >= MAX_ACTION_VERSION:
                raise LifecycleStateConflict("target guard version exhausted")
            replacement = replace(
                guard,
                action_ref=record.action_ref,
                operation="reactivate",
                state="active",
                version=guard.version + 1,
                updated_at=record.updated_at,
            )
            transaction.create(action_reference, record.to_document())
            transaction.update(guard_reference, replacement.to_document())
            return record

        try:
            return self._run_transaction(self._db, operation)
        except (LifecycleConflictError, LifecycleValidationError, PersistenceError):
            raise
        except Exception as exc:
            raise PersistenceError("reactivation reservation failed") from exc

    def activate_profile(
        self,
        action_ref: str,
        *,
        expected_version: int,
        now: datetime,
    ) -> LifecycleActionRecord:
        """Atomically activate the proven target and finalize reactivation."""

        action_reference = self._action_reference(action_ref)

        def operation(transaction: Any) -> LifecycleActionRecord:
            action_snapshot = self._snapshot(transaction, action_reference)
            if not action_snapshot.exists:
                raise LifecycleConflictError("lifecycle action not found")
            current = validate_action_document(action_snapshot.to_dict() or {})
            guard_ref = lifecycle_target_guard_reference(
                target_uid=current.target_uid,
                project_id=self._project_id,
                environment=self._environment,
            )
            guard_reference = self._guard_reference(guard_ref)
            profile_reference = self._db.collection("users").document(current.target_uid)
            guard_snapshot = self._snapshot(transaction, guard_reference)
            profile_snapshot = self._snapshot(transaction, profile_reference)
            if not guard_snapshot.exists or not profile_snapshot.exists:
                raise PersistenceError("reactivation target persistence is incomplete")
            guard = validate_target_guard_document(guard_snapshot.to_dict() or {})
            profile = _validate_disable_profile(profile_snapshot.to_dict() or {}, current.target_uid)
            if current.previous_action_ref is None:
                raise LifecycleReactivationNotEligible("reactivation lineage is missing")
            previous_reference = self._action_reference(current.previous_action_ref)
            previous_snapshot = self._snapshot(transaction, previous_reference)
            if not previous_snapshot.exists:
                raise LifecycleReactivationNotEligible("completed disable action is missing")
            previous = validate_action_document(previous_snapshot.to_dict() or {})
            previous_event_ref = lifecycle_audit_event_reference(
                action_ref=previous.action_ref,
                operation="disable",
                from_state="auth_disable_pending",
                to_state="completed",
                result_code="completed",
                version=previous.version,
            )
            previous_event_snapshot = self._snapshot(transaction, self._audit_reference(previous_event_ref))
            if not previous_event_snapshot.exists:
                raise LifecycleReactivationNotEligible("completed disable audit is missing")
            previous_event = validate_audit_document(previous_event_snapshot.to_dict() or {})
            _validate_completed_disable_lineage(
                previous,
                previous_event,
                target_uid=current.target_uid,
                account_ref=current.account_ref or "",
                target_role=current.target_role,
            )
            if (
                current.action_ref != action_ref
                or current.operation != "reactivate"
                or current.state != "profile_activation_pending"
                or current.version != expected_version
                or guard.guard_ref != guard_ref
                or guard.action_ref != current.action_ref
                or guard.operation != "reactivate"
                or guard.state != "active"
                or guard.target_uid != current.target_uid
                or profile["role"] != current.target_role
                or profile["active"] is not False
            ):
                raise LifecycleStateConflict("reactivation activation precondition failed")
            timestamp = _aware(now, "updatedAt")
            if current.version >= MAX_ACTION_VERSION or guard.version >= MAX_ACTION_VERSION:
                raise LifecycleStateConflict("lifecycle version exhausted")
            updated = replace(
                current,
                state="completed",
                result_code="completed",
                updated_at=timestamp,
                version=current.version + 1,
                completed_at=timestamp,
            )
            event_ref = lifecycle_audit_event_reference(
                action_ref=current.action_ref,
                operation="reactivate",
                from_state="profile_activation_pending",
                to_state="completed",
                result_code="completed",
                version=updated.version,
            )
            event_reference = self._audit_reference(event_ref)
            event_snapshot = self._snapshot(transaction, event_reference)
            event = LifecycleAuditEvent(
                event_ref=event_ref,
                action_ref=current.action_ref,
                operation="reactivate",
                actor_uid=current.actor_uid,
                target_uid=current.target_uid,
                from_state="profile_activation_pending",
                to_state="completed",
                result_code="completed",
                version=updated.version,
                created_at=timestamp,
            )
            if event_snapshot.exists:
                if validate_audit_document(event_snapshot.to_dict() or {}).to_document() != event.to_document():
                    raise LifecycleConflictError("immutable audit event conflict")
            else:
                transaction.create(event_reference, event.to_document())
            updated_guard = replace(
                guard,
                state="inactive",
                version=guard.version + 1,
                updated_at=timestamp,
            )
            transaction.update(profile_reference, {"active": True, "updatedAt": timestamp})
            transaction.update(action_reference, updated.to_document())
            transaction.update(guard_reference, updated_guard.to_document())
            return updated

        try:
            return self._run_transaction(self._db, operation)
        except (LifecycleConflictError, LifecycleValidationError, PersistenceError):
            raise
        except Exception as exc:
            raise PersistenceError("reactivation profile transaction failed") from exc

    def inactivate_profile(
        self,
        action_ref: str,
        *,
        now: datetime,
    ) -> LifecycleActionRecord:
        """Atomically inactivate the target profile and record the phase."""

        action_reference = self._action_reference(action_ref)

        def operation(transaction: Any) -> LifecycleActionRecord:
            action_snapshot = self._snapshot(transaction, action_reference)
            if not action_snapshot.exists:
                raise LifecycleConflictError("lifecycle action not found")
            current = validate_action_document(action_snapshot.to_dict() or {})
            if current.action_ref != action_ref or current.operation != "disable":
                raise PersistenceError("lifecycle disable action mismatch")
            guard_ref = lifecycle_target_guard_reference(
                target_uid=current.target_uid,
                project_id=self._project_id,
                environment=self._environment,
            )
            guard_reference = self._guard_reference(guard_ref)
            profile_reference = self._db.collection("users").document(current.target_uid)
            guard_snapshot = self._snapshot(transaction, guard_reference)
            profile_snapshot = self._snapshot(transaction, profile_reference)
            if not guard_snapshot.exists or not profile_snapshot.exists:
                raise PersistenceError("lifecycle target persistence is incomplete")
            guard = validate_target_guard_document(guard_snapshot.to_dict() or {})
            profile = _validate_disable_profile(
                profile_snapshot.to_dict() or {}, current.target_uid
            )
            if (
                guard.guard_ref != guard_ref
                or guard.target_uid != current.target_uid
                or guard.action_ref != current.action_ref
                or guard.operation != current.operation
                or guard.state != _guard_state_for_action(current.state)
                or current.target_role == "admin"
                or current.target_role != profile["role"]
            ):
                raise PersistenceError("lifecycle target ownership is invalid")
            if current.state in {"profile_inactivated", "auth_disable_pending", "completed"}:
                if profile["active"] is not False:
                    raise LifecycleStateConflict("lifecycle profile state is inconsistent")
                if current.state == "profile_inactivated" and current.result_code != "profile_inactivated":
                    raise PersistenceError("lifecycle profile transition is invalid")
                if current.state in {"profile_inactivated", "auth_disable_pending", "completed"}:
                    event_ref = lifecycle_audit_event_reference(
                        action_ref=current.action_ref,
                        operation=current.operation,
                        from_state="reserved",
                        result_code="profile_inactivated",
                        to_state="profile_inactivated",
                        version=2,
                    )
                    audit_snapshot = self._snapshot(transaction, self._audit_reference(event_ref))
                    if not audit_snapshot.exists:
                        raise PersistenceError("lifecycle profile audit is missing")
                    existing_event = validate_audit_document(audit_snapshot.to_dict() or {})
                    expected_event = LifecycleAuditEvent(
                        event_ref=event_ref,
                        action_ref=current.action_ref,
                        operation=current.operation,
                        actor_uid=current.actor_uid,
                        target_uid=current.target_uid,
                        from_state="reserved",
                        to_state="profile_inactivated",
                        result_code="profile_inactivated",
                        version=2,
                        created_at=existing_event.created_at,
                    )
                    if existing_event.to_document() != expected_event.to_document():
                        raise LifecycleConflictError("immutable audit event conflict")
                return current
            if (
                current.state != "reserved"
                or current.version != 1
                or current.result_code is not None
                or profile["active"] is not True
            ):
                raise LifecycleStateConflict("lifecycle profile state is not disableable")
            timestamp = _aware(now, "updatedAt")
            if guard.version >= MAX_ACTION_VERSION or current.version >= MAX_ACTION_VERSION:
                raise LifecycleStateConflict("lifecycle version exhausted")
            updated = replace(
                current,
                state="profile_inactivated",
                result_code="profile_inactivated",
                updated_at=timestamp,
                version=current.version + 1,
            )
            event_ref = lifecycle_audit_event_reference(
                action_ref=current.action_ref,
                operation=current.operation,
                from_state="reserved",
                result_code="profile_inactivated",
                to_state="profile_inactivated",
                version=updated.version,
            )
            audit_reference = self._audit_reference(event_ref)
            audit_snapshot = self._snapshot(transaction, audit_reference)
            event = LifecycleAuditEvent(
                event_ref=event_ref,
                action_ref=current.action_ref,
                operation=current.operation,
                actor_uid=current.actor_uid,
                target_uid=current.target_uid,
                from_state="reserved",
                to_state="profile_inactivated",
                result_code="profile_inactivated",
                version=updated.version,
                created_at=timestamp,
            )
            if audit_snapshot.exists:
                if validate_audit_document(audit_snapshot.to_dict() or {}).to_document() != event.to_document():
                    raise LifecycleConflictError("immutable audit event conflict")
            else:
                transaction.create(audit_reference, event.to_document())
            updated_guard = replace(
                guard,
                state="active",
                version=guard.version + 1,
                updated_at=timestamp,
            )
            transaction.update(profile_reference, {"active": False, "updatedAt": timestamp})
            transaction.update(action_reference, updated.to_document())
            transaction.update(guard_reference, updated_guard.to_document())
            return updated

        try:
            return self._run_transaction(self._db, operation)
        except (LifecycleConflictError, LifecycleValidationError, PersistenceError):
            raise
        except Exception as exc:
            raise PersistenceError("lifecycle profile transaction failed") from exc

    def transition(
        self,
        action_ref: str,
        *,
        expected_version: int,
        to_state: LifecycleState,
        result_code: str | None,
        now: datetime,
    ) -> LifecycleActionRecord:
        action_reference = self._action_reference(action_ref)

        def operation(transaction: Any) -> LifecycleActionRecord:
            action_snapshot = self._snapshot(transaction, action_reference)
            if not action_snapshot.exists:
                raise LifecycleConflictError("lifecycle action not found")
            current = validate_action_document(action_snapshot.to_dict() or {})
            guard_ref = lifecycle_target_guard_reference(
                target_uid=current.target_uid,
                project_id=self._project_id,
                environment=self._environment,
            )
            guard_reference = self._guard_reference(guard_ref)
            guard_snapshot = self._snapshot(transaction, guard_reference)
            if not guard_snapshot.exists:
                raise PersistenceError("lifecycle target guard missing")
            guard = validate_target_guard_document(guard_snapshot.to_dict() or {})
            if (
                current.action_ref != action_ref
                or guard.guard_ref != guard_ref
                or guard.target_uid != current.target_uid
                or guard.action_ref != current.action_ref
                or guard.operation != current.operation
                or guard.state != _guard_state_for_action(current.state)
            ):
                raise PersistenceError("lifecycle target guard ownership mismatch")
            if current.version != expected_version:
                raise LifecycleStateConflict("stale lifecycle action version")
            if current.state in {"conflict", "failed"}:
                raise LifecycleStateConflict("terminal lifecycle action cannot transition")
            if to_state not in ALLOWED_OPERATION_TRANSITIONS[current.operation][current.state]:
                raise LifecycleStateConflict("lifecycle transition is not allowed")
            timestamp = _aware(now, "updatedAt")
            if to_state == current.state:
                if result_code != current.result_code:
                    raise LifecycleStateConflict("same-state result conflict")
                return current
            new_version = current.version + 1
            if new_version > MAX_ACTION_VERSION:
                raise LifecycleStateConflict("lifecycle action version exhausted")
            if guard.version >= MAX_ACTION_VERSION:
                raise LifecycleStateConflict("target guard version exhausted")
            completed_at = current.completed_at
            if to_state == "completed" and completed_at is None:
                completed_at = timestamp
            updated = replace(
                current,
                state=to_state,
                result_code=result_code,
                updated_at=timestamp,
                version=new_version,
                completed_at=completed_at,
            )
            event_ref = lifecycle_audit_event_reference(
                action_ref=current.action_ref,
                operation=current.operation,
                from_state=current.state,
                result_code=result_code,
                to_state=to_state,
                version=new_version,
            )
            event_reference = self._audit_reference(event_ref)
            audit_snapshot = self._snapshot(transaction, event_reference)
            event = LifecycleAuditEvent(
                event_ref=event_ref,
                action_ref=current.action_ref,
                operation=current.operation,
                actor_uid=current.actor_uid,
                target_uid=current.target_uid,
                from_state=current.state,
                to_state=to_state,
                result_code=result_code,
                version=new_version,
                created_at=timestamp,
            )
            if audit_snapshot.exists:
                if validate_audit_document(audit_snapshot.to_dict() or {}).to_document() != event.to_document():
                    raise LifecycleConflictError("immutable audit event conflict")
            else:
                transaction.create(event_reference, event.to_document())
            guard_state = _guard_state_for_action(to_state)
            updated_guard = replace(
                guard,
                state=guard_state,
                version=guard.version + 1,
                updated_at=timestamp,
            )
            transaction.update(action_reference, updated.to_document())
            transaction.update(guard_reference, updated_guard.to_document())
            return updated

        try:
            return self._run_transaction(self._db, operation)
        except (LifecycleConflictError, LifecycleValidationError, PersistenceError):
            raise
        except Exception as exc:
            raise PersistenceError("lifecycle action transition failed") from exc

    def reassign_department(
        self,
        action_ref: str,
        *,
        expected_version: int,
        now: datetime,
    ) -> LifecycleActionRecord:
        """Atomically check assigned work and complete Staff reassignment."""

        action_reference = self._action_reference(action_ref)

        def operation(transaction: Any) -> LifecycleActionRecord:
            action_snapshot = self._snapshot(transaction, action_reference)
            if not action_snapshot.exists:
                raise LifecycleStateConflict("lifecycle action not found")
            current = validate_action_document(action_snapshot.to_dict() or {})
            if current.operation != "reassign_department" or current.target_role != "staff":
                raise PersistenceError("reassignment action mismatch")
            guard_ref = lifecycle_target_guard_reference(
                target_uid=current.target_uid,
                project_id=self._project_id,
                environment=self._environment,
            )
            guard_reference = self._guard_reference(guard_ref)
            profile_reference = self._db.collection("users").document(current.target_uid)
            ticket_query = self._db.collection("tickets").limit(MAX_REASSIGNMENT_TICKET_SCAN + 1)
            transition_version = current.version + 1 if current.state == "reserved" else current.version
            final_event_ref = lifecycle_audit_event_reference(
                action_ref=current.action_ref,
                operation="reassign_department",
                from_state="reserved",
                to_state="completed",
                result_code="completed",
                version=transition_version,
            )
            conflict_event_ref = lifecycle_audit_event_reference(
                action_ref=current.action_ref,
                operation="reassign_department",
                from_state="reserved",
                to_state="conflict",
                result_code="assigned_unresolved_work",
                version=transition_version,
            )
            guard_snapshot = self._snapshot(transaction, guard_reference)
            profile_snapshot = self._snapshot(transaction, profile_reference)
            ticket_snapshots = list(transaction.get(ticket_query))
            final_event_snapshot = self._snapshot(
                transaction, self._audit_reference(final_event_ref)
            )
            conflict_event_snapshot = self._snapshot(
                transaction, self._audit_reference(conflict_event_ref)
            )
            # All reads, including the bounded work scan and both deterministic
            # audit destinations, precede every write in this transaction.
            if not guard_snapshot.exists or not profile_snapshot.exists:
                raise PersistenceError("reassignment target persistence is incomplete")
            guard = validate_target_guard_document(guard_snapshot.to_dict() or {})
            profile = _validate_disable_profile(profile_snapshot.to_dict() or {}, current.target_uid)
            if current.state == "completed":
                if (
                    current.account_ref is None
                    or current.requested_department not in DEPARTMENT_IDS
                    or profile["departmentId"] != current.requested_department
                    or guard.guard_ref != guard_ref
                    or guard.target_uid != current.target_uid
                    or guard.action_ref != current.action_ref
                    or guard.operation != current.operation
                    or guard.state != "inactive"
                ):
                    raise LifecycleStateConflict("completed reassignment is inconsistent")
                if not final_event_snapshot.exists:
                    raise PersistenceError("reassignment audit is missing")
                validate_audit_document(final_event_snapshot.to_dict() or {})
                return current
            if (
                current.action_ref != action_ref
                or current.version != expected_version
                or current.account_ref is None
                or current.requested_department not in DEPARTMENT_IDS
                or current.target_role != "staff"
                or profile["role"] != "staff"
                or profile["active"] is not True
                or profile["departmentId"] not in DEPARTMENT_IDS
                or guard.guard_ref != guard_ref
                or guard.target_uid != current.target_uid
                or guard.action_ref != current.action_ref
                or guard.operation != current.operation
                or guard.state != "active"
            ):
                raise LifecycleStateConflict("reassignment precondition failed")
            if current.state != "reserved" or current.result_code is not None:
                raise LifecycleStateConflict("reassignment action is not recoverable")
            assigned_work = False
            for snapshot in ticket_snapshots:
                ticket = snapshot.to_dict()
                if not isinstance(ticket, dict):
                    raise PersistenceError("ticket assignment data is malformed")
                status = ticket.get("status")
                assigned_uid = ticket.get("assignedStaffId")
                if status not in {"submitted", "triaged", "in_progress", "awaiting_customer", "resolved", "closed"}:
                    raise PersistenceError("ticket assignment data is malformed")
                if assigned_uid is not None and (not isinstance(assigned_uid, str) or not _UID_PATTERN.fullmatch(assigned_uid)):
                    raise PersistenceError("ticket assignment data is malformed")
                if status in {"submitted", "triaged", "in_progress", "awaiting_customer"} and assigned_uid == current.target_uid:
                    assigned_work = True
            if len(ticket_snapshots) > MAX_REASSIGNMENT_TICKET_SCAN:
                raise PersistenceError("reassignment ticket scan is incomplete")
            timestamp = _aware(now, "updatedAt")
            if current.version >= MAX_ACTION_VERSION or guard.version >= MAX_ACTION_VERSION:
                raise LifecycleStateConflict("lifecycle version exhausted")
            next_state: LifecycleState = "conflict" if assigned_work else "completed"
            result_code = "assigned_unresolved_work" if assigned_work else "completed"
            updated = replace(
                current,
                state=next_state,
                result_code=result_code,
                updated_at=timestamp,
                version=current.version + 1,
                completed_at=timestamp if next_state == "completed" else None,
            )
            event_ref = conflict_event_ref if assigned_work else final_event_ref
            event_snapshot = conflict_event_snapshot if assigned_work else final_event_snapshot
            event = LifecycleAuditEvent(
                event_ref=event_ref,
                action_ref=current.action_ref,
                operation=current.operation,
                actor_uid=current.actor_uid,
                target_uid=current.target_uid,
                from_state="reserved",
                to_state=next_state,
                result_code=result_code,
                version=updated.version,
                created_at=timestamp,
            )
            if event_snapshot.exists:
                if validate_audit_document(event_snapshot.to_dict() or {}).to_document() != event.to_document():
                    raise LifecycleConflictError("immutable audit event conflict")
            else:
                transaction.create(self._audit_reference(event_ref), event.to_document())
            updated_guard = replace(
                guard,
                state="inactive",
                version=guard.version + 1,
                updated_at=timestamp,
            )
            if not assigned_work:
                transaction.update(profile_reference, {"departmentId": current.requested_department, "updatedAt": timestamp})
            transaction.update(action_reference, updated.to_document())
            transaction.update(guard_reference, updated_guard.to_document())
            return updated

        try:
            return self._run_transaction(self._db, operation)
        except (LifecycleConflictError, LifecycleValidationError, PersistenceError):
            raise
        except Exception as exc:
            raise PersistenceError("department reassignment transaction failed") from exc

    def reassignment_eligibility_reason(self, *, target_uid: str) -> str | None:
        """Return only a safe advisory reason for an existing target guard."""

        guard_ref = lifecycle_target_guard_reference(
            target_uid=target_uid,
            project_id=self._project_id,
            environment=self._environment,
        )
        guard_reference = self._guard_reference(guard_ref)

        def operation(transaction: Any) -> str | None:
            snapshot = self._snapshot(transaction, guard_reference)
            if not snapshot.exists:
                return None
            guard = validate_target_guard_document(snapshot.to_dict() or {})
            if guard.guard_ref != guard_ref or guard.target_uid != target_uid:
                raise PersistenceError("lifecycle target guard ownership mismatch")
            owner_snapshot = self._snapshot(
                transaction, self._action_reference(guard.action_ref)
            )
            if not owner_snapshot.exists:
                raise PersistenceError("lifecycle target guard owner is missing")
            owner = validate_action_document(owner_snapshot.to_dict() or {})
            if (
                owner.action_ref != guard.action_ref
                or owner.target_uid != target_uid
                or owner.operation != guard.operation
                or _guard_state_for_action(owner.state) != guard.state
            ):
                raise PersistenceError("lifecycle target guard owner is inconsistent")
            if guard.state in {"active", "blocked"}:
                return "lifecycle_conflict"
            return None

        try:
            return self._run_transaction(self._db, operation)
        except (LifecycleValidationError, PersistenceError):
            raise
        except Exception as exc:
            raise PersistenceError("reassignment eligibility lookup failed") from exc

    def append_audit(self, event: LifecycleAuditEvent) -> LifecycleAuditEvent:
        reference = self._audit_reference(event.event_ref)

        def operation(transaction: Any) -> LifecycleAuditEvent:
            snapshot = self._snapshot(transaction, reference)
            if snapshot.exists:
                existing = validate_audit_document(snapshot.to_dict() or {})
                if existing.to_document() != event.to_document():
                    raise LifecycleConflictError("immutable audit event conflict")
                return existing
            transaction.create(reference, event.to_document())
            return event

        try:
            return self._run_transaction(self._db, operation)
        except (LifecycleConflictError, LifecycleValidationError, PersistenceError):
            raise
        except Exception as exc:
            raise PersistenceError("lifecycle audit append failed") from exc


FirestoreLifecycleRepository = FirebaseLifecycleRepository


class LifecycleRepository(Protocol):
    def reserve(self, record: LifecycleActionRecord) -> LifecycleActionRecord: ...

    def get_action(self, action_ref: str) -> LifecycleActionRecord | None: ...

    def transition(
        self,
        action_ref: str,
        *,
        expected_version: int,
        to_state: LifecycleState,
        result_code: str | None,
        now: datetime,
    ) -> LifecycleActionRecord: ...

    def append_audit(self, event: LifecycleAuditEvent) -> LifecycleAuditEvent: ...


class InMemoryLifecycleRepository:
    """Pure fake repository for contract tests; never used by runtime wiring."""

    def __init__(self) -> None:
        self.records: dict[str, LifecycleActionRecord] = {}
        self.audit_events: dict[str, LifecycleAuditEvent] = {}
        self._actor_key_index: dict[tuple[str, str], str] = {}
        self._active_target_actions: dict[str, str] = {}

    def get_action(self, action_ref: str) -> LifecycleActionRecord | None:
        return self.records.get(action_ref)

    def reserve(self, record: LifecycleActionRecord) -> LifecycleActionRecord:
        existing = self.records.get(record.action_ref)
        if existing is not None:
            if not _same_request(existing, record):
                raise LifecycleIdempotencyConflict("idempotency request conflict")
            return existing

        key = (record.actor_uid, record.idempotency_key_hash)
        bound_action = self._actor_key_index.get(key)
        if bound_action is not None and bound_action != record.action_ref:
            raise LifecycleIdempotencyConflict("idempotency key conflict")

        active_action = self._active_target_actions.get(record.target_uid)
        if active_action is not None and active_action != record.action_ref:
            raise LifecycleStateConflict("target has an active lifecycle operation")

        self.records[record.action_ref] = record
        self._actor_key_index[key] = record.action_ref
        if record.state not in {"completed", "conflict", "failed"}:
            self._active_target_actions[record.target_uid] = record.action_ref
        return record

    def transition(
        self,
        action_ref: str,
        *,
        expected_version: int,
        to_state: LifecycleState,
        result_code: str | None,
        now: datetime,
    ) -> LifecycleActionRecord:
        current = self.records.get(action_ref)
        if current is None:
            raise LifecycleConflictError("lifecycle action not found")
        if current.version != expected_version:
            raise LifecycleStateConflict("stale lifecycle action version")
        if current.state in {"conflict", "failed"}:
            raise LifecycleStateConflict("terminal lifecycle action cannot transition")
        if to_state not in ALLOWED_OPERATION_TRANSITIONS[current.operation][current.state]:
            raise LifecycleStateConflict("lifecycle transition is not allowed")
        if to_state == current.state:
            return current
        timestamp = _aware(now, "updatedAt")
        completed_at = current.completed_at
        if to_state == "completed" and completed_at is None:
            completed_at = timestamp
        updated = replace(
            current,
            state=to_state,
            result_code=result_code,
            updated_at=timestamp,
            version=current.version + 1,
            completed_at=completed_at,
        )
        self.records[action_ref] = updated
        if to_state in {"completed", "conflict", "failed"}:
            self._active_target_actions.pop(current.target_uid, None)
        else:
            self._active_target_actions[current.target_uid] = action_ref
        return updated

    def append_audit(self, event: LifecycleAuditEvent) -> LifecycleAuditEvent:
        existing = self.audit_events.get(event.event_ref)
        if existing is not None:
            if existing.to_document() != event.to_document():
                raise LifecycleConflictError("immutable audit event conflict")
            return existing
        self.audit_events[event.event_ref] = event
        return event


def _same_request(left: LifecycleActionRecord, right: LifecycleActionRecord) -> bool:
    return (
        left.operation == right.operation
        and left.actor_uid == right.actor_uid
        and left.target_uid == right.target_uid
        and left.idempotency_key_hash == right.idempotency_key_hash
        and left.request_fingerprint == right.request_fingerprint
        and left.target_role == right.target_role
        and left.requested_department == right.requested_department
        and left.account_ref == right.account_ref
        and left.previous_action_ref == right.previous_action_ref
    )


class LifecycleActionService:
    """Validation and recovery coordinator for future trusted workflows."""

    def __init__(
        self,
        repository: LifecycleRepository,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def reserve(
        self,
        *,
        actor_uid: str,
        target_uid: str,
        target_role: str,
        operation: str,
        idempotency_key: str,
        requested_department: str | None = None,
        account_ref: str | None = None,
        previous_action_ref: str | None = None,
    ) -> LifecycleActionRecord:
        op = _require_operation(operation)
        if not isinstance(target_role, str) or target_role not in {"customer", "staff", "manager", "admin"}:
            raise LifecycleValidationError("target role is invalid")
        actor = _require_uid(actor_uid, "actor UID")
        target = _require_uid(target_uid, "target UID")
        if actor == target:
            raise LifecycleValidationError("actor and target must differ")
        normalized_key = normalize_idempotency_key(idempotency_key)
        action_ref = lifecycle_action_reference(
            actor_uid=actor,
            target_uid=target,
            idempotency_key=normalized_key,
            operation=op,
        )
        request_fingerprint = lifecycle_request_fingerprint(
            target_uid=target,
            operation=op,
            requested_department=requested_department,
        )
        if account_ref is not None and (
            not isinstance(account_ref, str)
            or not re.fullmatch(r"^acct_v1_[0-9a-f]{64}$", account_ref)
        ):
            raise LifecycleValidationError("account reference is invalid")
        timestamp = _aware(self._clock(), "createdAt")
        record = LifecycleActionRecord(
            operation=op,
            actor_uid=actor,
            target_uid=target,
            action_ref=action_ref,
            idempotency_key_hash=_sha256({"idempotencyKey": normalized_key}),
            request_fingerprint=request_fingerprint,
            state="reserved",
            result_code=None,
            target_role=target_role,  # type: ignore[arg-type]
            account_ref=account_ref,
            requested_department=requested_department,
            created_at=timestamp,
            updated_at=timestamp,
            previous_action_ref=previous_action_ref,
        )
        return self._repository.reserve(record)

    def transition(
        self,
        action_ref: str,
        *,
        expected_version: int,
        to_state: LifecycleState,
        result_code: str | None = None,
    ) -> LifecycleActionRecord:
        return self._repository.transition(
            action_ref,
            expected_version=expected_version,
            to_state=to_state,
            result_code=result_code,
            now=_aware(self._clock(), "updatedAt"),
        )

    def append_transition_audit(
        self,
        record: LifecycleActionRecord,
        *,
        from_state: LifecycleState,
    ) -> LifecycleAuditEvent:
        event_ref = lifecycle_audit_event_reference(
            action_ref=record.action_ref,
            from_state=from_state,
            operation=record.operation,
            result_code=record.result_code,
            to_state=record.state,
            version=record.version,
        )
        event = LifecycleAuditEvent(
            event_ref=event_ref,
            action_ref=record.action_ref,
            operation=record.operation,
            actor_uid=record.actor_uid,
            target_uid=record.target_uid,
            from_state=from_state,
            to_state=record.state,
            result_code=record.result_code,
            version=record.version,
            created_at=_aware(self._clock(), "createdAt"),
        )
        return self._repository.append_audit(event)
