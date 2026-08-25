"""ComplaintGuard Day 11 FastAPI application."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Literal

from fastapi import Depends, FastAPI, Header, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.account_state import (
    AccountStateValidationError,
    validate_profile_account_state,
)
from app.admin_auth import AdminPermissionError, require_active_admin
from app.admin_directory import (
    AdminDirectoryBackend,
    AdminDirectoryService,
    DirectoryDataIntegrityError,
)
from app.admin_disable import (
    AdminDisableBackend,
    AdminDisableService,
    DisableAdminTarget,
    DisableAlreadyInactive,
    DisableAuthIdentityConflict,
    DisableAuthIdentityMissing,
    DisableAuthUnavailable,
    DisableIncomplete,
    DisableRevocationFailed,
    DisableSelfTarget,
    FirebaseAdminDisableBackend,
)
from app.admin_lifecycle import (
    LifecycleIdempotencyConflict,
    LifecycleOperatorRecoveryRequired,
    LifecycleRecoveryActorMismatch,
    LifecycleRecoveryNotFound,
    LifecycleRecoveryOperationMismatch,
    LifecycleStateConflict,
)
from app.admin_reactivate import (
    AdminReactivateBackend,
    AdminReactivateService,
    FirebaseAdminReactivationBackend,
    ReactivateAdminTarget,
    ReactivateAlreadyActive,
    ReactivateAuthIdentityConflict,
    ReactivateAuthIdentityMissing,
    ReactivateAuthUnavailable,
    ReactivateIncomplete,
    ReactivatePendingSetup,
    ReactivateSelfTarget,
)
from app.admin_reassign import (
    AdminReassignBackend,
    AdminReassignService,
    FirebaseAdminReassignmentBackend,
    ReassignAdminTarget,
    ReassignAssignedWork,
    ReassignPendingOrInactive,
    ReassignRoleNotReassignable,
    ReassignSameDepartment,
    ReassignScanIncomplete,
    ReassignSelfTarget,
)
from app.admin_recovery import (
    AdminLifecycleRecoveryBackend,
    AdminLifecycleRecoveryService,
    FirebaseAdminLifecycleRecoveryBackend,
    RecoveryAssignedWork,
    RecoveryLifecycleConflict,
)
from app.admin_recovery_status import (
    AdminLifecycleRecoveryStatusBackend,
    AdminLifecycleRecoveryStatusService,
)
from app.admin_workflow import (
    AdminProvisioningBackend,
    AdminProvisioningService,
    FirebaseAdminProvisioningBackend,
    ProvisioningEmailExists,
    ProvisioningIdempotencyConflict,
    ProvisioningIncomplete,
    ProvisioningProfileConflict,
)
from app.auth_workflow import (
    CustomerProfileBackend,
    CustomerProfileConflict,
    FirebaseAdminCustomerProfileBackend,
)
from app.config import MODEL_VERSION, Settings
from app.customer_workflow import (
    CUSTOMER_HISTORY_DEFAULT_PAGE_SIZE,
    CUSTOMER_HISTORY_DEPARTMENTS,
    CUSTOMER_HISTORY_MAX_PAGE_SIZE,
    CUSTOMER_HISTORY_STATUSES,
    CustomerBackend,
    CustomerHistoryCursorError,
    CustomerHistoryFilters,
    CustomerWorkflowService,
    FeedbackAlreadySubmitted,
    FirebaseAdminCustomerBackend,
    InvalidTicketState,
    TicketNotFound,
    decode_customer_history_cursor,
)
from app.language import detect_language
from app.manager_workflow import (
    FirebaseAdminManagerBackend,
    ManagerBackend,
    ManagerWorkflowService,
)
from app.manager_workflow import (
    InvalidDepartmentError as ManagerInvalidDeptError,
)
from app.manager_workflow import (
    TicketNotFound as ManagerTicketNotFound,
)
from app.model import FrozenDepartmentClassifier, ModelArtifactError
from app.notifications import (
    FirebaseAdminNotificationBackend,
    NotificationBackend,
    NotificationNotFoundError,
    NotificationProfileError,
    NotificationService,
    NotificationValidationError,
    require_active_notification_profile,
)
from app.routing import OfflineMyanmarTranslator, TrustedRoutingInference
from app.schemas import (
    AdminDirectoryRequest,
    AdminDirectoryResponse,
    AdminDisableRequest,
    AdminDisableResponse,
    AdminLifecycleEligibilityResponse,
    AdminLifecycleRecoveryRequest,
    AdminLifecycleRecoveryResponse,
    AdminLifecycleRecoveryStatusResponse,
    AdminProvisioningRequest,
    AdminProvisioningResponse,
    AdminReactivateRequest,
    AdminReactivateResponse,
    AdminReassignDepartmentRequest,
    AdminReassignDepartmentResponse,
    CustomerFeedbackRequest,
    CustomerFeedbackResponse,
    CustomerMessageItem,
    CustomerMessageRequest,
    CustomerProfileRequest,
    CustomerProfileResponse,
    CustomerTicketDetail,
    CustomerTicketListResponse,
    ErrorDetail,
    ErrorResponse,
    HealthResponse,
    LowConfidenceTicketItem,
    ManagerAnalyticsResponse,
    ManagerOverrideRequest,
    ManagerOverrideResponse,
    NotificationItem,
    NotificationListResponse,
    NotificationReadAllResponse,
    NotificationReadResponse,
    NotificationUnreadCountResponse,
    PredictRequest,
    PredictResponse,
    StaffMutationResponse,
    StaffReplyRequest,
    StaffRequestAction,
    StaffTicketDetail,
    StaffTicketListResponse,
    StaffTicketSummary,
    StaffTransitionRequest,
    SubmitComplaintRequest,
    SubmitComplaintResponse,
)
from app.staff_workflow import (
    FirebaseAdminStaffBackend,
    InvalidTransition,
    StaffActor,
    StaffBackend,
    StaffTicketNotFound,
    StaffWorkflowService,
)
from app.ticketing import (
    AuthenticationError,
    ComplaintSubmissionService,
    FirebaseAdminTicketBackend,
    PersistenceError,
    TicketBackend,
)
from app.ticketing import PermissionError as SubmissionPermissionError

ModelLoader = Callable[..., FrozenDepartmentClassifier]


class ApiError(RuntimeError):
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or []


def _persisted_profile_state_is_valid(profile: Any) -> bool:
    try:
        validate_profile_account_state(profile)
    except (AccountStateValidationError, AttributeError):
        return False
    return True


def _error_payload(
    code: str,
    message: str,
    details: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    response = ErrorResponse(
        error={
            "code": code,
            "message": message,
            "details": details or [],
        }
    )
    return response.model_dump(mode="json")


def create_app(
    *,
    settings: Settings | None = None,
    model_loader: ModelLoader = FrozenDepartmentClassifier.load,
    ticket_backend: TicketBackend | None = None,
    staff_backend: StaffBackend | None = None,
    customer_backend: CustomerBackend | None = None,
    manager_backend: ManagerBackend | None = None,
    customer_profile_backend: CustomerProfileBackend | None = None,
    admin_provisioning_backend: AdminProvisioningBackend | None = None,
    admin_directory_backend: AdminDirectoryBackend | None = None,
    admin_disable_backend: AdminDisableBackend | None = None,
    admin_reactivate_backend: AdminReactivateBackend | None = None,
    admin_reassign_backend: AdminReassignBackend | None = None,
    admin_recovery_backend: AdminLifecycleRecoveryBackend | None = None,
    admin_recovery_status_backend: AdminLifecycleRecoveryStatusBackend | None = None,
    notification_backend: NotificationBackend | None = None,
) -> FastAPI:
    runtime_settings = settings or Settings.default()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.classifier = None
        app.state.routing_inference = None
        app.state.model_error_code = None
        try:
            app.state.classifier = model_loader(
                runtime_settings.model_path,
                expected_sha256=runtime_settings.expected_model_sha256,
            )
            app.state.routing_inference = TrustedRoutingInference(
                app.state.classifier,
                confidence_threshold=runtime_settings.routing_confidence_threshold,
                translator=OfflineMyanmarTranslator(),
            )
        except (ModelArtifactError, OSError, ValueError, TypeError):
            app.state.model_error_code = "model_unavailable"
        yield
        app.state.routing_inference = None
        app.state.classifier = None

    api = FastAPI(
        title="ComplaintGuard ML API",
        version="1.0.0",
        description=(
            "Local inference for the frozen English TF-IDF/MultinomialNB model. "
            "Myanmar translation remains a development baseline and is not approved."
        ),
        lifespan=lifespan,
    )
    api.add_middleware(
        CORSMiddleware,
        allow_origins=list(runtime_settings.allowed_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @api.exception_handler(ApiError)
    async def api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(exc.code, exc.message, exc.details),
        )

    @api.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        details = []
        for error in exc.errors():
            location = [str(value) for value in error.get("loc", ()) if value != "body"]
            details.append(
                ErrorDetail(
                    field=".".join(location) or None,
                    type=str(error.get("type", "validation_error")),
                ).model_dump(mode="json")
            )
        return JSONResponse(
            status_code=422,
            content=_error_payload(
                "request_validation_error",
                "Request validation failed.",
                details,
            ),
        )

    @api.get("/health", response_model=HealthResponse)
    async def health(request: Request) -> HealthResponse:
        loaded = request.app.state.classifier is not None
        return HealthResponse(
            status="ok" if loaded else "degraded",
            service="complaintguard-ml-api",
            model_loaded=loaded,
            model_version=MODEL_VERSION if loaded else None,
            supported_prediction_languages=["en"],
            myanmar_readiness="development_baseline_not_approved",
        )

    @api.post(
        "/predict",
        response_model=PredictResponse,
        responses={
            422: {"model": ErrorResponse},
            503: {"model": ErrorResponse},
        },
    )
    async def predict(
        payload: PredictRequest,
        request: Request,
    ) -> PredictResponse:
        language = detect_language(payload.text)
        if language != "en":
            raise ApiError(
                status_code=422,
                code=(
                    "myanmar_not_production_ready"
                    if language in {"my", "mixed"}
                    else "unsupported_input"
                ),
                message=(
                    "Myanmar translation is not approved for production prediction."
                    if language in {"my", "mixed"}
                    else "Complaint text must contain supported English letters."
                ),
                details=[{"detected_language": language}],
            )
        classifier = request.app.state.classifier
        if classifier is None:
            raise ApiError(
                status_code=503,
                code="model_unavailable",
                message="The prediction model is unavailable.",
            )
        try:
            prediction = classifier.predict(payload.text)
        except (ModelArtifactError, ValueError, TypeError):
            raise ApiError(
                status_code=503,
                code="prediction_unavailable",
                message="Prediction could not be completed.",
            ) from None
        return PredictResponse(
            department_id=prediction.department_id,
            confidence=prediction.confidence,
            detected_language="en",
            model_version=classifier.model_version,
            fallback=prediction.fallback,
            fallback_reason=prediction.fallback_reason,
        )

    @api.post(
        "/auth/customer-profile",
        response_model=CustomerProfileResponse,
        response_model_by_alias=True,
        responses={401: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    )
    async def complete_customer_profile(
        payload: CustomerProfileRequest,
        response: Response,
        authorization: str | None = Header(default=None),
    ) -> CustomerProfileResponse:
        if not authorization or not authorization.startswith("Bearer "):
            raise ApiError(
                status_code=401,
                code="authentication_required",
                message="A valid Firebase ID token is required.",
            )
        token = authorization.split(" ", 1)[1].strip()
        if not token:
            raise ApiError(
                status_code=401,
                code="authentication_required",
                message="A valid Firebase ID token is required.",
            )
        try:
            backend = customer_profile_backend or FirebaseAdminCustomerProfileBackend()
        except PersistenceError:
            raise ApiError(
                status_code=503,
                code="customer_profile_unavailable",
                message="Account setup is temporarily unavailable. Try again.",
            ) from None
        try:
            identity = backend.verify_identity(token)
        except AuthenticationError:
            raise ApiError(
                status_code=401,
                code="authentication_required",
                message="A valid Firebase ID token is required.",
            ) from None
        except Exception:  # noqa: BLE001 -- SDK errors are not stable types
            raise ApiError(
                status_code=401,
                code="authentication_required",
                message="A valid Firebase ID token is required.",
            ) from None
        try:
            status, profile = backend.complete_customer_profile(
                identity,
                display_name=payload.display_name,
                locale=payload.locale,
            )
        except CustomerProfileConflict:
            raise ApiError(
                status_code=409,
                code="profile_conflict",
                message="This account requires support.",
            ) from None
        except PersistenceError:
            raise ApiError(
                status_code=503,
                code="customer_profile_unavailable",
                message="Account setup is temporarily unavailable. Try again.",
            ) from None
        response.status_code = 201 if status == "created" else 200
        return CustomerProfileResponse(status=status, profile=profile)

    @api.post(
        "/admin/users",
        response_model=AdminProvisioningResponse,
        response_model_by_alias=True,
        responses={
            401: {"model": ErrorResponse},
            403: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
            503: {"model": ErrorResponse},
        },
    )
    async def provision_admin_user(
        payload: AdminProvisioningRequest,
        response: Response,
        authorization: str | None = Header(default=None),
    ) -> AdminProvisioningResponse:
        if not authorization or not authorization.startswith("Bearer "):
            raise ApiError(
                status_code=401,
                code="authentication_required",
                message="A valid Firebase ID token is required.",
            )
        if not authorization.split(" ", 1)[1].strip():
            raise ApiError(
                status_code=401,
                code="authentication_required",
                message="A valid Firebase ID token is required.",
            )
        try:
            backend = admin_provisioning_backend or FirebaseAdminProvisioningBackend()
        except PersistenceError:
            raise ApiError(
                status_code=503,
                code="service_unavailable",
                message="Account provisioning is temporarily unavailable.",
            ) from None
        try:
            actor = require_active_admin(authorization, backend)
        except AuthenticationError:
            raise ApiError(
                status_code=401,
                code="authentication_required",
                message="A valid Firebase ID token is required.",
            ) from None
        except AdminPermissionError:
            raise ApiError(
                status_code=403,
                code="admin_required",
                message="Active administrative access is required.",
            ) from None
        except PersistenceError:
            raise ApiError(
                status_code=503,
                code="service_unavailable",
                message="Account provisioning is temporarily unavailable.",
            ) from None
        try:
            result = AdminProvisioningService(backend).provision(actor, payload)
        except ProvisioningEmailExists:
            raise ApiError(
                status_code=409,
                code="email_exists",
                message="That email address is already in use.",
            ) from None
        except ProvisioningProfileConflict:
            raise ApiError(
                status_code=409,
                code="profile_conflict",
                message="The account profile requires support.",
            ) from None
        except ProvisioningIdempotencyConflict:
            raise ApiError(
                status_code=409,
                code="idempotency_conflict",
                message="This request key was already used for different details.",
            ) from None
        except ProvisioningIncomplete:
            raise ApiError(
                status_code=503,
                code="provisioning_incomplete",
                message="Account setup is temporarily incomplete. Try again.",
            ) from None
        except PersistenceError:
            raise ApiError(
                status_code=503,
                code="service_unavailable",
                message="Account provisioning is temporarily unavailable.",
            ) from None
        response.status_code = 201 if result.created else 200
        return AdminProvisioningResponse(
            status=result.status,
            uid=result.identity.uid,
            email=result.identity.email,
            displayName=result.identity.display_name,
            locale=result.request.locale,
            role=result.request.role,
            departmentId=result.request.department_id,
            active=False,
            setupRequired=True,
        )

    @api.get(
        "/admin/users",
        response_model=AdminDirectoryResponse,
        response_model_by_alias=True,
        responses={
            401: {"model": ErrorResponse},
            403: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
            503: {"model": ErrorResponse},
        },
    )
    async def list_admin_users(
        request: Request,
        payload: AdminDirectoryRequest = Depends(),  # noqa: B008 - FastAPI dependency marker.
        authorization: str | None = Header(default=None),
    ) -> AdminDirectoryResponse:
        if set(request.query_params) - {"role", "departmentId", "active", "search", "pageSize", "cursor"}:
            raise ApiError(
                status_code=422,
                code="validation_error",
                message="The directory filters are invalid.",
            )
        if not authorization or not authorization.startswith("Bearer "):
            raise ApiError(
                status_code=401,
                code="authentication_required",
                message="A valid Firebase ID token is required.",
            )
        if not authorization.split(" ", 1)[1].strip():
            raise ApiError(
                status_code=401,
                code="authentication_required",
                message="A valid Firebase ID token is required.",
            )
        try:
            backend = (
                admin_directory_backend
                or admin_provisioning_backend
                or admin_reactivate_backend
                or admin_reassign_backend
                or FirebaseAdminReactivationBackend()
            )
            require_active_admin(authorization, backend)
        except AuthenticationError:
            raise ApiError(
                status_code=401,
                code="authentication_required",
                message="A valid Firebase ID token is required.",
            ) from None
        except AdminPermissionError:
            raise ApiError(
                status_code=403,
                code="admin_required",
                message="Active administrative access is required.",
            ) from None
        except PersistenceError:
            raise ApiError(
                status_code=503,
                code="service_unavailable",
                message="The account directory is temporarily unavailable.",
            ) from None

        try:
            return AdminDirectoryService(backend).list_users(payload)
        except ValueError:
            raise ApiError(
                status_code=422,
                code="validation_error",
                message="The directory filters are invalid.",
            ) from None
        except DirectoryDataIntegrityError:
            raise ApiError(
                status_code=503,
                code="directory_data_integrity",
                message="The account directory is temporarily unavailable.",
            ) from None
        except PersistenceError:
            raise ApiError(
                status_code=503,
                code="service_unavailable",
                message="The account directory is temporarily unavailable.",
            ) from None

    @api.get(
        "/admin/users/{account_ref}/lifecycle-eligibility",
        response_model=AdminLifecycleEligibilityResponse,
        response_model_by_alias=True,
        responses={
            401: {"model": ErrorResponse},
            403: {"model": ErrorResponse},
            404: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
            503: {"model": ErrorResponse},
        },
    )
    async def get_admin_lifecycle_eligibility(
        account_ref: str,
        authorization: str | None = Header(default=None),
    ) -> AdminLifecycleEligibilityResponse:
        if not authorization or not authorization.startswith("Bearer "):
            raise ApiError(
                status_code=401,
                code="authentication_required",
                message="A valid Firebase ID token is required.",
            )
        if not authorization.split(" ", 1)[1].strip():
            raise ApiError(
                status_code=401,
                code="authentication_required",
                message="A valid Firebase ID token is required.",
            )
        try:
            backend = (
                admin_directory_backend
                or admin_provisioning_backend
                or admin_reactivate_backend
                or admin_reassign_backend
                or FirebaseAdminReactivationBackend()
            )
            actor = require_active_admin(authorization, backend)
        except AuthenticationError:
            raise ApiError(
                status_code=401,
                code="authentication_required",
                message="A valid Firebase ID token is required.",
            ) from None
        except AdminPermissionError:
            raise ApiError(
                status_code=403,
                code="admin_required",
                message="Active administrative access is required.",
            ) from None
        except PersistenceError:
            raise ApiError(
                status_code=503,
                code="service_unavailable",
                message="The lifecycle check is temporarily unavailable.",
            ) from None

        try:
            return AdminDirectoryService(backend).lifecycle_eligibility(
                actor.uid,
                account_ref,
            )
        except ValueError:
            raise ApiError(
                status_code=422,
                code="validation_error",
                message="The account reference is invalid.",
            ) from None
        except LookupError:
            raise ApiError(
                status_code=404,
                code="account_not_found",
                message="The account was not found.",
            ) from None
        except DirectoryDataIntegrityError:
            raise ApiError(
                status_code=503,
                code="directory_data_integrity",
                message="The lifecycle check is temporarily unavailable.",
            ) from None
        except PersistenceError:
            raise ApiError(
                status_code=503,
                code="service_unavailable",
                message="The lifecycle check is temporarily unavailable.",
            ) from None

    @api.get(
        "/admin/users/{account_ref}/lifecycle-recovery-status",
        response_model=AdminLifecycleRecoveryStatusResponse,
        response_model_by_alias=True,
        responses={
            401: {"model": ErrorResponse},
            403: {"model": ErrorResponse},
            404: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
            503: {"model": ErrorResponse},
        },
    )
    async def get_admin_lifecycle_recovery_status(
        account_ref: str,
        authorization: str | None = Header(default=None),
    ) -> AdminLifecycleRecoveryStatusResponse:
        if not authorization or not authorization.startswith("Bearer "):
            raise ApiError(
                status_code=401,
                code="authentication_required",
                message="A valid Firebase ID token is required.",
            )
        if not authorization.split(" ", 1)[1].strip():
            raise ApiError(
                status_code=401,
                code="authentication_required",
                message="A valid Firebase ID token is required.",
            )
        try:
            backend = (
                admin_recovery_status_backend
                or admin_recovery_backend
                or FirebaseAdminLifecycleRecoveryBackend()
            )
            actor = require_active_admin(authorization, backend)
        except AuthenticationError:
            raise ApiError(
                status_code=401,
                code="authentication_required",
                message="A valid Firebase ID token is required.",
            ) from None
        except AdminPermissionError:
            raise ApiError(
                status_code=403,
                code="admin_required",
                message="Active administrative access is required.",
            ) from None
        except PersistenceError:
            raise ApiError(
                status_code=503,
                code="service_unavailable",
                message="Lifecycle recovery status is temporarily unavailable.",
            ) from None

        try:
            return AdminLifecycleRecoveryStatusService(
                backend  # type: ignore[arg-type]
            ).status(actor, account_ref=account_ref)
        except ValueError:
            raise ApiError(
                status_code=422,
                code="validation_error",
                message="The account reference is invalid.",
            ) from None
        except LookupError:
            raise ApiError(
                status_code=404,
                code="account_not_found",
                message="The account was not found.",
            ) from None
        except PersistenceError:
            raise ApiError(
                status_code=503,
                code="service_unavailable",
                message="Lifecycle recovery status is temporarily unavailable.",
            ) from None

    @api.post(
        "/admin/users/{account_ref}/reactivate",
        response_model=AdminReactivateResponse,
        response_model_by_alias=True,
        responses={
            401: {"model": ErrorResponse},
            403: {"model": ErrorResponse},
            404: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
            503: {"model": ErrorResponse},
        },
    )
    async def reactivate_admin_account(
        account_ref: str,
        payload: AdminReactivateRequest,
        authorization: str | None = Header(default=None),
    ) -> AdminReactivateResponse:
        if not authorization or not authorization.startswith("Bearer ") or not authorization.split(" ", 1)[1].strip():
            raise ApiError(status_code=401, code="authentication_required", message="A valid Firebase ID token is required.")
        try:
            backend = admin_reactivate_backend or FirebaseAdminReactivationBackend()
            actor = require_active_admin(authorization, backend)
        except AuthenticationError:
            raise ApiError(status_code=401, code="authentication_required", message="A valid Firebase ID token is required.") from None
        except AdminPermissionError:
            raise ApiError(status_code=403, code="admin_required", message="Active administrative access is required.") from None
        except PersistenceError:
            raise ApiError(status_code=503, code="service_unavailable", message="Account reactivation is temporarily unavailable.") from None
        try:
            return AdminReactivateService(backend).reactivate(
                actor, account_ref=account_ref, idempotency_key=payload.idempotency_key
            )
        except ValueError:
            raise ApiError(status_code=422, code="invalid_request", message="The account reference or request is invalid.") from None
        except ReactivateAdminTarget:
            raise ApiError(status_code=409, code="admin_reactivate_not_available", message="This account operation is not available.") from None
        except ReactivateSelfTarget:
            raise ApiError(status_code=409, code="lifecycle_conflict", message="This account operation is not available.") from None
        except ReactivateAlreadyActive:
            raise ApiError(status_code=409, code="already_active", message="The account is already active.") from None
        except ReactivatePendingSetup:
            raise ApiError(status_code=409, code="pending_setup_activation_forbidden", message="This account is not eligible for reactivation.") from None
        except LookupError:
            raise ApiError(status_code=404, code="account_not_found", message="The account was not found.") from None
        except LifecycleIdempotencyConflict:
            raise ApiError(status_code=409, code="idempotency_conflict", message="This request key was already used for different details.") from None
        except LifecycleStateConflict:
            raise ApiError(status_code=409, code="lifecycle_conflict", message="The account operation cannot proceed safely.") from None
        except (ReactivateAuthIdentityMissing, ReactivateAuthIdentityConflict, ReactivateAuthUnavailable, ReactivateIncomplete):
            raise ApiError(status_code=503, code="lifecycle_incomplete", message="Account reactivation is temporarily incomplete. Try again.") from None
        except PersistenceError:
            raise ApiError(status_code=503, code="service_unavailable", message="Account reactivation is temporarily unavailable.") from None

    @api.post(
        "/admin/users/{account_ref}/disable",
        response_model=AdminDisableResponse,
        response_model_by_alias=True,
        responses={
            401: {"model": ErrorResponse},
            403: {"model": ErrorResponse},
            404: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
            503: {"model": ErrorResponse},
        },
    )
    async def disable_admin_account(
        account_ref: str,
        payload: AdminDisableRequest,
        authorization: str | None = Header(default=None),
    ) -> AdminDisableResponse:
        if not authorization or not authorization.startswith("Bearer ") or not authorization.split(" ", 1)[1].strip():
            raise ApiError(
                status_code=401,
                code="authentication_required",
                message="A valid Firebase ID token is required.",
            )
        try:
            backend = admin_disable_backend or FirebaseAdminDisableBackend()
            actor = require_active_admin(authorization, backend)
        except AuthenticationError:
            raise ApiError(status_code=401, code="authentication_required", message="A valid Firebase ID token is required.") from None
        except AdminPermissionError:
            raise ApiError(status_code=403, code="admin_required", message="Active administrative access is required.") from None
        except PersistenceError:
            raise ApiError(status_code=503, code="service_unavailable", message="Account disablement is temporarily unavailable.") from None

        try:
            return AdminDisableService(backend).disable(
                actor, account_ref=account_ref, idempotency_key=payload.idempotency_key
            )
        except ValueError:
            raise ApiError(status_code=422, code="invalid_request", message="The account reference or request is invalid.") from None
        except DisableAdminTarget:
            raise ApiError(status_code=409, code="admin_disable_not_available", message="This account operation is not available.") from None
        except DisableSelfTarget:
            raise ApiError(status_code=409, code="lifecycle_conflict", message="This account operation is not available.") from None
        except DisableAlreadyInactive:
            raise ApiError(status_code=409, code="already_inactive", message="The account is already inactive.") from None
        except LookupError:
            raise ApiError(status_code=404, code="account_not_found", message="The account was not found.") from None
        except LifecycleIdempotencyConflict:
            raise ApiError(status_code=409, code="idempotency_conflict", message="This request key was already used for different details.") from None
        except LifecycleStateConflict:
            raise ApiError(status_code=409, code="lifecycle_conflict", message="The account operation cannot proceed safely.") from None
        except (DisableAuthIdentityMissing, DisableAuthIdentityConflict, DisableAuthUnavailable, DisableRevocationFailed, DisableIncomplete):
            raise ApiError(status_code=503, code="lifecycle_incomplete", message="Account disablement is temporarily incomplete. Try again.") from None
        except DirectoryDataIntegrityError:
            raise ApiError(status_code=503, code="service_unavailable", message="Account disablement is temporarily unavailable.") from None
        except PersistenceError:
            raise ApiError(status_code=503, code="service_unavailable", message="Account disablement is temporarily unavailable.") from None

    @api.post(
        "/admin/users/{account_ref}/reassign-department",
        response_model=AdminReassignDepartmentResponse,
        response_model_by_alias=True,
        responses={
            401: {"model": ErrorResponse},
            403: {"model": ErrorResponse},
            404: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
            503: {"model": ErrorResponse},
        },
    )
    async def reassign_admin_staff_department(
        account_ref: str,
        payload: AdminReassignDepartmentRequest,
        authorization: str | None = Header(default=None),
    ) -> AdminReassignDepartmentResponse:
        if not authorization or not authorization.startswith("Bearer ") or not authorization.split(" ", 1)[1].strip():
            raise ApiError(status_code=401, code="authentication_required", message="A valid Firebase ID token is required.")
        try:
            backend = admin_reassign_backend or FirebaseAdminReassignmentBackend()
            actor = require_active_admin(authorization, backend)
        except AuthenticationError:
            raise ApiError(status_code=401, code="authentication_required", message="A valid Firebase ID token is required.") from None
        except AdminPermissionError:
            raise ApiError(status_code=403, code="admin_required", message="Active administrative access is required.") from None
        except PersistenceError:
            raise ApiError(status_code=503, code="service_unavailable", message="Department reassignment is temporarily unavailable.") from None
        try:
            return AdminReassignService(backend).reassign(
                actor,
                account_ref=account_ref,
                idempotency_key=payload.idempotency_key,
                department_id=payload.department_id,
            )
        except ValueError:
            raise ApiError(status_code=422, code="invalid_request", message="The account reference or request is invalid.") from None
        except ReassignAdminTarget:
            raise ApiError(status_code=409, code="admin_reassign_not_available", message="This account operation is not available.") from None
        except ReassignSelfTarget:
            raise ApiError(status_code=409, code="lifecycle_conflict", message="This account operation is not available.") from None
        except LookupError:
            raise ApiError(status_code=404, code="account_not_found", message="The account was not found.") from None
        except ReassignPendingOrInactive:
            raise ApiError(status_code=409, code="role_not_reassignable", message="Only active Staff accounts can be reassigned.") from None
        except ReassignRoleNotReassignable:
            raise ApiError(status_code=409, code="role_not_reassignable", message="This account role cannot be reassigned.") from None
        except ReassignSameDepartment:
            raise ApiError(status_code=409, code="department_unchanged", message="The Staff account is already in that department.") from None
        except ReassignAssignedWork:
            raise ApiError(status_code=409, code="assigned_unresolved_work", message="The Staff account has unresolved assigned work.") from None
        except LifecycleIdempotencyConflict:
            raise ApiError(status_code=409, code="idempotency_conflict", message="This request key was already used for different details.") from None
        except LifecycleStateConflict:
            raise ApiError(status_code=409, code="lifecycle_conflict", message="The account operation cannot proceed safely.") from None
        except ReassignScanIncomplete:
            raise ApiError(status_code=503, code="bounded_scan_incomplete", message="Department reassignment is temporarily unavailable.") from None
        except DirectoryDataIntegrityError:
            raise ApiError(status_code=503, code="service_unavailable", message="Department reassignment is temporarily unavailable.") from None
        except PersistenceError:
            raise ApiError(status_code=503, code="service_unavailable", message="Department reassignment is temporarily unavailable.") from None

    @api.post(
        "/admin/users/{account_ref}/lifecycle-recovery",
        response_model=AdminLifecycleRecoveryResponse,
        response_model_by_alias=True,
        responses={
            401: {"model": ErrorResponse},
            403: {"model": ErrorResponse},
            404: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
            503: {"model": ErrorResponse},
        },
    )
    async def recover_admin_lifecycle(
        account_ref: str,
        payload: AdminLifecycleRecoveryRequest,
        authorization: str | None = Header(default=None),
    ) -> AdminLifecycleRecoveryResponse:
        if not authorization or not authorization.startswith("Bearer ") or not authorization.split(" ", 1)[1].strip():
            raise ApiError(status_code=401, code="authentication_required", message="A valid Firebase ID token is required.")
        try:
            backend = admin_recovery_backend or FirebaseAdminLifecycleRecoveryBackend()
            actor = require_active_admin(authorization, backend)
        except AuthenticationError:
            raise ApiError(status_code=401, code="authentication_required", message="A valid Firebase ID token is required.") from None
        except AdminPermissionError:
            raise ApiError(status_code=403, code="admin_required", message="Active administrative access is required.") from None
        except PersistenceError:
            raise ApiError(status_code=503, code="service_unavailable", message="Lifecycle recovery is temporarily unavailable.") from None
        department_id = getattr(payload, "department_id", None)
        try:
            return AdminLifecycleRecoveryService(backend).recover(
                actor,
                account_ref=account_ref,
                operation=payload.operation,
                department_id=department_id,
            )
        except ValueError:
            raise ApiError(status_code=422, code="invalid_request", message="The account reference or recovery request is invalid.") from None
        except LifecycleRecoveryActorMismatch:
            raise ApiError(status_code=403, code="recovery_actor_mismatch", message="This recovery request is not available.") from None
        except LifecycleRecoveryNotFound:
            raise ApiError(status_code=404, code="account_or_recovery_not_found", message="The account recovery was not found.") from None
        except LifecycleRecoveryOperationMismatch:
            raise ApiError(status_code=409, code="recovery_operation_mismatch", message="The recovery request does not match the existing operation.") from None
        except RecoveryAssignedWork:
            raise ApiError(status_code=409, code="assigned_unresolved_work", message="The existing reassignment is blocked by unresolved assigned work.") from None
        except RecoveryLifecycleConflict:
            raise ApiError(status_code=409, code="lifecycle_conflict", message="The existing lifecycle operation is in conflict.") from None
        except LifecycleOperatorRecoveryRequired:
            raise ApiError(status_code=409, code="operator_recovery_required", message="Operator recovery is required for this lifecycle operation.") from None
        except LifecycleStateConflict:
            raise ApiError(status_code=409, code="lifecycle_conflict", message="The lifecycle operation cannot proceed safely.") from None
        except (DisableIncomplete, ReactivateIncomplete):
            raise ApiError(status_code=503, code="lifecycle_incomplete", message="Lifecycle recovery is temporarily incomplete. Try again.") from None
        except ReassignScanIncomplete:
            raise ApiError(status_code=503, code="bounded_scan_incomplete", message="Lifecycle recovery is temporarily unavailable.") from None
        except LookupError:
            raise ApiError(status_code=404, code="account_or_recovery_not_found", message="The account recovery was not found.") from None
        except PersistenceError:
            raise ApiError(status_code=503, code="service_unavailable", message="Lifecycle recovery is temporarily unavailable.") from None
    @api.post(
        "/tickets",
        response_model=SubmitComplaintResponse,
        response_model_by_alias=True,
        status_code=201,
        responses={
            401: {"model": ErrorResponse},
            403: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
            503: {"model": ErrorResponse},
        },
    )
    async def submit_complaint(
        payload: SubmitComplaintRequest,
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> SubmitComplaintResponse:
        try:
            backend = ticket_backend or FirebaseAdminTicketBackend()
            result = ComplaintSubmissionService(
                backend,
                routing_inference=request.app.state.routing_inference,
            ).submit(
                authorization=authorization,
                payload=payload,
            )
        except AuthenticationError:
            raise ApiError(
                status_code=401,
                code="authentication_required",
                message="A valid Firebase ID token is required.",
            ) from None
        except SubmissionPermissionError:
            raise ApiError(
                status_code=403,
                code="customer_role_required",
                message="Only an active customer may submit a complaint.",
            ) from None
        except PersistenceError:
            raise ApiError(
                status_code=503,
                code="ticket_creation_unavailable",
                message="The complaint could not be saved. Try again.",
            ) from None
        return SubmitComplaintResponse(
            complaintId=result.complaint_id,
            status=result.status,
        )

    def staff_service() -> StaffWorkflowService:
        if staff_backend is not None:
            return StaffWorkflowService(staff_backend)
        try:
            return StaffWorkflowService(FirebaseAdminStaffBackend())
        except PersistenceError:
            raise ApiError(
                status_code=503,
                code="staff_service_unavailable",
                message="The staff service is unavailable.",
            ) from None

    def staff_actor(
        service: StaffWorkflowService, authorization: str | None
    ) -> StaffActor:
        try:
            return service.authenticate(authorization)
        except AuthenticationError:
            raise ApiError(
                status_code=401,
                code="authentication_required",
                message="A valid Firebase ID token is required.",
            ) from None
        except SubmissionPermissionError:
            raise ApiError(
                status_code=403,
                code="staff_role_required",
                message="An active staff profile with a valid department is required.",
            ) from None

    def staff_error(exc: Exception) -> ApiError:
        if isinstance(exc, StaffTicketNotFound):
            return ApiError(
                status_code=404, code="ticket_not_found", message="Ticket not found."
            )
        if isinstance(exc, InvalidTransition):
            return ApiError(
                status_code=409, code="invalid_transition", message=str(exc)
            )
        return ApiError(
            status_code=503,
            code="staff_service_unavailable",
            message="The staff service is unavailable.",
        )

    @api.get(
        "/staff/tickets",
        response_model=StaffTicketListResponse,
        response_model_by_alias=True,
    )
    async def list_staff_tickets(
        authorization: str | None = Header(default=None),
        status: Literal["triaged", "in_progress", "awaiting_customer", "resolved"]
        | None = None,
        priority: Literal["normal", "high", "urgent"] | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> StaffTicketListResponse:
        service = staff_service()
        actor = staff_actor(service, authorization)
        try:
            tickets = service.list_tickets(
                actor,
                status=status,
                priority=priority,
                created_from=created_from,
                created_to=created_to,
            )
        except PersistenceError as exc:
            raise staff_error(exc) from None
        return StaffTicketListResponse(
            tickets=[StaffTicketSummary.model_validate(ticket) for ticket in tickets]
        )

    @api.get(
        "/staff/tickets/{ticket_id}",
        response_model=StaffTicketDetail,
        response_model_by_alias=True,
    )
    async def get_staff_ticket(
        ticket_id: str,
        authorization: str | None = Header(default=None),
    ) -> StaffTicketDetail:
        service = staff_service()
        actor = staff_actor(service, authorization)
        try:
            return StaffTicketDetail.model_validate(service.detail(actor, ticket_id))
        except (StaffTicketNotFound, PersistenceError) as exc:
            raise staff_error(exc) from None

    @api.post(
        "/staff/tickets/{ticket_id}/replies",
        response_model=StaffMutationResponse,
        response_model_by_alias=True,
    )
    async def add_staff_reply(
        ticket_id: str,
        payload: StaffReplyRequest,
        authorization: str | None = Header(default=None),
    ) -> StaffMutationResponse:
        service = staff_service()
        actor = staff_actor(service, authorization)
        try:
            result = service.reply(
                actor, ticket_id, body=payload.body, action_id=payload.action_id
            )
        except (StaffTicketNotFound, PersistenceError) as exc:
            raise staff_error(exc) from None
        return StaffMutationResponse(
            ticketId=result.ticket_id,
            actionId=result.action_id,
            status=result.status,
            duplicate=result.duplicate,
        )

    @api.post(
        "/staff/tickets/{ticket_id}/transitions",
        response_model=StaffMutationResponse,
        response_model_by_alias=True,
    )
    async def transition_staff_ticket(
        ticket_id: str,
        payload: StaffTransitionRequest,
        authorization: str | None = Header(default=None),
    ) -> StaffMutationResponse:
        service = staff_service()
        actor = staff_actor(service, authorization)
        try:
            result = service.transition(
                actor,
                ticket_id,
                to_status=payload.status,
                resolution_summary=payload.resolution_summary,
                action_id=payload.action_id,
            )
        except (StaffTicketNotFound, InvalidTransition, PersistenceError) as exc:
            raise staff_error(exc) from None
        return StaffMutationResponse(
            ticketId=result.ticket_id,
            actionId=result.action_id,
            status=result.status,
            duplicate=result.duplicate,
        )

    @api.post(
        "/staff/tickets/{ticket_id}/requests",
        response_model=StaffMutationResponse,
        response_model_by_alias=True,
    )
    async def request_staff_action(
        ticket_id: str,
        payload: StaffRequestAction,
        authorization: str | None = Header(default=None),
    ) -> StaffMutationResponse:
        service = staff_service()
        actor = staff_actor(service, authorization)
        try:
            result = service.request(
                actor,
                ticket_id,
                request_type=payload.type,
                reason=payload.reason,
                action_id=payload.action_id,
            )
        except (StaffTicketNotFound, PersistenceError) as exc:
            raise staff_error(exc) from None
        return StaffMutationResponse(
            ticketId=result.ticket_id,
            actionId=result.action_id,
            status=result.status,
            duplicate=result.duplicate,
        )

    def customer_svc() -> CustomerWorkflowService:
        if customer_backend is not None:
            return CustomerWorkflowService(customer_backend)
        try:
            return CustomerWorkflowService(FirebaseAdminCustomerBackend())
        except PersistenceError:
            raise ApiError(
                status_code=503,
                code="customer_service_unavailable",
                message="The customer service is unavailable.",
            ) from None

    def customer_actor(authorization: str | None) -> str:
        if not authorization or not authorization.startswith("Bearer "):
            raise ApiError(
                status_code=401,
                code="authentication_required",
                message="A valid Firebase ID token is required.",
            )
        token = authorization.split(" ", 1)[1].strip()
        if ticket_backend is not None:
            try:
                uid = ticket_backend.verify_id_token(token)
            except Exception:  # noqa: BLE001 -- adapters expose SDK-specific auth errors
                raise ApiError(
                    status_code=401,
                    code="authentication_required",
                    message="A valid Firebase ID token is required.",
                ) from None
            try:
                profile = ticket_backend.get_user_profile(uid)
            except Exception:  # noqa: BLE001 -- backend profile failures must fail closed
                raise ApiError(
                    status_code=503,
                    code="profile_lookup_unavailable",
                    message="The customer profile could not be verified.",
                ) from None
            if (
                not profile
                or profile.get("role") != "customer"
                or profile.get("active") is not True
                or not _persisted_profile_state_is_valid(profile)
            ):
                raise ApiError(
                    status_code=403,
                    code="customer_role_required",
                    message="An active customer profile is required.",
                )
            return uid

        try:
            tb = ticket_backend or FirebaseAdminTicketBackend()
        except PersistenceError:
            raise ApiError(
                status_code=503,
                code="authentication_service_unavailable",
                message="Authentication could not be completed.",
            ) from None
        try:
            uid = tb.verify_id_token(token)
        except Exception:  # noqa: BLE001 -- Firebase SDK auth errors are not stable API types
            raise ApiError(
                status_code=401,
                code="authentication_required",
                message="A valid Firebase ID token is required.",
            ) from None
        try:
            profile = tb.get_user_profile(uid)
        except Exception:  # noqa: BLE001 -- backend profile failures must fail closed
            raise ApiError(
                status_code=503,
                code="profile_lookup_unavailable",
                message="The customer profile could not be verified.",
            ) from None
        if (
            not profile
            or profile.get("role") != "customer"
            or profile.get("active") is not True
            or not _persisted_profile_state_is_valid(profile)
        ):
            raise ApiError(
                status_code=403,
                code="customer_role_required",
                message="An active customer profile is required.",
            )
        return uid

    @api.get(
        "/customer/tickets",
        response_model=CustomerTicketListResponse,
        response_model_by_alias=True,
    )
    async def list_customer_tickets(
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> CustomerTicketListResponse:
        cust_id = customer_actor(authorization)
        allowed_parameters = {"pageSize", "cursor", "status", "departmentId"}
        if (
            any(key not in allowed_parameters for key in request.query_params)
            or any(
                len(request.query_params.getlist(key)) != 1
                for key in allowed_parameters
                if key in request.query_params
            )
        ):
            raise ApiError(
                status_code=422,
                code="invalid_customer_history_query",
                message="The customer history query is invalid.",
            )
        status = request.query_params.get("status")
        department_id = request.query_params.get("departmentId")
        if (
            status is not None and status not in CUSTOMER_HISTORY_STATUSES
        ) or (
            department_id is not None
            and department_id not in CUSTOMER_HISTORY_DEPARTMENTS
        ):
            raise ApiError(
                status_code=422,
                code="invalid_customer_history_filter",
                message="The customer history query is invalid.",
            )
        filters = CustomerHistoryFilters(
            status=status,
            department_id=department_id,
        )
        page_size_text = request.query_params.get("pageSize")
        if page_size_text is None:
            page_size = CUSTOMER_HISTORY_DEFAULT_PAGE_SIZE
        elif (
            not page_size_text.isascii()
            or not page_size_text.isdigit()
            or (len(page_size_text) > 1 and page_size_text.startswith("0"))
        ):
            raise ApiError(
                status_code=422,
                code="invalid_customer_history_page_size",
                message="The customer history query is invalid.",
            )
        else:
            page_size = int(page_size_text)
            if not 1 <= page_size <= CUSTOMER_HISTORY_MAX_PAGE_SIZE:
                raise ApiError(
                    status_code=422,
                    code="invalid_customer_history_page_size",
                    message="The customer history query is invalid.",
                )
        cursor_value = request.query_params.get("cursor")
        try:
            cursor = (
                decode_customer_history_cursor(cursor_value, cust_id, filters)
                if cursor_value is not None
                else None
            )
        except CustomerHistoryCursorError:
            raise ApiError(
                status_code=422,
                code="invalid_customer_history_cursor",
                message="The customer history query is invalid.",
            ) from None
        svc = customer_svc()
        try:
            return svc.list_ticket_page(cust_id, page_size, cursor, filters)
        except PersistenceError:
            raise ApiError(
                status_code=503,
                code="customer_service_unavailable",
                message="The customer service is unavailable.",
            ) from None

    @api.get(
        "/customer/tickets/{ticket_id}",
        response_model=CustomerTicketDetail,
        response_model_by_alias=True,
    )
    async def get_customer_ticket(
        ticket_id: str,
        authorization: str | None = Header(default=None),
    ) -> CustomerTicketDetail:
        cust_id = customer_actor(authorization)
        svc = customer_svc()
        try:
            return svc.get_ticket_detail(cust_id, ticket_id)
        except TicketNotFound:
            raise ApiError(
                status_code=404,
                code="ticket_not_found",
                message="Ticket not found.",
            ) from None

    @api.post(
        "/customer/tickets/{ticket_id}/messages",
        response_model=CustomerMessageItem,
        response_model_by_alias=True,
    )
    async def add_customer_message(
        ticket_id: str,
        payload: CustomerMessageRequest,
        authorization: str | None = Header(default=None),
    ) -> CustomerMessageItem:
        cust_id = customer_actor(authorization)
        svc = customer_svc()
        try:
            return CustomerMessageItem.model_validate(
                svc.send_message(cust_id, ticket_id, payload)
            )
        except TicketNotFound:
            raise ApiError(
                status_code=404,
                code="ticket_not_found",
                message="Ticket not found.",
            ) from None
        except InvalidTicketState as exc:
            raise ApiError(
                status_code=409,
                code="invalid_ticket_state",
                message=str(exc),
            ) from None
        except ValueError as exc:
            raise ApiError(
                status_code=422,
                code="invalid_message",
                message=str(exc),
            ) from None
        except PersistenceError:
            raise ApiError(
                status_code=503,
                code="customer_service_unavailable",
                message="The customer service is unavailable.",
            ) from None

    @api.post(
        "/customer/tickets/{ticket_id}/feedback",
        response_model=CustomerFeedbackResponse,
        response_model_by_alias=True,
    )
    async def submit_customer_feedback(
        ticket_id: str,
        payload: CustomerFeedbackRequest,
        authorization: str | None = Header(default=None),
    ) -> CustomerFeedbackResponse:
        cust_id = customer_actor(authorization)
        svc = customer_svc()
        try:
            return svc.submit_feedback(cust_id, ticket_id, payload)
        except TicketNotFound:
            raise ApiError(
                status_code=404,
                code="ticket_not_found",
                message="Ticket not found.",
            ) from None
        except InvalidTicketState as exc:
            raise ApiError(
                status_code=409,
                code="invalid_ticket_state",
                message=str(exc),
            ) from None
        except FeedbackAlreadySubmitted as exc:
            raise ApiError(
                status_code=409,
                code="feedback_already_submitted",
                message=str(exc),
            ) from None
        except ValueError as exc:
            raise ApiError(
                status_code=422,
                code="invalid_feedback",
                message=str(exc),
            ) from None
        except PersistenceError:
            raise ApiError(
                status_code=503,
                code="customer_service_unavailable",
                message="The customer service is unavailable.",
            ) from None

    def manager_svc() -> ManagerWorkflowService:
        if manager_backend is not None:
            return ManagerWorkflowService(manager_backend)
        try:
            return ManagerWorkflowService(FirebaseAdminManagerBackend())
        except PersistenceError:
            raise ApiError(
                status_code=503,
                code="manager_service_unavailable",
                message="The manager service is unavailable.",
            ) from None

    def manager_actor(authorization: str | None) -> str:
        if not authorization or not authorization.startswith("Bearer "):
            raise ApiError(
                status_code=401,
                code="authentication_required",
                message="A valid Firebase ID token is required.",
            )
        token = authorization.split(" ", 1)[1].strip()
        if ticket_backend is not None:
            try:
                uid = ticket_backend.verify_id_token(token)
            except Exception:  # noqa: BLE001 -- adapters expose SDK-specific auth errors
                raise ApiError(
                    status_code=401,
                    code="authentication_required",
                    message="A valid Firebase ID token is required.",
                ) from None
            try:
                profile = ticket_backend.get_user_profile(uid)
            except Exception:  # noqa: BLE001 -- backend profile failures must fail closed
                raise ApiError(
                    status_code=503,
                    code="profile_lookup_unavailable",
                    message="The manager profile could not be verified.",
                ) from None
            if (
                not profile
                or profile.get("role") != "manager"
                or profile.get("active") is not True
                or not _persisted_profile_state_is_valid(profile)
            ):
                raise ApiError(
                    status_code=403,
                    code="manager_role_required",
                    message="An active manager profile is required.",
                )
            return uid

        try:
            tb = ticket_backend or FirebaseAdminTicketBackend()
        except PersistenceError:
            raise ApiError(
                status_code=503,
                code="authentication_service_unavailable",
                message="Authentication could not be completed.",
            ) from None
        try:
            uid = tb.verify_id_token(token)
        except Exception:  # noqa: BLE001 -- Firebase SDK auth errors are not stable API types
            raise ApiError(
                status_code=401,
                code="authentication_required",
                message="A valid Firebase ID token is required.",
            ) from None
        try:
            profile = tb.get_user_profile(uid)
        except Exception:  # noqa: BLE001 -- backend profile failures must fail closed
            raise ApiError(
                status_code=503,
                code="profile_lookup_unavailable",
                message="The manager profile could not be verified.",
            ) from None
        if (
            not profile
            or profile.get("role") != "manager"
            or profile.get("active") is not True
            or not _persisted_profile_state_is_valid(profile)
        ):
            raise ApiError(
                status_code=403,
                code="manager_role_required",
                message="An active manager profile is required.",
            )
        return uid

    @api.get(
        "/manager/analytics",
        response_model=ManagerAnalyticsResponse,
        response_model_by_alias=True,
    )
    async def get_manager_analytics(
        authorization: str | None = Header(default=None),
    ) -> ManagerAnalyticsResponse:
        _mgr_id = manager_actor(authorization)
        svc = manager_svc()
        data = svc.get_analytics()
        return ManagerAnalyticsResponse.model_validate(data)

    @api.get(
        "/manager/low-confidence-tickets",
        response_model=list[LowConfidenceTicketItem],
        response_model_by_alias=True,
    )
    async def list_low_confidence_tickets(
        authorization: str | None = Header(default=None),
    ) -> list[LowConfidenceTicketItem]:
        _mgr_id = manager_actor(authorization)
        svc = manager_svc()
        tickets = svc.list_low_confidence_tickets()
        return [LowConfidenceTicketItem.model_validate(t) for t in tickets]

    @api.post(
        "/manager/tickets/{ticket_id}/override",
        response_model=ManagerOverrideResponse,
        response_model_by_alias=True,
    )
    async def override_ticket_department(
        ticket_id: str,
        payload: ManagerOverrideRequest,
        authorization: str | None = Header(default=None),
    ) -> ManagerOverrideResponse:
        mgr_id = manager_actor(authorization)
        svc = manager_svc()
        try:
            doc = svc.override_department(
                ticket_id=ticket_id,
                new_department_id=payload.new_department_id,
                manager_id=mgr_id,
                reason=payload.reason,
                action_id=payload.action_id,
            )
        except ManagerTicketNotFound:
            raise ApiError(
                status_code=404, code="ticket_not_found", message="Ticket not found."
            ) from None
        except ManagerInvalidDeptError:
            raise ApiError(
                status_code=400,
                code="invalid_department",
                message="Invalid department ID.",
            ) from None
        except PersistenceError:
            raise ApiError(
                status_code=503,
                code="manager_service_unavailable",
                message="The manager service is unavailable.",
            ) from None
        return ManagerOverrideResponse(
            ticketId=doc["id"],
            departmentId=doc["departmentId"],
            routingSource="manager_override",
            updatedAt=doc["updatedAt"],
        )

    def notification_service() -> NotificationService:
        if notification_backend is not None:
            return NotificationService(notification_backend)
        try:
            return NotificationService(FirebaseAdminNotificationBackend())
        except PersistenceError:
            raise ApiError(
                status_code=503,
                code="service_unavailable",
                message="Notifications are temporarily unavailable.",
            ) from None

    def notification_actor(authorization: str | None) -> str:
        try:
            backend = ticket_backend or FirebaseAdminTicketBackend()
            return require_active_notification_profile(authorization, backend).uid
        except AuthenticationError:
            raise ApiError(
                status_code=401,
                code="authentication_required",
                message="A valid Firebase ID token is required.",
            ) from None
        except NotificationProfileError:
            raise ApiError(
                status_code=403,
                code="active_profile_required",
                message="An active application profile is required.",
            ) from None
        except PersistenceError:
            raise ApiError(
                status_code=503,
                code="service_unavailable",
                message="Authentication could not be completed.",
            ) from None

    def _notification_item(record: Any) -> NotificationItem:
        return NotificationItem(
            notificationRef=record.notification_ref,
            type=record.type,
            severity=record.severity,
            category=record.category,
            relatedTicketRef=record.related_ticket_ref,
            titleKey=record.title_key,
            bodyKey=record.body_key,
            params=record.params,
            navigationTarget=record.navigation_target,
            createdAt=record.created_at,
            readAt=record.read_at,
            unread=record.read_at is None,
        )

    @api.get(
        "/notifications",
        response_model=NotificationListResponse,
        response_model_by_alias=True,
        responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 422: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    )
    async def list_notifications(
        authorization: str | None = Header(default=None),
        page_size: int = Query(default=20, alias="pageSize", ge=1, le=50),
        unread_only: bool = Query(default=False, alias="unreadOnly"),
        cursor: str | None = Query(default=None, max_length=512),
    ) -> NotificationListResponse:
        recipient_uid = notification_actor(authorization)
        try:
            page = notification_service().list(
                recipient_uid,
                unread_only=unread_only,
                cursor=cursor,
                page_size=page_size,
            )
        except NotificationValidationError:
            raise ApiError(
                status_code=422,
                code="invalid_request",
                message="The notification request is invalid.",
            ) from None
        except PersistenceError:
            raise ApiError(
                status_code=503,
                code="service_unavailable",
                message="Notifications are temporarily unavailable.",
            ) from None
        return NotificationListResponse(
            notifications=[_notification_item(record) for record in page.records],
            nextCursor=page.next_cursor,
        )

    @api.get(
        "/notifications/unread-count",
        response_model=NotificationUnreadCountResponse,
        response_model_by_alias=True,
        responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    )
    async def unread_notification_count(
        authorization: str | None = Header(default=None),
    ) -> NotificationUnreadCountResponse:
        recipient_uid = notification_actor(authorization)
        try:
            count = notification_service().unread_count(recipient_uid)
        except PersistenceError:
            raise ApiError(
                status_code=503,
                code="service_unavailable",
                message="Notifications are temporarily unavailable.",
            ) from None
        return NotificationUnreadCountResponse(unreadCount=count)

    @api.post(
        "/notifications/{notification_ref}/read",
        response_model=NotificationReadResponse,
        response_model_by_alias=True,
        responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    )
    async def mark_notification_read(
        notification_ref: str,
        authorization: str | None = Header(default=None),
    ) -> NotificationReadResponse:
        recipient_uid = notification_actor(authorization)
        try:
            record = notification_service().mark_read(recipient_uid, notification_ref)
        except NotificationValidationError:
            raise ApiError(
                status_code=422,
                code="invalid_request",
                message="The notification reference is invalid.",
            ) from None
        except NotificationNotFoundError:
            raise ApiError(
                status_code=404,
                code="notification_not_found",
                message="Notification not found.",
            ) from None
        except PersistenceError:
            raise ApiError(
                status_code=503,
                code="service_unavailable",
                message="Notifications are temporarily unavailable.",
            ) from None
        return NotificationReadResponse(
            notificationRef=record.notification_ref,
            readAt=record.read_at,
        )

    @api.post(
        "/notifications/read-all",
        response_model=NotificationReadAllResponse,
        response_model_by_alias=True,
        responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    )
    async def mark_all_notifications_read(
        authorization: str | None = Header(default=None),
    ) -> NotificationReadAllResponse:
        recipient_uid = notification_actor(authorization)
        try:
            updated_count = notification_service().mark_all_read(recipient_uid)
        except PersistenceError:
            raise ApiError(
                status_code=503,
                code="service_unavailable",
                message="Notifications are temporarily unavailable.",
            ) from None
        return NotificationReadAllResponse(updatedCount=updated_count)

    return api


app = create_app()
