"""Trusted complaint submission and ticket lifecycle boundaries."""

from __future__ import annotations

import hashlib
import logging
import os
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, cast

from app.schemas import DepartmentId, SubmitComplaintRequest

if TYPE_CHECKING:
    from app.routing import RoutingPrediction, TrustedRoutingInference

DEPARTMENT_IDS = frozenset(DepartmentId.__args__)
INITIAL_STATUS = "submitted"
INITIAL_ROUTING_SOURCE = "pending"
logger = logging.getLogger(__name__)

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

    def create_ticket(
        self, document: dict[str, Any], *, idempotency_key: str
    ) -> str: ...

    def persist_prediction(
        self, ticket_id: str, prediction: RoutingPrediction
    ) -> None: ...

    def persist_inference_failure(
        self, ticket_id: str, *, code: str, detected_language: str
    ) -> None: ...


def firebase_admin_clients() -> tuple[Any, Any, object]:
    """Create production clients or an explicitly isolated local-emulator pair."""

    import firebase_admin
    from firebase_admin import auth, firestore

    firestore_emulator = os.getenv("FIRESTORE_EMULATOR_HOST")
    auth_emulator = os.getenv("FIREBASE_AUTH_EMULATOR_HOST")
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCLOUD_PROJECT")
    if firestore_emulator or auth_emulator:
        if not firestore_emulator or not auth_emulator:
            raise PersistenceError("both Firebase emulators must be configured")
        if project_id != "demo-complaintguard":
            raise PersistenceError("emulators require the isolated demo project")
        try:
            firebase_admin.get_app()
        except ValueError:
            try:
                firebase_admin.initialize_app(options={"projectId": project_id})
            except ValueError:
                firebase_admin.get_app()
        from google.auth.credentials import AnonymousCredentials
        from google.cloud import firestore as google_firestore

        db = google_firestore.Client(
            project=project_id, credentials=AnonymousCredentials()
        )
        return auth, db, firestore.SERVER_TIMESTAMP

    try:
        firebase_admin.get_app()
    except ValueError:
        try:
            firebase_admin.initialize_app()
        except ValueError:
            firebase_admin.get_app()
    return auth, firestore.client(), firestore.SERVER_TIMESTAMP


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
    if routing_source == INITIAL_ROUTING_SOURCE and (
        status != INITIAL_STATUS or department_id is not None
    ):
        raise ValueError("pending ticket must not have a department")
    if routing_source == "manual_review" and department_id is not None:
        raise ValueError("manual-review ticket must not have a department")
    if routing_source in {"model", "manager_override"} and department_id is None:
        raise ValueError("routed ticket requires a department")


class ComplaintSubmissionService:
    def __init__(
        self,
        backend: TicketBackend,
        routing_inference: TrustedRoutingInference | None = None,
    ) -> None:
        self._backend = backend
        self._routing_inference = routing_inference

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
            logger.warning("profile lookup failed (%s)", type(exc).__name__)
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
            complaint_id = self._backend.create_ticket(
                document, idempotency_key=payload.action_id
            )
        except Exception as exc:
            logger.warning("ticket creation failed (%s)", type(exc).__name__)
            raise PersistenceError("ticket creation failed") from exc
        if self._routing_inference is not None:
            from app.routing import RoutingInferenceError

            try:
                prediction = self._routing_inference.predict(document["complaintText"])
                self._backend.persist_prediction(complaint_id, prediction)
            except RoutingInferenceError as exc:
                try:
                    self._backend.persist_inference_failure(
                        complaint_id,
                        code=exc.code,
                        detected_language=exc.detected_language,
                    )
                except PersistenceError:
                    # The original pending ticket is durable and recoverable.
                    logger.warning("inference failure state could not be persisted")
            except Exception:  # noqa: BLE001 - sanitize the inference boundary.
                # Prediction persistence failure must never lose or invent routing
                # for the already-created complaint.
                logger.warning("trusted inference failed unexpectedly")
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

    def __init__(self, db: Any = None) -> None:
        if db is not None:
            self._db = db
            from firebase_admin import firestore

            self.server_timestamp = firestore.SERVER_TIMESTAMP
            self._auth = None
            return
        try:
            self._auth, self._db, self.server_timestamp = firebase_admin_clients()
        except Exception as exc:
            logger.warning(
                "Firebase Admin ticket adapter initialization failed (%s)",
                type(exc).__name__,
            )
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

    def create_ticket(self, document: dict[str, Any], *, idempotency_key: str) -> str:
        digest = hashlib.sha256(
            f"{document['customerId']}:{idempotency_key}".encode()
        ).hexdigest()[:32]
        ticket_id = f"ticket_{digest}"
        reference = self._db.collection("tickets").document(ticket_id)

        def operation(transaction: Any) -> str:
            snapshot = next(transaction.get(reference))
            if snapshot.exists:
                existing = snapshot.to_dict()
                if existing.get("customerId") != document["customerId"]:
                    raise PersistenceError("submission ownership conflict")
                return ticket_id
            transaction.set(reference, document)
            return ticket_id

        try:
            return run_firestore_transaction(self._db, operation)
        except PersistenceError:
            raise
        except Exception as exc:
            raise PersistenceError("ticket creation transaction failed") from exc

    def persist_prediction(self, ticket_id: str, prediction: RoutingPrediction) -> None:
        reference = self._db.collection("tickets").document(ticket_id)
        event_reference = reference.collection("events").document("model_v1_routing")
        action_reference = reference.collection("actions").document("model_v1_routing")

        def operation(transaction: Any) -> None:
            action = next(transaction.get(action_reference))
            if action.exists:
                return
            snapshot = next(transaction.get(reference))
            if not snapshot.exists:
                raise PersistenceError("ticket disappeared before prediction")
            ticket = snapshot.to_dict()
            if ticket.get("routingSource") != "pending":
                return
            department_id = (
                None if prediction.requires_manual_review else prediction.department_id
            )
            routing_source = (
                "manual_review" if prediction.requires_manual_review else "model"
            )
            status = "submitted" if prediction.requires_manual_review else "triaged"
            updates = {
                "departmentId": department_id,
                "predictedDepartmentId": prediction.department_id,
                "predictionConfidence": prediction.confidence,
                "detectedLanguage": prediction.detected_language,
                "predictionModelVersion": prediction.model_version,
                "manualReviewReason": prediction.manual_review_reason,
                "routingSource": routing_source,
                "status": status,
                "updatedAt": self.server_timestamp,
            }
            validate_routing_state(
                department_id=department_id,
                status=status,
                routing_source=routing_source,
            )
            transaction.update(reference, updates)
            transaction.set(
                event_reference,
                {
                    "ticketId": ticket_id,
                    "type": "model_prediction",
                    "actorId": "trusted_ml_v1",
                    "actorRole": "system",
                    "fromValue": None,
                    "toValue": department_id,
                    "predictedDepartmentId": prediction.department_id,
                    "predictionConfidence": prediction.confidence,
                    "routingSource": routing_source,
                    "createdAt": self.server_timestamp,
                },
            )
            transaction.set(action_reference, {"type": "model_prediction"})

        try:
            run_firestore_transaction(self._db, operation)
        except PersistenceError:
            raise
        except Exception as exc:
            raise PersistenceError("prediction transaction failed") from exc

    def persist_inference_failure(
        self, ticket_id: str, *, code: str, detected_language: str
    ) -> None:
        reference = self._db.collection("tickets").document(ticket_id)
        action_reference = reference.collection("actions").document(
            "model_v1_inference_failure"
        )

        def operation(transaction: Any) -> None:
            action = next(transaction.get(action_reference))
            if action.exists:
                return
            snapshot = next(transaction.get(reference))
            if not snapshot.exists:
                raise PersistenceError("ticket disappeared before failure recording")
            if snapshot.to_dict().get("routingSource") != "pending":
                return
            transaction.update(
                reference,
                {
                    "departmentId": None,
                    "predictedDepartmentId": None,
                    "predictionConfidence": None,
                    "detectedLanguage": detected_language,
                    "manualReviewReason": code,
                    "routingSource": "manual_review",
                    "status": "submitted",
                    "updatedAt": self.server_timestamp,
                },
            )
            transaction.set(action_reference, {"type": "inference_failure"})

        try:
            run_firestore_transaction(self._db, operation)
        except PersistenceError:
            raise
        except Exception as exc:
            raise PersistenceError("inference failure transaction failed") from exc
