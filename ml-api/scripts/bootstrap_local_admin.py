"""Fail-closed, owner-operated bootstrap for one local ComplaintGuard Admin."""

from __future__ import annotations

import getpass
import os
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.account_state import AccountStateValidationError, validate_account_state
from app.firebase_environment import (
    FirebaseEnvironmentSafetyError,
    LocalEmulatorEnvironment,
    validate_local_emulator_environment,
)
from app.ticketing import firebase_admin_clients, run_firestore_transaction

FIXED_UID = "complaintguard-local-admin-v1"
FIXED_EMAIL = "admin.demo@complaintguard.test"
FIXED_DISPLAY_NAME = "ComplaintGuard Admin"
FIXED_LOCALE = "en"
FIXED_ROLE = "admin"
MIN_BOOTSTRAP_PASSWORD_LENGTH = 12


class BootstrapError(RuntimeError):
    """Safe operator-facing bootstrap failure identified only by a code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class BootstrapConflict(BootstrapError):
    pass


class BootstrapInputError(BootstrapError):
    pass


class BootstrapDependencyError(BootstrapError):
    pass


@dataclass(frozen=True)
class AuthRecord:
    uid: str
    email: str
    display_name: str
    disabled: bool


@dataclass(frozen=True)
class BootstrapResult:
    status: str


class BootstrapBackend(Protocol):
    server_timestamp: object

    def get_auth_by_uid(self, uid: str) -> AuthRecord | None: ...

    def get_auth_by_email(self, email: str) -> AuthRecord | None: ...

    def list_active_admin_uids(self) -> set[str]: ...

    def get_profile(self, uid: str) -> dict[str, Any] | None: ...

    def create_auth(
        self,
        *,
        uid: str,
        email: str,
        display_name: str,
        password: str,
    ) -> AuthRecord: ...

    def set_auth_disabled(self, uid: str, disabled: bool) -> None: ...

    def ensure_inactive_profile(self, uid: str) -> None: ...

    def activate_profile(self, uid: str) -> None: ...


def validate_bootstrap_environment(
    values: dict[str, str | None] | None = None,
) -> LocalEmulatorEnvironment:
    """Validate all Firebase targeting before an Admin SDK client is built."""

    try:
        environment = validate_local_emulator_environment(
            values if values is not None else os.environ
        )
    except FirebaseEnvironmentSafetyError as exc:
        raise BootstrapDependencyError("environment_invalid") from exc
    if environment.project_id != "demo-complaintguard":
        raise BootstrapDependencyError("environment_invalid")
    return environment


def _profile_matches(profile: Any, *, active: bool | None = None) -> bool:
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
    if active is not None and profile.get("active") is not active:
        return False
    try:
        validate_account_state(
            active=profile.get("active"),
            role=profile.get("role"),
            account_state=profile.get("accountState"),
        )
    except AccountStateValidationError:
        return False
    return (
        profile.get("email") == FIXED_EMAIL
        and profile.get("displayName") == FIXED_DISPLAY_NAME
        and profile.get("locale") == FIXED_LOCALE
        and profile.get("role") == FIXED_ROLE
        and profile.get("departmentId") is None
        and profile.get("active") in {True, False}
        and profile.get("createdAt") is not None
        and profile.get("updatedAt") is not None
    )


def _read_password(password_reader: Callable[[str], str] | None = None) -> str:
    reader = password_reader or getpass.getpass
    password = reader("Bootstrap password: ")
    confirmation = reader("Confirm bootstrap password: ")
    try:
        if password != confirmation:
            raise BootstrapInputError("password_mismatch")
        if (
            len(password) < MIN_BOOTSTRAP_PASSWORD_LENGTH
            or not re.search(r"[A-Za-z]", password)
            or not re.search(r"\d", password)
        ):
            raise BootstrapInputError("password_weak")
        return password
    finally:
        confirmation = ""


def bootstrap_local_admin(
    *,
    backend: BootstrapBackend | None = None,
    environment: dict[str, str | None] | None = None,
    password_reader: Callable[[str], str] | None = None,
) -> BootstrapResult:
    """Create or safely resume the one fixed local Admin lifecycle."""

    validate_bootstrap_environment(environment)
    try:
        service = backend or FirebaseAdminBootstrapBackend()
        active_admins = service.list_active_admin_uids()
        if any(uid != FIXED_UID for uid in active_admins):
            raise BootstrapConflict("admin_already_exists")
        fixed_auth = service.get_auth_by_uid(FIXED_UID)
        email_auth = service.get_auth_by_email(FIXED_EMAIL)
        profile = service.get_profile(FIXED_UID)
    except BootstrapError:
        raise
    except Exception as exc:
        raise BootstrapDependencyError("dependency_unavailable") from exc

    if email_auth is not None and email_auth.uid != FIXED_UID:
        raise BootstrapConflict("email_identity_conflict")
    if fixed_auth is not None and (
        fixed_auth.email != FIXED_EMAIL
        or fixed_auth.display_name != FIXED_DISPLAY_NAME
    ):
        raise BootstrapConflict("fixed_identity_conflict")
    if profile is not None and not _profile_matches(profile):
        raise BootstrapConflict("profile_conflict")
    if profile is not None and fixed_auth is None:
        raise BootstrapConflict("profile_without_auth")

    if fixed_auth is not None:
        if profile is not None and profile.get("active") is True:
            if fixed_auth.disabled:
                try:
                    service.set_auth_disabled(FIXED_UID, False)
                except Exception as exc:
                    raise BootstrapDependencyError("bootstrap_incomplete") from exc
                return BootstrapResult("resumed")
            return BootstrapResult("existing")
        if not fixed_auth.disabled:
            raise BootstrapConflict("enabled_partial_bootstrap")
        try:
            service.ensure_inactive_profile(FIXED_UID)
            service.set_auth_disabled(FIXED_UID, False)
            service.activate_profile(FIXED_UID)
        except BootstrapError:
            raise
        except Exception as exc:
            raise BootstrapDependencyError("bootstrap_incomplete") from exc
        return BootstrapResult("resumed")

    try:
        password = _read_password(password_reader)
    except BootstrapError:
        raise
    except Exception as exc:
        raise BootstrapInputError("password_input_failed") from exc
    try:
        try:
            identity = service.create_auth(
                uid=FIXED_UID,
                email=FIXED_EMAIL,
                display_name=FIXED_DISPLAY_NAME,
                password=password,
            )
        except Exception as exc:
            raise BootstrapDependencyError("auth_creation_failed") from exc
    finally:
        password = ""

    if identity.uid != FIXED_UID or identity.email != FIXED_EMAIL:
        raise BootstrapConflict("created_identity_conflict")
    try:
        service.ensure_inactive_profile(FIXED_UID)
        service.set_auth_disabled(FIXED_UID, False)
        service.activate_profile(FIXED_UID)
    except BootstrapError:
        raise
    except Exception as exc:
        raise BootstrapDependencyError("bootstrap_incomplete") from exc
    return BootstrapResult("created")


class FirebaseAdminBootstrapBackend:
    """Explicitly local Firebase Admin adapter, constructed only after validation."""

    def __init__(self) -> None:
        try:
            self._auth, self._db, self.server_timestamp = firebase_admin_clients()
        except Exception as exc:
            raise BootstrapDependencyError("dependency_unavailable") from exc

    @staticmethod
    def _missing_auth_error(exc: Exception) -> bool:
        return exc.__class__.__name__ in {"UserNotFoundError", "UserNotFound"}

    def get_auth_by_uid(self, uid: str) -> AuthRecord | None:
        try:
            record = self._auth.get_user(uid)
        except Exception as exc:
            if self._missing_auth_error(exc):
                return None
            raise
        return _auth_record(record)

    def get_auth_by_email(self, email: str) -> AuthRecord | None:
        try:
            record = self._auth.get_user_by_email(email)
        except Exception as exc:
            if self._missing_auth_error(exc):
                return None
            raise
        return _auth_record(record)

    def list_active_admin_uids(self) -> set[str]:
        result: set[str] = set()
        for snapshot in self._db.collection("users").stream():
            value = snapshot.to_dict() or {}
            if value.get("role") == "admin" and value.get("active") is True:
                result.add(snapshot.id)
        return result

    def get_profile(self, uid: str) -> dict[str, Any] | None:
        snapshot = self._db.collection("users").document(uid).get()
        return snapshot.to_dict() if snapshot.exists else None

    def create_auth(
        self,
        *,
        uid: str,
        email: str,
        display_name: str,
        password: str,
    ) -> AuthRecord:
        record = self._auth.create_user(
            uid=uid,
            email=email,
            display_name=display_name,
            password=password,
            disabled=True,
        )
        return _auth_record(record)

    def set_auth_disabled(self, uid: str, disabled: bool) -> None:
        self._auth.update_user(uid, disabled=disabled)

    def ensure_inactive_profile(self, uid: str) -> None:
        reference = self._db.collection("users").document(uid)
        document = {
            "email": FIXED_EMAIL,
            "displayName": FIXED_DISPLAY_NAME,
            "locale": FIXED_LOCALE,
            "role": FIXED_ROLE,
            "departmentId": None,
            "active": False,
            "accountState": "inactive_unverified",
            "createdAt": self.server_timestamp,
            "updatedAt": self.server_timestamp,
        }

        def operation(transaction: Any) -> None:
            snapshot = next(transaction.get(reference))
            if snapshot.exists:
                if not _profile_matches(snapshot.to_dict(), active=False):
                    raise BootstrapConflict("profile_conflict")
                return
            transaction.create(reference, document)

        run_firestore_transaction(self._db, operation)

    def activate_profile(self, uid: str) -> None:
        reference = self._db.collection("users").document(uid)

        def operation(transaction: Any) -> None:
            snapshot = next(transaction.get(reference))
            if not snapshot.exists or not _profile_matches(snapshot.to_dict()):
                raise BootstrapConflict("profile_conflict")
            if snapshot.to_dict().get("active") is True:
                return
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
    return AuthRecord(uid=uid, email=email, display_name=display_name, disabled=disabled)


def main() -> int:
    try:
        result = bootstrap_local_admin()
    except BootstrapError as exc:
        messages = {
            "environment_invalid": "Bootstrap conflict",
            "admin_already_exists": "Bootstrap conflict",
            "email_identity_conflict": "Bootstrap conflict",
            "fixed_identity_conflict": "Bootstrap conflict",
            "profile_conflict": "Bootstrap conflict",
            "profile_without_auth": "Bootstrap conflict",
            "enabled_partial_bootstrap": "Bootstrap conflict",
            "created_identity_conflict": "Bootstrap conflict",
            "password_mismatch": "Bootstrap incomplete",
            "password_weak": "Bootstrap incomplete",
            "password_input_failed": "Bootstrap incomplete",
            "auth_creation_failed": "Bootstrap incomplete",
            "bootstrap_incomplete": "Bootstrap incomplete",
            "dependency_unavailable": "Bootstrap incomplete",
            "identity_invalid": "Bootstrap incomplete",
        }
        print(messages.get(exc.code, "Bootstrap incomplete"))
        return 1
    print(
        {
            "created": "Admin created",
            "existing": "Existing Admin preserved",
            "resumed": "Partial bootstrap resumed",
        }.get(result.status, "Bootstrap incomplete")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
