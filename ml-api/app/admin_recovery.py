"""Trusted continuation of existing Admin lifecycle actions only."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Protocol

from app.admin_auth import AdminPrincipal
from app.admin_directory import AdminDirectoryRow, validate_account_reference
from app.admin_disable import AdminDisableService
from app.admin_lifecycle import (
    LifecycleActionRecord,
    LifecycleOperation,
    LifecycleStateConflict,
    LifecycleTargetGuard,
    LifecycleValidationError,
)
from app.admin_reactivate import (
    AdminReactivateService,
    FirebaseAdminReactivationBackend,
)
from app.admin_reassign import AdminReassignService
from app.schemas import AdminLifecycleRecoveryResponse
from app.ticketing import DEPARTMENT_IDS


class RecoveryLifecycleConflict(RuntimeError):
    """An existing conflict action is returned as a safe conflict."""


class RecoveryAssignedWork(RuntimeError):
    """An existing reassignment conflict is safe to report as work-blocked."""


class AdminLifecycleRecoveryBackend(Protocol):
    def resolve_target(self, account_ref: str) -> tuple[str, AdminDirectoryRow]: ...

    def recover_existing_action(
        self,
        *,
        actor_uid: str,
        target_uid: str,
        account_ref: str,
        target_role: str,
        operation: LifecycleOperation,
        requested_department: str | None = None,
    ) -> tuple[LifecycleActionRecord, LifecycleTargetGuard]: ...

    def inactivate_profile(self, action_ref: str, *, now: datetime) -> LifecycleActionRecord: ...

    def transition(
        self,
        action_ref: str,
        *,
        expected_version: int,
        to_state: object,
        result_code: str | None,
        now: datetime,
    ) -> LifecycleActionRecord: ...

    def disable_auth_identity(self, target_uid: str) -> None: ...

    def revoke_refresh_tokens(self, target_uid: str) -> None: ...

    def activate_profile(
        self, action_ref: str, *, expected_version: int, now: datetime
    ) -> LifecycleActionRecord: ...

    def enable_auth_identity(self, target_uid: str) -> None: ...

    def reassign_department(
        self, action_ref: str, *, expected_version: int, now: datetime
    ) -> LifecycleActionRecord: ...


class AdminLifecycleRecoveryService:
    def __init__(
        self,
        backend: AdminLifecycleRecoveryBackend,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._backend = backend
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def recover(
        self,
        actor: AdminPrincipal,
        *,
        account_ref: str,
        operation: LifecycleOperation,
        department_id: str | None = None,
    ) -> AdminLifecycleRecoveryResponse:
        validate_account_reference(account_ref)
        if operation not in {"disable", "reactivate", "reassign_department"}:
            raise LifecycleValidationError("recovery operation is invalid")
        if operation == "reassign_department" and department_id not in DEPARTMENT_IDS:
            raise LifecycleValidationError("recovery department is invalid")
        if operation != "reassign_department" and department_id is not None:
            raise LifecycleValidationError("recovery department is invalid")
        target_uid, target = self._backend.resolve_target(account_ref)
        if target_uid == actor.uid:
            raise LifecycleStateConflict("self-target recovery is forbidden")
        if target.role == "admin":
            raise LifecycleStateConflict("Admin lifecycle recovery is unavailable")
        if target.role not in {"customer", "staff", "manager"}:
            raise LifecycleValidationError("target role is invalid")
        if operation == "reassign_department" and target.role != "staff":
            raise LifecycleStateConflict("target role is not reassignable")
        action, _guard = self._backend.recover_existing_action(
            actor_uid=actor.uid,
            target_uid=target_uid,
            account_ref=account_ref,
            target_role=target.role,
            operation=operation,
            requested_department=department_id,
        )
        if action.state == "conflict":
            if operation == "reassign_department" and action.result_code == "assigned_unresolved_work":
                raise RecoveryAssignedWork("assigned unresolved work prevents recovery")
            raise RecoveryLifecycleConflict("lifecycle recovery conflict")
        if operation == "disable":
            return AdminDisableService(self._backend, clock=self._clock).continue_existing(
                actor, account_ref=account_ref, action=action
            )
        if operation == "reactivate":
            return AdminReactivateService(self._backend, clock=self._clock).continue_existing(
                actor, account_ref=account_ref, action=action
            )
        if operation == "reassign_department" and department_id is not None:
            return AdminReassignService(self._backend, clock=self._clock).continue_existing(
                account_ref=account_ref,
                department_id=department_id,
                action=action,
            )
        raise LifecycleValidationError("recovery request is invalid")


class FirebaseAdminLifecycleRecoveryBackend(FirebaseAdminReactivationBackend):
    """Explicit local Firebase adapter for continuation only."""

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
        return self._lifecycle.recover_existing_action(
            actor_uid=actor_uid,
            target_uid=target_uid,
            account_ref=account_ref,
            target_role=target_role,
            operation=operation,
            requested_department=requested_department,
        )

    def reassign_department(
        self, action_ref: str, *, expected_version: int, now: datetime
    ) -> LifecycleActionRecord:
        return self._lifecycle.reassign_department(
            action_ref, expected_version=expected_version, now=now
        )
