"""Trusted active-Admin authorization for future administrative workflows."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from app.account_state import AccountStateValidationError, validate_account_state
from app.language import normalize_input
from app.ticketing import AuthenticationError, PersistenceError, firebase_admin_clients


class AdminPermissionError(RuntimeError):
    """The verified identity is not an active, valid application Admin."""


@dataclass(frozen=True)
class AdminPrincipal:
    """Minimum trusted identity needed by future Admin workflows."""

    uid: str
    email: str
    display_name: str
    locale: str
    role: Literal["admin"] = "admin"


class AdminAuthBackend(Protocol):
    def verify_id_token(self, token: str) -> dict[str, Any]: ...

    def get_user_profile(self, uid: str) -> dict[str, Any] | None: ...


_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise AuthenticationError("Firebase ID token required")
    scheme, separator, token = authorization.partition(" ")
    if separator != " " or scheme.lower() != "bearer" or not token.strip():
        raise AuthenticationError("Firebase ID token required")
    return token.strip()


def _valid_identity(decoded: Any) -> tuple[str, str]:
    if not isinstance(decoded, dict):
        raise AuthenticationError("invalid Firebase ID token")
    uid = decoded.get("uid")
    email = decoded.get("email")
    if (
        not isinstance(uid, str)
        or not uid.strip()
        or not isinstance(email, str)
        or not _EMAIL_PATTERN.fullmatch(email.strip())
    ):
        raise AuthenticationError("invalid Firebase ID token")
    return uid.strip(), email.strip()


def _valid_admin_profile(
    profile: Any,
    *,
    uid: str,
    email: str,
) -> AdminPrincipal | None:
    if not isinstance(profile, dict):
        return None
    profile_uid = profile.get("uid")
    display_name = profile.get("displayName")
    locale = profile.get("locale")
    if profile_uid is not None and profile_uid != uid:
        return None
    if (
        profile.get("email") != email
        or profile.get("role") != "admin"
        or profile.get("active") is not True
        or profile.get("departmentId") is not None
        or not isinstance(display_name, str)
        or not normalize_input(display_name)
        or locale not in {"en", "my"}
        or profile.get("createdAt") is None
        or profile.get("updatedAt") is None
    ):
        return None
    try:
        validate_account_state(
            active=profile.get("active"),
            role=profile.get("role"),
            account_state=profile.get("accountState"),
        )
    except AccountStateValidationError:
        return None
    return AdminPrincipal(
        uid=uid,
        email=email,
        display_name=normalize_input(display_name),
        locale=locale,
    )


def require_active_admin(
    authorization: str | None,
    backend: AdminAuthBackend,
) -> AdminPrincipal:
    """Authorize an active Admin without trusting request-supplied identity."""

    token = _bearer_token(authorization)
    try:
        decoded = backend.verify_id_token(token)
        uid, email = _valid_identity(decoded)
    except PersistenceError:
        raise PersistenceError("Admin authorization unavailable") from None
    except AuthenticationError:
        raise
    except Exception as exc:
        raise AuthenticationError("invalid Firebase ID token") from exc

    try:
        profile = backend.get_user_profile(uid)
    except Exception as exc:
        raise PersistenceError("profile lookup failed") from exc
    principal = _valid_admin_profile(profile, uid=uid, email=email)
    if principal is None:
        raise AdminPermissionError("active Admin profile required")
    return principal


class FirebaseAdminAuthBackend:
    """Local-only Firebase Admin adapter for the future Admin authorization path."""

    def __init__(self, clients: tuple[Any, Any, object] | None = None) -> None:
        try:
            self._auth, self._db, timestamp = clients or firebase_admin_clients()
            self._server_timestamp = timestamp
        except PersistenceError:
            raise
        except Exception as exc:
            raise PersistenceError("Firebase Admin is not configured") from exc

    def verify_id_token(self, token: str) -> dict[str, Any]:
        try:
            decoded = self._auth.verify_id_token(token)
        except Exception as exc:
            raise AuthenticationError("invalid Firebase ID token") from exc
        if not isinstance(decoded, dict):
            raise AuthenticationError("invalid Firebase ID token")
        return decoded

    def get_user_profile(self, uid: str) -> dict[str, Any] | None:
        try:
            snapshot = self._db.collection("users").document(uid).get()
        except Exception as exc:
            raise PersistenceError("profile lookup failed") from exc
        return snapshot.to_dict() if snapshot.exists else None
