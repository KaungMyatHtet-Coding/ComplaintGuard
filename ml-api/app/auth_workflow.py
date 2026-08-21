"""Trusted Firebase identity and Customer-profile completion workflow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.ticketing import (
    AuthenticationError,
    PersistenceError,
    firebase_admin_clients,
    run_firestore_transaction,
)


@dataclass(frozen=True)
class VerifiedFirebaseIdentity:
    """The only Firebase identity values used by public profile completion."""

    uid: str
    email: str


class CustomerProfileConflict(RuntimeError):
    """An existing profile is not a complete active Customer profile."""


class CustomerProfileBackend(Protocol):
    def verify_identity(self, token: str) -> VerifiedFirebaseIdentity: ...

    def complete_customer_profile(
        self,
        identity: VerifiedFirebaseIdentity,
        *,
        display_name: str,
        locale: str,
    ) -> tuple[str, dict[str, Any]]: ...


def _complete_customer_profile(
    value: Any,
    identity: VerifiedFirebaseIdentity,
) -> bool:
    if not isinstance(value, dict):
        return False
    return (
        value.get("email") == identity.email
        and isinstance(value.get("displayName"), str)
        and bool(value["displayName"].strip())
        and value.get("locale") in {"en", "my"}
        and value.get("role") == "customer"
        and value.get("departmentId") is None
        and value.get("active") is True
        and value.get("createdAt") is not None
        and value.get("updatedAt") is not None
    )


def _safe_profile(uid: str, value: dict[str, Any]) -> dict[str, Any]:
    return {
        "uid": uid,
        "email": value["email"],
        "displayName": value["displayName"].strip(),
        "locale": value["locale"],
        "role": "customer",
        "departmentId": None,
        "active": True,
    }


class FirebaseAdminCustomerProfileBackend:
    """Firebase Admin adapter restricted to the validated local Emulator."""

    def __init__(self, clients: tuple[Any, Any, object] | None = None) -> None:
        try:
            self._auth, self._db, self._server_timestamp = (
                clients or firebase_admin_clients()
            )
        except PersistenceError:
            raise
        except Exception as exc:
            raise PersistenceError("Firebase Admin is not configured") from exc

    def verify_identity(self, token: str) -> VerifiedFirebaseIdentity:
        try:
            decoded = self._auth.verify_id_token(token)
        except Exception as exc:
            raise AuthenticationError("Firebase ID token verification failed") from exc
        uid = decoded.get("uid")
        email = decoded.get("email")
        if not isinstance(uid, str) or not uid or not isinstance(email, str) or not email:
            raise AuthenticationError("verified Firebase identity is incomplete")
        return VerifiedFirebaseIdentity(uid=uid, email=email)

    def complete_customer_profile(
        self,
        identity: VerifiedFirebaseIdentity,
        *,
        display_name: str,
        locale: str,
    ) -> tuple[str, dict[str, Any]]:
        reference = self._db.collection("users").document(identity.uid)
        profile = {
            "email": identity.email,
            "displayName": display_name,
            "locale": locale,
            "role": "customer",
            "departmentId": None,
            "active": True,
            "createdAt": self._server_timestamp,
            "updatedAt": self._server_timestamp,
        }

        def operation(transaction: Any) -> tuple[str, dict[str, Any]]:
            snapshot = next(transaction.get(reference))
            if snapshot.exists:
                existing = snapshot.to_dict()
                if not _complete_customer_profile(existing, identity):
                    raise CustomerProfileConflict("existing profile cannot be completed")
                return "existing", _safe_profile(identity.uid, existing)
            transaction.create(reference, profile)
            return "created", _safe_profile(identity.uid, profile)

        try:
            return run_firestore_transaction(self._db, operation)
        except CustomerProfileConflict:
            raise
        except Exception as exc:
            raise PersistenceError("customer profile transaction failed") from exc
