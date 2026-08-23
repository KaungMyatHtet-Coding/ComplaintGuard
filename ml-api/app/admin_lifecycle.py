"""Trusted, backend-only account-lifecycle coordination foundation.

This module deliberately has no HTTP route, Firebase adapter, import-time
write, or profile/Auth mutation.  It provides the validated action and audit
contracts future trusted lifecycle workflows can use.
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


def _guard_state_for_action(
    state: LifecycleState,
) -> Literal["active", "inactive", "blocked"]:
    if state == "failed":
        return "blocked"
    if state in {"completed", "conflict"}:
        return "inactive"
    return "active"

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
    if not isinstance(value, datetime) or value.tzinfo is None:
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
    required = _ACTION_FIELDS - {"accountRef", "requestedDepartment", "completedAt"}
    if set(document) - _ACTION_FIELDS or not required <= set(document):
        raise LifecycleValidationError("lifecycle action fields are invalid")
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
