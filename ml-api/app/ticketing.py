"""Trusted complaint submission and ticket lifecycle boundaries."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol, cast

from app.schemas import DepartmentId, SubmitComplaintRequest

DEPARTMENT_IDS = frozenset(DepartmentId.__args__)
INITIAL_STATUS = "submitted"
INITIAL_ROUTING_SOURCE = "pending"

_LABELED_SECRET = re.compile(r"(?i)\b(password|passcode|pin)\s*[:=\-]?\s*\S+")
_LABELED_ACCOUNT = re.compile(
    r"(?i)\b(account|card)(\s+(number|no\.?))?\s*[:=\-]?\s*[\d -]{6,23}"
)
_LONG_NUMBER = re.compile(r"(?<!\d)(?:\d[ -]?){8,19}(?!\d)")


class AuthenticationError(RuntimeError):
    """The Firebase ID token is missing or invalid."""


class PermissionError(RuntimeError):
    """The authenticated profile cannot submit complaints."""


class PersistenceError(RuntimeError):
    """Firestore could not create the ticket."""


class TicketBackend(Protocol):
    server_timestamp: object

    def verify_id_token(self, token: str) -> str: ...

    def get_user_profile(self, uid: str) -> dict[str, Any] | None: ...

    def create_ticket(self, document: dict[str, Any]) -> str: ...


def run_firestore_transaction(db: Any, operation: Any) -> Any:
    """Run a callable in a real Firestore transaction with SDK retries."""

    from google.cloud import firestore

    return firestore.transactional(operation)(db.transaction())


@dataclass(frozen=True)
class SubmissionResult:
    complaint_id: str
    status: str


def redact_sensitive_data(text: str) -> str:
    """Redact labeled secrets/account values and long payment-like numbers."""

    redacted = _LABELED_SECRET.sub(lambda match: f"{match.group(1)} [REDACTED]", text)
    redacted = _LABELED_ACCOUNT.sub(
        lambda match: f"{match.group(1)} [REDACTED]", redacted
    )
    return _LONG_NUMBER.sub("[REDACTED]", redacted)


def build_initial_ticket(
    *, customer_id: str, payload: SubmitComplaintRequest, server_timestamp: object
) -> dict[str, Any]:
    return {
        "customerId": customer_id,
        "complaintText": redact_sensitive_data(payload.complaint_text),
        "inputLocale": payload.input_locale,
        "departmentId": None,
        "assignedStaffId": None,
        "status": INITIAL_STATUS,
        "priority": "normal",
        "predictedDepartmentId": None,
        "predictionConfidence": None,
        "routingSource": INITIAL_ROUTING_SOURCE,
        "escalated": False,
        "resolutionSummary": None,
        "createdAt": server_timestamp,
        "updatedAt": server_timestamp,
        "resolvedAt": None,
    }


def validate_routing_state(
    *, department_id: str | None, status: str, routing_source: str
) -> None:
    """Enforce pending/null and routed/non-null ticket invariants."""

    if department_id is not None and department_id not in DEPARTMENT_IDS:
        raise ValueError("unknown department ID")
    pending = status == INITIAL_STATUS and routing_source == INITIAL_ROUTING_SOURCE
    if pending and department_id is not None:
        raise ValueError("pending ticket must not have a department")
    if not pending and department_id is None:
        raise ValueError("routed ticket requires a department")


class ComplaintSubmissionService:
    def __init__(self, backend: TicketBackend) -> None:
        self._backend = backend

    def submit(
        self, *, authorization: str | None, payload: SubmitComplaintRequest
    ) -> SubmissionResult:
        token = _bearer_token(authorization)
        try:
            customer_id = self._backend.verify_id_token(token)
        except Exception as exc:
            raise AuthenticationError("invalid Firebase ID token") from exc

        try:
            profile = self._backend.get_user_profile(customer_id)
        except Exception as exc:
            raise PersistenceError("profile lookup failed") from exc
        if not profile or profile.get("active") is not True:
            raise PermissionError("active customer profile required")
        if profile.get("role") != "customer":
            raise PermissionError("customer role required")

        document = build_initial_ticket(
            customer_id=customer_id,
            payload=payload,
            server_timestamp=self._backend.server_timestamp,
        )
        validate_routing_state(
            department_id=cast(str | None, document["departmentId"]),
            status=cast(str, document["status"]),
            routing_source=cast(str, document["routingSource"]),
        )
        try:
            complaint_id = self._backend.create_ticket(document)
        except Exception as exc:
            raise PersistenceError("ticket creation failed") from exc
        return SubmissionResult(complaint_id=complaint_id, status=INITIAL_STATUS)


def _bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise AuthenticationError("Firebase ID token required")
    scheme, separator, token = authorization.partition(" ")
    if separator != " " or scheme.lower() != "bearer" or not token.strip():
        raise AuthenticationError("Firebase ID token required")
    return token.strip()


class FirebaseAdminTicketBackend:
    """Firebase Admin adapter initialized from Application Default Credentials."""

    def __init__(self) -> None:
        try:
            import firebase_admin
            from firebase_admin import auth, firestore

            try:
                firebase_admin.get_app()
            except ValueError:
                firebase_admin.initialize_app()
            self._auth = auth
            self._db = firestore.client()
            self.server_timestamp = firestore.SERVER_TIMESTAMP
        except Exception as exc:
            raise PersistenceError("Firebase Admin is not configured") from exc

    def verify_id_token(self, token: str) -> str:
        decoded = self._auth.verify_id_token(token)
        uid = decoded.get("uid")
        if not isinstance(uid, str) or not uid:
            raise AuthenticationError("verified token has no UID")
        return uid

    def get_user_profile(self, uid: str) -> dict[str, Any] | None:
        snapshot = self._db.collection("users").document(uid).get()
        return snapshot.to_dict() if snapshot.exists else None

    def create_ticket(self, document: dict[str, Any]) -> str:
        reference = self._db.collection("tickets").document()
        reference.set(document)
        return reference.id
