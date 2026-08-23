"""Trusted, recoverable Admin disable orchestration for non-Admin targets."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, Protocol

from app.admin_auth import AdminAuthBackend, AdminPrincipal, FirebaseAdminAuthBackend
from app.admin_directory import AdminDirectoryRow, AdminDirectoryService
from app.admin_lifecycle import (
    FirebaseLifecycleRepository,
    LifecycleActionRecord,
    LifecycleActionService,
    LifecycleRepository,
    LifecycleStateConflict,
    LifecycleValidationError,
    lifecycle_action_reference,
)
from app.schemas import AdminDisableResponse
from app.ticketing import PersistenceError, firebase_admin_clients


class DisableAlreadyInactive(LookupError):
    """The target is inactive without a matching disable action."""


class DisableAdminTarget(RuntimeError):
    """Admin disablement is deferred to the separately guarded slice."""


class DisableSelfTarget(RuntimeError):
    """An Admin cannot target their own account."""


class DisableIncomplete(RuntimeError):
    """Auth or completion persistence needs a safe retry."""


class DisableAuthIdentityMissing(RuntimeError):
    """The trusted target UID has no matching Auth identity."""


class DisableAuthIdentityConflict(RuntimeError):
    """The trusted Auth identity does not match the requested target."""


class DisableAuthUnavailable(RuntimeError):
    """Auth disablement could not be safely confirmed."""


class DisableRevocationFailed(RuntimeError):
    """Refresh-token revocation could not be safely confirmed."""


class AdminDisableBackend(AdminAuthBackend, LifecycleRepository, Protocol):
    def resolve_target(self, account_ref: str) -> tuple[str, AdminDirectoryRow]: ...

    def get_action(self, action_ref: str) -> LifecycleActionRecord | None: ...

    def inactivate_profile(self, action_ref: str, *, now: datetime) -> LifecycleActionRecord: ...

    def disable_auth_identity(self, target_uid: str) -> None: ...

    def revoke_refresh_tokens(self, target_uid: str) -> None: ...


class AdminDisableService:
    def __init__(
        self,
        backend: AdminDisableBackend,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._backend = backend
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def disable(
        self,
        actor: AdminPrincipal,
        *,
        account_ref: str,
        idempotency_key: str,
    ) -> AdminDisableResponse:
        target_uid, target = self._backend.resolve_target(account_ref)
        if target_uid == actor.uid:
            raise DisableSelfTarget("self-target disable is forbidden")
        if target.role == "admin":
            raise DisableAdminTarget("Admin disablement is not available in this slice")
        if target.role not in {"customer", "staff", "manager"}:
            raise LifecycleValidationError("target role is invalid")

        action_ref = lifecycle_action_reference(
            actor_uid=actor.uid,
            target_uid=target_uid,
            idempotency_key=idempotency_key,
            operation="disable",
        )
        existing = self._backend.get_action(action_ref)
        if not target.active:
            if existing is None or existing.target_uid != target_uid or existing.operation != "disable":
                raise DisableAlreadyInactive("target is already inactive")
            if existing.state not in {
                "profile_inactivated",
                "auth_disable_pending",
                "completed",
            }:
                raise DisableAlreadyInactive("target is already inactive")

        action = LifecycleActionService(self._backend, clock=self._clock).reserve(
            actor_uid=actor.uid,
            target_uid=target_uid,
            target_role=target.role,
            operation="disable",
            idempotency_key=idempotency_key,
            account_ref=account_ref,
        )
        return self.continue_existing(
            actor,
            account_ref=account_ref,
            action=action,
        )

    def continue_existing(
        self,
        actor: AdminPrincipal,
        *,
        account_ref: str,
        action: LifecycleActionRecord,
    ) -> AdminDisableResponse:
        """Continue one already-reserved action without reserving anything."""

        if action.state in {"reserved", "profile_inactivated", "auth_disable_pending", "completed"}:
            action = self._backend.inactivate_profile(
                action.action_ref,
                now=self._clock(),
            )
        if action.state == "completed":
            return self._response(account_ref)
        if action.state == "profile_inactivated":
            action = LifecycleActionService(self._backend, clock=self._clock).transition(
                action.action_ref,
                expected_version=action.version,
                to_state="auth_disable_pending",
                result_code="auth_disable_pending",
            )
        if action.state != "auth_disable_pending":
            raise LifecycleStateConflict("disable action is not recoverable")
        try:
            self._backend.disable_auth_identity(action.target_uid)
            self._backend.revoke_refresh_tokens(action.target_uid)
        except (DisableAuthIdentityMissing, DisableAuthIdentityConflict) as exc:
            raise DisableIncomplete("trusted Auth identity is unavailable") from exc
        except (DisableAuthUnavailable, DisableRevocationFailed) as exc:
            raise DisableIncomplete("Auth disablement is incomplete") from exc
        try:
            completed = LifecycleActionService(self._backend, clock=self._clock).transition(
                action.action_ref,
                expected_version=action.version,
                to_state="completed",
                result_code="completed",
            )
        except Exception as exc:
            raise DisableIncomplete("lifecycle completion is incomplete") from exc
        if completed.state != "completed":
            raise DisableIncomplete("lifecycle completion is incomplete")
        return self._response(account_ref)

    @staticmethod
    def _response(account_ref: str) -> AdminDisableResponse:
        return AdminDisableResponse(
            accountRef=account_ref,
            operation="disable",
            status="completed",
            profileState="inactive",
        )


class FirebaseAdminDisableBackend(FirebaseAdminAuthBackend):
    """Explicit local Firebase adapter for disable orchestration."""

    def __init__(self, clients: tuple[Any, Any, object] | None = None) -> None:
        actual_clients = clients or firebase_admin_clients()
        super().__init__(actual_clients)
        self._lifecycle = FirebaseLifecycleRepository(actual_clients)

    def list_user_profiles(self, *, limit: int) -> list[tuple[str, dict[str, Any]]]:
        try:
            snapshots = self._db.collection("users").limit(limit).stream()
            return [(snapshot.id, snapshot.to_dict() or {}) for snapshot in snapshots]
        except Exception as exc:
            raise PersistenceError("directory lookup failed") from exc

    def list_tickets(self, *, limit: int) -> list[dict[str, Any]]:
        try:
            snapshots = self._db.collection("tickets").limit(limit).stream()
            return [snapshot.to_dict() or {} for snapshot in snapshots]
        except Exception as exc:
            raise PersistenceError("ticket eligibility lookup failed") from exc

    def resolve_target(self, account_ref: str) -> tuple[str, AdminDirectoryRow]:
        return AdminDirectoryService(self).resolve_account_reference(account_ref)

    def get_action(self, action_ref: str) -> LifecycleActionRecord | None:
        return self._lifecycle.get_action(action_ref)

    def reserve(self, record: LifecycleActionRecord) -> LifecycleActionRecord:
        return self._lifecycle.reserve(record)

    def inactivate_profile(self, action_ref: str, *, now: datetime) -> LifecycleActionRecord:
        return self._lifecycle.inactivate_profile(action_ref, now=now)

    def transition(self, action_ref: str, *, expected_version: int, to_state: Any, result_code: str | None, now: datetime) -> LifecycleActionRecord:
        return self._lifecycle.transition(
            action_ref,
            expected_version=expected_version,
            to_state=to_state,
            result_code=result_code,
            now=now,
        )

    def append_audit(self, event: Any) -> Any:
        return self._lifecycle.append_audit(event)

    def disable_auth_identity(self, target_uid: str) -> None:
        try:
            identity = self._auth.get_user(target_uid)
            if getattr(identity, "uid", target_uid) != target_uid:
                raise DisableAuthIdentityConflict("Auth identity mismatch")
            self._auth.update_user(target_uid, disabled=True)
        except DisableAuthIdentityConflict:
            raise
        except Exception as exc:
            if exc.__class__.__name__ in {"UserNotFoundError", "UserNotFound"}:
                raise DisableAuthIdentityMissing("Auth identity missing") from exc
            raise DisableAuthUnavailable("Auth disablement unavailable") from exc

    def revoke_refresh_tokens(self, target_uid: str) -> None:
        try:
            self._auth.revoke_refresh_tokens(target_uid)
        except Exception as exc:
            if exc.__class__.__name__ in {"UserNotFoundError", "UserNotFound"}:
                raise DisableAuthIdentityMissing("Auth identity missing") from exc
            raise DisableRevocationFailed("Auth revocation unavailable") from exc
