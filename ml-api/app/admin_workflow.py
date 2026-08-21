"""Trusted pending Staff/Manager provisioning without credential handling."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Protocol

from app.admin_auth import AdminAuthBackend, AdminPrincipal, FirebaseAdminAuthBackend
from app.schemas import AdminProvisioningRequest
from app.ticketing import PersistenceError, run_firestore_transaction


class ProvisioningEmailExists(RuntimeError):
    """The target email belongs to an unrelated existing Auth identity."""


class ProvisioningProfileConflict(RuntimeError):
    """The target UID has an incompatible existing profile."""


class ProvisioningIdempotencyConflict(RuntimeError):
    """The action key was reused with a different request."""


class ProvisioningIncomplete(RuntimeError):
    """A safe pending operation needs a later retry."""


ADMIN_PROVISIONING_ACTION_DOMAIN = "complaintguard:admin-provisioning:v1"


@dataclass(frozen=True)
class AuthIdentity:
    uid: str
    email: str
    display_name: str
    disabled: bool = True


@dataclass(frozen=True)
class PendingProvisioningResult:
    status: str
    identity: AuthIdentity
    request: AdminProvisioningRequest
    created: bool


class AdminProvisioningBackend(AdminAuthBackend, Protocol):
    server_timestamp: object

    def list_user_profiles(self, *, limit: int) -> list[tuple[str, dict[str, Any]]]: ...

    def reserve_action(
        self,
        *,
        action_id: str,
        actor_uid: str,
        key_fingerprint: str,
        request_fingerprint: str,
    ) -> dict[str, Any] | None: ...

    def create_disabled_auth(self, *, email: str, display_name: str) -> AuthIdentity: ...

    def get_auth_identity(self, uid: str) -> AuthIdentity: ...

    def record_target(self, *, action_id: str, target_uid: str) -> None: ...

    def complete_pending(
        self,
        *,
        action_id: str,
        identity: AuthIdentity,
        request: AdminProvisioningRequest,
    ) -> None: ...

    def mark_action_failed(self, *, action_id: str, code: str) -> None: ...


def _action_id(actor_uid: str, idempotency_key: str) -> str:
    canonical_tuple = json.dumps(
        [ADMIN_PROVISIONING_ACTION_DOMAIN, actor_uid, idempotency_key],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical_tuple.encode("utf-8")).hexdigest()


def _fingerprint(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode()).hexdigest()


def request_fingerprint(request: AdminProvisioningRequest) -> str:
    return _fingerprint(request.model_dump(mode="json", by_alias=True))


def idempotency_key_fingerprint(key: str) -> str:
    return _fingerprint({"idempotencyKey": key})


class AdminProvisioningService:
    def __init__(self, backend: AdminProvisioningBackend) -> None:
        self._backend = backend

    def provision(
        self,
        actor: AdminPrincipal,
        request: AdminProvisioningRequest,
    ) -> PendingProvisioningResult:
        action_id = _action_id(actor.uid, request.idempotency_key)
        fingerprint = request_fingerprint(request)
        action = self._backend.reserve_action(
            action_id=action_id,
            actor_uid=actor.uid,
            key_fingerprint=idempotency_key_fingerprint(request.idempotency_key),
            request_fingerprint=fingerprint,
        )
        if action is not None:
            if action.get("requestFingerprint") != fingerprint:
                raise ProvisioningIdempotencyConflict("idempotency key reused")
            result = self._recover_existing(action, request, action_id)
            if result is not None:
                return result

        if action is not None and action.get("status") == "failed":
            if action.get("resultCode") == "email_exists":
                raise ProvisioningEmailExists("target email already exists")
            if action.get("resultCode") == "auth_creation_failed":
                # A failed Auth call has no confirmed UID. A retry is safe;
                # the adapter must still reject any unrelated existing email.
                pass
            else:
                raise ProvisioningIncomplete("pending provisioning requires retry")
        elif action is not None and action.get("targetUid") is None:
            raise ProvisioningIncomplete("pending provisioning requires retry")

        try:
            identity = self._backend.create_disabled_auth(
                email=request.email,
                display_name=request.display_name,
            )
        except ProvisioningEmailExists:
            self._safe_mark_failed(action_id, "email_exists")
            raise
        except Exception as exc:
            self._safe_mark_failed(action_id, "auth_creation_failed")
            raise ProvisioningIncomplete("provisioning is temporarily incomplete") from exc

        try:
            self._backend.record_target(action_id=action_id, target_uid=identity.uid)
            self._backend.complete_pending(
                action_id=action_id,
                identity=identity,
                request=request,
            )
        except ProvisioningProfileConflict:
            raise
        except Exception as exc:
            raise ProvisioningIncomplete("provisioning is temporarily incomplete") from exc
        return PendingProvisioningResult("pending_setup", identity, request, True)

    def _recover_existing(
        self,
        action: dict[str, Any],
        request: AdminProvisioningRequest,
        action_id: str,
    ) -> PendingProvisioningResult | None:
        target_uid = action.get("targetUid")
        if isinstance(target_uid, str):
            identity = self._backend.get_auth_identity(target_uid)
            if (
                identity.disabled is not True
                or identity.email != request.email
                or identity.display_name != request.display_name
            ):
                raise ProvisioningProfileConflict("pending identity conflict")
            self._backend.complete_pending(
                action_id=action_id,
                identity=identity,
                request=request,
            )
            return PendingProvisioningResult("pending_setup", identity, request, False)
        return None

    def _safe_mark_failed(self, action_id: str, code: str) -> None:
        try:
            self._backend.mark_action_failed(action_id=action_id, code=code)
        except Exception:  # noqa: BLE001 - do not expose finalization details.
            # The original safe failure remains safe even if action finalization
            # is unavailable; no credential or profile data is logged.
            return


class FirebaseAdminProvisioningBackend(FirebaseAdminAuthBackend):
    """Fail-closed local Admin SDK adapter for pending account creation."""

    server_timestamp: object

    def __init__(self, clients: tuple[Any, Any, object] | None = None) -> None:
        super().__init__(clients)
        self.server_timestamp = self._server_timestamp

    def _action_reference(self, action_id: str) -> Any:
        return self._db.collection("adminProvisioningActions").document(action_id)

    def reserve_action(
        self,
        *,
        action_id: str,
        actor_uid: str,
        key_fingerprint: str,
        request_fingerprint: str,
    ) -> dict[str, Any] | None:
        reference = self._action_reference(action_id)
        document = {
            "actorUid": actor_uid,
            "actionId": action_id,
            "idempotencyKeyFingerprint": key_fingerprint,
            "requestFingerprint": request_fingerprint,
            "operation": "create_pending_user",
            "targetUid": None,
            "status": "started",
            "resultCode": None,
            "createdAt": self.server_timestamp,
            "updatedAt": self.server_timestamp,
        }

        def operation(transaction: Any) -> dict[str, Any] | None:
            snapshot = next(transaction.get(reference))
            if snapshot.exists:
                return snapshot.to_dict()
            transaction.create(reference, document)
            return None

        try:
            return run_firestore_transaction(self._db, operation)
        except Exception as exc:
            raise PersistenceError("provisioning action reservation failed") from exc

    def create_disabled_auth(self, *, email: str, display_name: str) -> AuthIdentity:
        try:
            record = self._auth.create_user(
                email=email,
                display_name=display_name,
                disabled=True,
            )
        except Exception as exc:
            if exc.__class__.__name__ in {"EmailAlreadyExistsError", "EmailAlreadyExists"}:
                raise ProvisioningEmailExists("target email already exists") from exc
            raise ProvisioningIncomplete("provisioning is temporarily incomplete") from exc
        uid = getattr(record, "uid", None)
        verified_email = getattr(record, "email", None)
        verified_name = getattr(record, "display_name", None) or display_name
        if not isinstance(uid, str) or not isinstance(verified_email, str):
            raise ProvisioningIncomplete("provisioning is temporarily incomplete")
        if getattr(record, "disabled", None) is not True:
            raise ProvisioningIncomplete("provisioning is temporarily incomplete")
        return AuthIdentity(
            uid=uid,
            email=verified_email,
            display_name=verified_name,
            disabled=True,
        )

    def get_auth_identity(self, uid: str) -> AuthIdentity:
        try:
            record = self._auth.get_user(uid)
        except Exception as exc:
            raise PersistenceError("pending identity lookup failed") from exc
        email = getattr(record, "email", None)
        display_name = getattr(record, "display_name", None) or ""
        if not isinstance(email, str) or not isinstance(display_name, str):
            raise ProvisioningIncomplete("pending identity is incomplete")
        if getattr(record, "disabled", None) is not True:
            raise ProvisioningProfileConflict("pending identity is not disabled")
        return AuthIdentity(uid=uid, email=email, display_name=display_name, disabled=True)

    def record_target(self, *, action_id: str, target_uid: str) -> None:
        reference = self._action_reference(action_id)

        def operation(transaction: Any) -> None:
            snapshot = next(transaction.get(reference))
            if not snapshot.exists:
                raise PersistenceError("provisioning action missing")
            current = snapshot.to_dict() or {}
            existing = current.get("targetUid")
            if existing is not None and existing != target_uid:
                raise ProvisioningIdempotencyConflict("provisioning target conflict")
            transaction.update(
                reference,
                {"targetUid": target_uid, "updatedAt": self.server_timestamp},
            )

        try:
            run_firestore_transaction(self._db, operation)
        except (ProvisioningIdempotencyConflict, PersistenceError):
            raise
        except Exception as exc:
            raise PersistenceError("provisioning target update failed") from exc

    def complete_pending(
        self,
        *,
        action_id: str,
        identity: AuthIdentity,
        request: AdminProvisioningRequest,
    ) -> None:
        action_reference = self._action_reference(action_id)
        profile_reference = self._db.collection("users").document(identity.uid)
        profile = {
            "email": identity.email,
            "displayName": identity.display_name,
            "locale": request.locale,
            "role": request.role,
            "departmentId": request.department_id,
            "active": False,
            "createdAt": self.server_timestamp,
            "updatedAt": self.server_timestamp,
        }

        def operation(transaction: Any) -> None:
            action_snapshot = next(transaction.get(action_reference))
            profile_snapshot = next(transaction.get(profile_reference))
            if not action_snapshot.exists:
                raise PersistenceError("provisioning action missing")
            action = action_snapshot.to_dict() or {}
            if action.get("targetUid") != identity.uid:
                raise ProvisioningIdempotencyConflict("provisioning target conflict")
            if profile_snapshot.exists:
                existing = profile_snapshot.to_dict() or {}
                expected = {key: value for key, value in profile.items() if key not in {"createdAt", "updatedAt"}}
                if (
                    any(existing.get(key) != value for key, value in expected.items())
                    or existing.get("createdAt") is None
                    or existing.get("updatedAt") is None
                ):
                    raise ProvisioningProfileConflict("existing profile conflict")
            else:
                transaction.create(profile_reference, profile)
            transaction.update(
                action_reference,
                {
                    "status": "pending_setup",
                    "resultCode": "pending_setup",
                    "updatedAt": self.server_timestamp,
                },
            )

        try:
            run_firestore_transaction(self._db, operation)
        except (ProvisioningIdempotencyConflict, ProvisioningProfileConflict, PersistenceError):
            raise
        except Exception as exc:
            raise PersistenceError("pending profile completion failed") from exc

    def mark_action_failed(self, *, action_id: str, code: str) -> None:
        reference = self._action_reference(action_id)

        def operation(transaction: Any) -> None:
            snapshot = next(transaction.get(reference))
            if not snapshot.exists:
                return
            transaction.update(
                reference,
                {"status": "failed", "resultCode": code, "updatedAt": self.server_timestamp},
            )

        try:
            run_firestore_transaction(self._db, operation)
        except Exception as exc:
            raise PersistenceError("provisioning action update failed") from exc

    def list_user_profiles(self, *, limit: int) -> list[tuple[str, dict[str, Any]]]:
        try:
            snapshots = (
                self._db.collection("users")
                .where("role", "in", ["staff", "manager"])
                .limit(limit)
                .stream()
            )
            return [
                (snapshot.id, snapshot.to_dict() or {})
                for snapshot in snapshots
            ]
        except Exception as exc:
            raise PersistenceError("directory lookup failed") from exc
