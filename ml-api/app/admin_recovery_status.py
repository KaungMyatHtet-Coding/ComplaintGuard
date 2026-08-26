"""Actor-bound, read-only discovery of existing lifecycle actions."""

from __future__ import annotations

from typing import Protocol

from app.admin_auth import AdminPrincipal
from app.admin_directory import AdminDirectoryRow, validate_account_reference
from app.admin_lifecycle import LifecycleOperation, LifecycleValidationError
from app.schemas import AdminLifecycleRecoveryStatusResponse


class AdminLifecycleRecoveryStatusBackend(Protocol):
    def resolve_target(self, account_ref: str) -> tuple[str, AdminDirectoryRow]: ...

    def recovery_status(
        self,
        *,
        actor_uid: str,
        target_uid: str,
        account_ref: str,
        target_role: str,
    ) -> tuple[str, LifecycleOperation | None, str | None]: ...


class AdminLifecycleRecoveryStatusService:
    """Project only safe continuation metadata for the original Admin actor."""

    def __init__(self, backend: AdminLifecycleRecoveryStatusBackend) -> None:
        self._backend = backend

    def status(
        self,
        actor: AdminPrincipal,
        *,
        account_ref: str,
    ) -> AdminLifecycleRecoveryStatusResponse:
        validate_account_reference(account_ref)
        target_uid, target = self._backend.resolve_target(account_ref)

        # Self-target and Admin-target lifecycle mutation remain unavailable;
        # neither case may reveal lifecycle records through this projection.
        if target_uid == actor.uid or target.role == "admin":
            return self._response(account_ref, "none", None, None)
        if target.role not in {"customer", "staff", "manager"}:
            raise LifecycleValidationError("target role is invalid")

        recovery_state, operation, department_id = self._backend.recovery_status(
            actor_uid=actor.uid,
            target_uid=target_uid,
            account_ref=account_ref,
            target_role=target.role,
        )
        return self._response(account_ref, recovery_state, operation, department_id)

    @staticmethod
    def _response(
        account_ref: str,
        recovery_state: str,
        operation: LifecycleOperation | None,
        department_id: str | None,
    ) -> AdminLifecycleRecoveryStatusResponse:
        return AdminLifecycleRecoveryStatusResponse(
            accountRef=account_ref,
            recoveryState=recovery_state,
            operation=operation,
            departmentId=department_id,
        )
