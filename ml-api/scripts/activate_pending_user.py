"""Fail-closed, owner-operated activation for one pending Staff or Manager."""

from __future__ import annotations

import getpass
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.account_state import AccountStateValidationError, validate_account_state
from app.ticketing import firebase_admin_clients, run_firestore_transaction
from scripts.bootstrap_local_admin import (
    AuthRecord,
    BootstrapConflict,
    BootstrapDependencyError,
    BootstrapError,
    BootstrapInputError,
    validate_bootstrap_environment,
)

MIN_ACTIVATION_PASSWORD_LENGTH = 12
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_ACTION_STATES = {
    "pending_setup",
    "activation_started",
    "password_configured",
    "auth_enabled",
    "active",
}


class ActivationError(BootstrapError):
    """Safe operator-facing activation failure."""


@dataclass(frozen=True)
class ActivationResult:
    status: str


class ActivationBackend(Protocol):
    server_timestamp: object

    def get_auth_by_email(self, email: str) -> AuthRecord | None: ...

    def get_profile(self, uid: str) -> dict[str, Any] | None: ...

    def list_actions_for_target(self, uid: str) -> list[dict[str, Any]]: ...

    def get_profile_for_actor(self, uid: str) -> dict[str, Any] | None: ...

    def update_action_status(self, action_id: str, target_uid: str, status: str) -> None: ...

    def set_password(self, uid: str, password: str) -> None: ...

    def enable_auth(self, uid: str) -> None: ...

    def activate_profile(self, uid: str) -> None: ...


def normalize_target_email(value: str) -> str:
    normalized = value.strip().lower()
    if not _EMAIL_PATTERN.fullmatch(normalized):
        raise ActivationError("target_email_invalid")
    return normalized


def _profile_matches_target(profile: Any, auth: AuthRecord) -> bool:
    if not isinstance(profile, dict):
        return False
    expected_keys = {
        "email",
        "displayName",
        "locale",
        "role",
        "departmentId",
        "active",
        "accountState",
        "createdAt",
        "updatedAt",
    }
    if set(profile) != expected_keys:
        return False
    if (
        not isinstance(auth.uid, str)
        or not isinstance(auth.email, str)
        or not _EMAIL_PATTERN.fullmatch(auth.email)
        or not isinstance(auth.display_name, str)
        or not auth.display_name.strip()
        or profile.get("email") != auth.email
        or profile.get("displayName") != auth.display_name
        or not isinstance(profile.get("displayName"), str)
        or not profile["displayName"].strip()
        or profile.get("locale") not in {"en", "my"}
        or profile.get("role") not in {"staff", "manager"}
        or profile.get("active") is not True and profile.get("active") is not False
        or _invalid_account_state(profile)
        or profile.get("createdAt") is None
        or profile.get("updatedAt") is None
    ):
        return False
    if profile["role"] == "staff":
        return isinstance(profile.get("departmentId"), str) and bool(
            re.fullmatch(
                r"(transfer_payment|account_support|card_atm|fraud_security|loan_credit|general_support)",
                profile["departmentId"],
            )
        )
    return profile.get("departmentId") is None


def _invalid_account_state(profile: dict[str, Any]) -> bool:
    try:
        validate_account_state(
            active=profile.get("active"),
            role=profile.get("role"),
            account_state=profile.get("accountState"),
        )
    except AccountStateValidationError:
        return True
    return False


def _admin_actor_is_valid(profile: Any) -> bool:
    if not isinstance(profile, dict):
        return False
    expected_keys = {
        "email",
        "displayName",
        "locale",
        "role",
        "departmentId",
        "active",
        "accountState",
        "createdAt",
        "updatedAt",
    }
    return (
        set(profile) == expected_keys
        and isinstance(profile.get("email"), str)
        and bool(_EMAIL_PATTERN.fullmatch(profile["email"]))
        and isinstance(profile.get("displayName"), str)
        and bool(profile["displayName"].strip())
        and profile.get("locale") in {"en", "my"}
        and profile.get("role") == "admin"
        and profile.get("departmentId") is None
        and profile.get("active") is True
        and profile.get("accountState") == "active"
        and profile.get("createdAt") is not None
        and profile.get("updatedAt") is not None
    )


def _read_password(password_reader: Callable[[str], str] | None = None) -> str:
    reader = password_reader or getpass.getpass
    password = reader("New account password: ")
    confirmation = reader("Confirm new account password: ")
    try:
        if password != confirmation:
            raise BootstrapInputError("password_mismatch")
        if (
            len(password) < MIN_ACTIVATION_PASSWORD_LENGTH
            or not re.search(r"[A-Za-z]", password)
            or not re.search(r"\d", password)
        ):
            raise BootstrapInputError("password_weak")
        return password
    finally:
        confirmation = ""


def activate_pending_user(
    *,
    backend: ActivationBackend | None = None,
    environment: dict[str, str | None] | None = None,
    email_reader: Callable[[str], str] | None = None,
    password_reader: Callable[[str], str] | None = None,
) -> ActivationResult:
    """Activate exactly one proven pending Staff or Manager account."""

    validate_bootstrap_environment(environment)
    reader = email_reader or input
    try:
        target_email = normalize_target_email(reader("Target account email: "))
    except ActivationError:
        raise
    except Exception as exc:
        raise ActivationError("target_email_invalid") from exc

    try:
        service = backend or FirebaseAdminActivationBackend()
        auth = service.get_auth_by_email(target_email)
        if auth is None:
            raise ActivationError("target_not_found")
        profile = service.get_profile(auth.uid)
        if not _profile_matches_target(profile, auth):
            raise BootstrapConflict("profile_conflict")
        actions = service.list_actions_for_target(auth.uid)
        if len(actions) != 1:
            raise BootstrapConflict("provisioning_origin_conflict")
        action = actions[0]
        _verify_provisioning_origin(action, auth, profile, service)
    except BootstrapError:
        raise
    except Exception as exc:
        raise BootstrapDependencyError("dependency_unavailable") from exc

    status = action["status"]
    if status == "active":
        if auth.disabled or profile.get("active") is not True or profile.get("accountState") != "active":
            raise BootstrapConflict("activation_state_conflict")
        return ActivationResult("existing")
    if profile.get("active") is True:
        if auth.disabled or status != "auth_enabled":
            raise BootstrapConflict("activation_state_conflict")
        try:
            service.update_action_status(action["actionId"], auth.uid, "active")
        except Exception as exc:
            raise BootstrapDependencyError("activation_incomplete") from exc
        return ActivationResult("completed")
    if auth.disabled is False:
        if status != "auth_enabled":
            raise BootstrapConflict("activation_state_conflict")
        try:
            service.activate_profile(auth.uid)
            service.update_action_status(action["actionId"], auth.uid, "active")
        except Exception as exc:
            raise BootstrapDependencyError("activation_incomplete") from exc
        return ActivationResult("completed")
    if status == "activation_started":
        raise BootstrapDependencyError("activation_incomplete")

    if status == "pending_setup":
        try:
            service.update_action_status(action["actionId"], auth.uid, "activation_started")
        except Exception as exc:
            raise BootstrapDependencyError("activation_incomplete") from exc
        password = _read_password(password_reader)
        try:
            service.set_password(auth.uid, password)
        except Exception as exc:
            raise BootstrapDependencyError("activation_incomplete") from exc
        finally:
            password = ""
        try:
            service.update_action_status(action["actionId"], auth.uid, "password_configured")
        except Exception as exc:
            raise BootstrapDependencyError("activation_incomplete") from exc
        status = "password_configured"

    if status == "password_configured":
        try:
            service.enable_auth(auth.uid)
            service.update_action_status(action["actionId"], auth.uid, "auth_enabled")
        except Exception as exc:
            raise BootstrapDependencyError("activation_incomplete") from exc
        status = "auth_enabled"

    if status == "auth_enabled":
        try:
            service.activate_profile(auth.uid)
            service.update_action_status(action["actionId"], auth.uid, "active")
        except Exception as exc:
            raise BootstrapDependencyError("activation_incomplete") from exc
        return ActivationResult("completed")
    raise BootstrapConflict("activation_state_conflict")


def _verify_provisioning_origin(
    action: dict[str, Any],
    auth: AuthRecord,
    profile: dict[str, Any],
    backend: ActivationBackend,
) -> None:
    if (
        action.get("operation") != "create_pending_user"
        or action.get("targetUid") != auth.uid
        or not isinstance(action.get("actionId"), str)
        or not action["actionId"]
        or action.get("status") not in _ACTION_STATES
        or not isinstance(action.get("requestFingerprint"), str)
        or not action["requestFingerprint"]
        or not isinstance(action.get("idempotencyKeyFingerprint"), str)
        or not action["idempotencyKeyFingerprint"]
        or not isinstance(action.get("actorUid"), str)
        or not action["actorUid"]
    ):
        raise BootstrapConflict("provisioning_origin_conflict")
    actor_profile = backend.get_profile_for_actor(action["actorUid"])
    if not _admin_actor_is_valid(actor_profile):
        raise BootstrapConflict("provisioning_actor_conflict")
    if profile.get("active") is True and action["status"] not in {"auth_enabled", "active"}:
        raise BootstrapConflict("activation_state_conflict")


class FirebaseAdminActivationBackend:
    """Explicitly local Firebase Admin adapter, constructed after validation."""

    def __init__(self) -> None:
        self._auth, self._db, self.server_timestamp = firebase_admin_clients()

    def get_auth_by_email(self, email: str) -> AuthRecord | None:
        try:
            record = self._auth.get_user_by_email(email)
        except Exception as exc:
            if exc.__class__.__name__ in {"UserNotFoundError", "UserNotFound"}:
                return None
            raise
        return _auth_record(record)

    def get_profile(self, uid: str) -> dict[str, Any] | None:
        snapshot = self._db.collection("users").document(uid).get()
        return snapshot.to_dict() if snapshot.exists else None

    def list_actions_for_target(self, uid: str) -> list[dict[str, Any]]:
        actions = []
        for snapshot in self._db.collection("adminProvisioningActions").stream():
            value = snapshot.to_dict() or {}
            if value.get("targetUid") == uid:
                actions.append(value)
        return actions

    def get_profile_for_actor(self, uid: str) -> dict[str, Any] | None:
        return self.get_profile(uid)

    def update_action_status(self, action_id: str, target_uid: str, status: str) -> None:
        if status not in _ACTION_STATES:
            raise BootstrapConflict("activation_state_conflict")
        reference = self._db.collection("adminProvisioningActions").document(action_id)

        def operation(transaction: Any) -> None:
            snapshot = next(transaction.get(reference))
            if not snapshot.exists:
                raise BootstrapConflict("provisioning_origin_conflict")
            value = snapshot.to_dict() or {}
            if value.get("targetUid") != target_uid:
                raise BootstrapConflict("provisioning_origin_conflict")
            transaction.update(
                reference,
                {"status": status, "updatedAt": self.server_timestamp},
            )

        run_firestore_transaction(self._db, operation)

    def set_password(self, uid: str, password: str) -> None:
        record = self._auth.get_user(uid)
        if getattr(record, "disabled", None) is not True:
            raise BootstrapConflict("activation_state_conflict")
        self._auth.update_user(uid, password=password)

    def enable_auth(self, uid: str) -> None:
        self._auth.update_user(uid, disabled=False)

    def activate_profile(self, uid: str) -> None:
        reference = self._db.collection("users").document(uid)

        def operation(transaction: Any) -> None:
            snapshot = next(transaction.get(reference))
            if not snapshot.exists:
                raise BootstrapConflict("profile_conflict")
            value = snapshot.to_dict() or {}
            if value.get("active") is True:
                return
            if (
                value.get("active") is not False
                or value.get("accountState") != "pending_setup"
                or value.get("role") not in {"staff", "manager"}
                or value.get("locale") not in {"en", "my"}
                or not isinstance(value.get("email"), str)
                or not isinstance(value.get("displayName"), str)
                or value.get("createdAt") is None
                or value.get("updatedAt") is None
                or (
                    value.get("role") == "staff"
                    and not isinstance(value.get("departmentId"), str)
                )
                or (
                    value.get("role") == "manager"
                    and value.get("departmentId") is not None
                )
            ):
                raise BootstrapConflict("profile_conflict")
            transaction.update(
                reference,
                {"active": True, "accountState": "active", "updatedAt": self.server_timestamp},
            )

        run_firestore_transaction(self._db, operation)


def _auth_record(record: Any) -> AuthRecord:
    uid = getattr(record, "uid", None)
    email = getattr(record, "email", None)
    display_name = getattr(record, "display_name", None)
    disabled = getattr(record, "disabled", None)
    if not isinstance(uid, str) or not isinstance(email, str) or not isinstance(display_name, str):
        raise BootstrapDependencyError("identity_invalid")
    if disabled not in {True, False}:
        raise BootstrapDependencyError("identity_invalid")
    return AuthRecord(uid, email, display_name, disabled)


def main() -> int:
    try:
        result = activate_pending_user()
    except BootstrapError as exc:
        messages = {
            "target_email_invalid": "Activation conflict",
            "target_not_found": "Activation conflict",
            "provisioning_origin_conflict": "Activation conflict",
            "provisioning_actor_conflict": "Activation conflict",
            "profile_conflict": "Activation conflict",
            "activation_state_conflict": "Activation conflict",
            "environment_invalid": "Activation incomplete",
            "dependency_unavailable": "Activation incomplete",
            "activation_incomplete": "Activation incomplete",
            "password_mismatch": "Activation incomplete",
            "password_weak": "Activation incomplete",
        }
        print(messages.get(exc.code, "Activation incomplete"))
        return 1
    print(
        {
            "completed": "Activation completed",
            "existing": "Existing activation preserved",
        }.get(result.status, "Activation incomplete")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
