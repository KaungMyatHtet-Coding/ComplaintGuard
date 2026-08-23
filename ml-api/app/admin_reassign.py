"""Trusted, recoverable Staff department reassignment orchestration."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Protocol

from app.admin_auth import AdminPrincipal
from app.admin_directory import AdminDirectoryRow
from app.admin_disable import FirebaseAdminDisableBackend
from app.admin_lifecycle import (
    FirebaseLifecycleRepository,
    LifecycleActionRecord,
    LifecycleActionService,
    LifecycleStateConflict,
    lifecycle_action_reference,
)
from app.schemas import AdminReassignDepartmentResponse
from app.ticketing import PersistenceError, firebase_admin_clients


class ReassignAdminTarget(RuntimeError):
    """Admin targets are not supported by the Staff reassignment slice."""


class ReassignSelfTarget(RuntimeError):
    """An Admin cannot target their own account."""


class ReassignPendingOrInactive(RuntimeError):
    """Only active Staff profiles may be reassigned."""


class ReassignRoleNotReassignable(RuntimeError):
    """Customer, Manager, and other non-Staff roles are immutable here."""


class ReassignSameDepartment(RuntimeError):
    """The requested department is already the trusted current department."""


class ReassignAssignedWork(RuntimeError):
    """Explicit unresolved work prevents reassignment."""


class ReassignScanIncomplete(RuntimeError):
    """The bounded assignment scan could not establish a safe result."""


class AdminReassignBackend(Protocol):
    def resolve_target(self, account_ref: str) -> tuple[str, AdminDirectoryRow]: ...

    def get_action(self, action_ref: str) -> LifecycleActionRecord | None: ...

    def reserve(self, record: LifecycleActionRecord) -> LifecycleActionRecord: ...

    def reassign_department(
        self, action_ref: str, *, expected_version: int, now: datetime
    ) -> LifecycleActionRecord: ...

    def reassignment_eligibility_reason(self, *, target_uid: str) -> str | None: ...


class AdminReassignService:
    def __init__(
        self,
        backend: AdminReassignBackend,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._backend = backend
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def reassign(
        self,
        actor: AdminPrincipal,
        *,
        account_ref: str,
        idempotency_key: str,
        department_id: str,
    ) -> AdminReassignDepartmentResponse:
        target_uid, target = self._backend.resolve_target(account_ref)
        if target_uid == actor.uid:
            raise ReassignSelfTarget("self-target reassignment is forbidden")
        if target.role == "admin":
            raise ReassignAdminTarget("Admin reassignment is not available in this slice")
        if target.role != "staff":
            raise ReassignRoleNotReassignable("target role is not reassignable")
        if not target.active:
            raise ReassignPendingOrInactive("inactive Staff cannot be reassigned")
        action_ref = lifecycle_action_reference(
            actor_uid=actor.uid,
            target_uid=target_uid,
            idempotency_key=idempotency_key,
            operation="reassign_department",
        )
        existing = self._backend.get_action(action_ref)
        if existing is not None:
            if existing.state == "completed":
                replay = LifecycleActionService(self._backend, clock=self._clock).reserve(
                    actor_uid=actor.uid,
                    target_uid=target_uid,
                    target_role="staff",
                    operation="reassign_department",
                    idempotency_key=idempotency_key,
                    account_ref=account_ref,
                    requested_department=department_id,
                )
                if replay.state == "completed" and target.department_id == department_id:
                    return self._response(account_ref, department_id)
            if existing.state == "conflict" and existing.result_code == "assigned_unresolved_work":
                raise ReassignAssignedWork("assigned unresolved work prevents reassignment")
        if existing is None and target.department_id == department_id:
            raise ReassignSameDepartment("department is unchanged")

        action = LifecycleActionService(self._backend, clock=self._clock).reserve(
            actor_uid=actor.uid,
            target_uid=target_uid,
            target_role="staff",
            operation="reassign_department",
            idempotency_key=idempotency_key,
            account_ref=account_ref,
            requested_department=department_id,
        )
        return self.continue_existing(
            account_ref=account_ref,
            department_id=department_id,
            current_department_id=target.department_id,
            action=action,
        )

    def continue_existing(
        self,
        *,
        account_ref: str,
        department_id: str,
        current_department_id: str | None = None,
        action: LifecycleActionRecord,
    ) -> AdminReassignDepartmentResponse:
        """Continue one discovered action without reserving a new action."""

        if action.state == "completed":
            if current_department_id is not None and current_department_id != department_id:
                raise LifecycleStateConflict("completed reassignment is inconsistent")
            return self._response(account_ref, department_id)
        if action.state == "conflict":
            if action.result_code == "assigned_unresolved_work":
                raise ReassignAssignedWork("assigned unresolved work prevents reassignment")
            raise LifecycleStateConflict("reassignment conflict is not recoverable")
        try:
            result = self._backend.reassign_department(
                action.action_ref,
                expected_version=action.version,
                now=self._clock(),
            )
        except PersistenceError as exc:
            if "scan is incomplete" in str(exc):
                raise ReassignScanIncomplete("assignment scan is incomplete") from exc
            raise
        if result.state == "conflict" and result.result_code == "assigned_unresolved_work":
            raise ReassignAssignedWork("assigned unresolved work prevents reassignment")
        if result.state != "completed":
            raise LifecycleStateConflict("reassignment action is not complete")
        return self._response(account_ref, department_id)

    @staticmethod
    def _response(account_ref: str, department_id: str) -> AdminReassignDepartmentResponse:
        return AdminReassignDepartmentResponse(
            accountRef=account_ref,
            operation="reassign_department",
            status="completed",
            departmentId=department_id,
        )


class FirebaseAdminReassignmentBackend(FirebaseAdminDisableBackend):
    """Explicit local Firebase adapter; no Auth operation is exposed."""

    def __init__(self, clients: tuple[object, object, object] | None = None) -> None:
        actual_clients = clients or firebase_admin_clients()
        super().__init__(actual_clients)
        self._lifecycle = FirebaseLifecycleRepository(actual_clients)

    def reassign_department(
        self, action_ref: str, *, expected_version: int, now: datetime
    ) -> LifecycleActionRecord:
        return self._lifecycle.reassign_department(
            action_ref, expected_version=expected_version, now=now
        )

    def reassignment_eligibility_reason(self, *, target_uid: str) -> str | None:
        return self._lifecycle.reassignment_eligibility_reason(target_uid=target_uid)
