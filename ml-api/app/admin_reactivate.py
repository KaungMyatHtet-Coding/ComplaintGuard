"""Trusted, recoverable Admin reactivation for non-Admin targets."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Protocol

from app.admin_auth import AdminPrincipal
from app.admin_directory import AdminDirectoryRow
from app.admin_disable import FirebaseAdminDisableBackend
from app.admin_lifecycle import (
    LifecycleActionRecord,
    LifecycleActionService,
    LifecycleReactivationNotEligible,
    LifecycleRepository,
    LifecycleStateConflict,
    LifecycleValidationError,
    lifecycle_action_reference,
)
from app.schemas import AdminReactivateResponse


class ReactivateAlreadyActive(LookupError):
    """The target is active without a matching completed reactivation."""


class ReactivateAdminTarget(RuntimeError):
    """Admin reactivation is deferred to the globally governed slice."""


class ReactivateSelfTarget(RuntimeError):
    """An Admin cannot target their own account."""


class ReactivatePendingSetup(RuntimeError):
    """The inactive profile has no trusted completed-disable proof."""


class ReactivateIncomplete(RuntimeError):
    """Auth or completion persistence needs a safe retry."""


class ReactivateAuthIdentityMissing(RuntimeError):
    """The trusted target UID has no matching Auth identity."""


class ReactivateAuthIdentityConflict(RuntimeError):
    """The trusted Auth identity does not match the requested target."""


class ReactivateAuthUnavailable(RuntimeError):
    """Auth enablement could not be safely confirmed."""


class AdminReactivateBackend(LifecycleRepository, Protocol):
    def resolve_target(self, account_ref: str) -> tuple[str, AdminDirectoryRow]: ...

    def get_action(self, action_ref: str) -> LifecycleActionRecord | None: ...

    def find_completed_disable_action(
        self, *, target_uid: str, account_ref: str, target_role: str
    ) -> LifecycleActionRecord: ...

    def reserve_reactivation(self, record: LifecycleActionRecord) -> LifecycleActionRecord: ...

    def activate_profile(
        self, action_ref: str, *, expected_version: int, now: datetime
    ) -> LifecycleActionRecord: ...

    def enable_auth_identity(self, target_uid: str) -> None: ...


class AdminReactivateService:
    def __init__(
        self,
        backend: AdminReactivateBackend,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._backend = backend
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def reactivate(
        self,
        actor: AdminPrincipal,
        *,
        account_ref: str,
        idempotency_key: str,
    ) -> AdminReactivateResponse:
        target_uid, target = self._backend.resolve_target(account_ref)
        if target_uid == actor.uid:
            raise ReactivateSelfTarget("self-target reactivation is forbidden")
        if target.role == "admin":
            raise ReactivateAdminTarget("Admin reactivation is not available in this slice")
        if target.role not in {"customer", "staff", "manager"}:
            raise LifecycleValidationError("target role is invalid")

        action_ref = lifecycle_action_reference(
            actor_uid=actor.uid,
            target_uid=target_uid,
            idempotency_key=idempotency_key,
            operation="reactivate",
        )
        existing = self._backend.get_action(action_ref)
        if target.active and not (
            existing is not None
            and existing.operation == "reactivate"
            and existing.state == "completed"
        ):
            raise ReactivateAlreadyActive("target is already active")

        if existing is not None:
            previous_action_ref = existing.previous_action_ref
            if previous_action_ref is None:
                raise ReactivatePendingSetup("reactivation proof is missing")
        else:
            try:
                previous = self._backend.find_completed_disable_action(
                    target_uid=target_uid,
                    account_ref=account_ref,
                    target_role=target.role,
                )
            except LifecycleReactivationNotEligible as exc:
                raise ReactivatePendingSetup("pending_setup activation is forbidden") from exc
            previous_action_ref = previous.action_ref

        action = LifecycleActionService(self._backend, clock=self._clock).reserve(
            actor_uid=actor.uid,
            target_uid=target_uid,
            target_role=target.role,
            operation="reactivate",
            idempotency_key=idempotency_key,
            account_ref=account_ref,
            previous_action_ref=previous_action_ref,
        )
        action = self._backend.reserve_reactivation(action)
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
    ) -> AdminReactivateResponse:
        """Continue one discovered action without reserving or transferring it."""

        if action.state == "completed":
            return self._response(account_ref)
        auth_enabled_in_this_attempt = False
        if action.state == "reserved":
            try:
                action = LifecycleActionService(self._backend, clock=self._clock).transition(
                    action.action_ref,
                    expected_version=action.version,
                    to_state="auth_enable_pending",
                    result_code="auth_enable_pending",
                )
            except Exception as exc:
                raise ReactivateIncomplete("reactivation auth-pending transition is incomplete") from exc
        if action.state == "auth_enable_pending":
            try:
                self._backend.enable_auth_identity(action.target_uid)
            except (ReactivateAuthIdentityMissing, ReactivateAuthIdentityConflict, ReactivateAuthUnavailable) as exc:
                raise ReactivateIncomplete("Auth enablement is incomplete") from exc
            auth_enabled_in_this_attempt = True
            try:
                action = LifecycleActionService(self._backend, clock=self._clock).transition(
                    action.action_ref,
                    expected_version=action.version,
                    to_state="profile_activation_pending",
                    result_code="profile_activation_pending",
                )
            except Exception as exc:
                raise ReactivateIncomplete("reactivation profile-pending transition is incomplete") from exc
        if action.state == "profile_activation_pending":
            if not auth_enabled_in_this_attempt:
                try:
                    self._backend.enable_auth_identity(action.target_uid)
                except (ReactivateAuthIdentityMissing, ReactivateAuthIdentityConflict, ReactivateAuthUnavailable) as exc:
                    raise ReactivateIncomplete("Auth enablement is incomplete") from exc
            try:
                action = self._backend.activate_profile(
                    action.action_ref,
                    expected_version=action.version,
                    now=self._clock(),
                )
            except Exception as exc:
                raise ReactivateIncomplete("reactivation completion is incomplete") from exc
        if action.state != "completed":
            raise LifecycleStateConflict("reactivation action is not recoverable")
        return self._response(account_ref)

    @staticmethod
    def _response(account_ref: str) -> AdminReactivateResponse:
        return AdminReactivateResponse(
            accountRef=account_ref,
            operation="reactivate",
            status="completed",
            profileState="active",
        )


class FirebaseAdminReactivationBackend(FirebaseAdminDisableBackend):
    """Explicit local Firebase adapter for reactivation orchestration."""

    def enable_auth_identity(self, target_uid: str) -> None:
        try:
            identity = self._auth.get_user(target_uid)
            if getattr(identity, "uid", target_uid) != target_uid:
                raise ReactivateAuthIdentityConflict("Auth identity mismatch")
            self._auth.update_user(target_uid, disabled=False)
        except ReactivateAuthIdentityConflict:
            raise
        except Exception as exc:
            if exc.__class__.__name__ in {"UserNotFoundError", "UserNotFound"}:
                raise ReactivateAuthIdentityMissing("Auth identity missing") from exc
            raise ReactivateAuthUnavailable("Auth enablement unavailable") from exc

    def reactivation_eligibility_reason(
        self,
        *,
        target_uid: str,
        account_ref: str,
        target_role: str,
    ) -> str | None:
        return self._lifecycle.reactivation_eligibility_reason(
            target_uid=target_uid,
            account_ref=account_ref,
            target_role=target_role,
        )
