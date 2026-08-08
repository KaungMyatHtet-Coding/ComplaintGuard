"""ComplaintGuard Day 11 FastAPI application."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Literal

from fastapi import FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import MODEL_VERSION, Settings
from app.customer_workflow import (
    CustomerBackend,
    CustomerWorkflowService,
    FeedbackAlreadySubmitted,
    FirebaseAdminCustomerBackend,
    InvalidTicketState,
    TicketNotFound,
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
from app.routing import OfflineMyanmarTranslator, TrustedRoutingInference
from app.schemas import (
    CustomerFeedbackRequest,
    CustomerFeedbackResponse,
    CustomerMessageItem,
    CustomerMessageRequest,
    CustomerTicketDetail,
    CustomerTicketListResponse,
    ErrorDetail,
    ErrorResponse,
    HealthResponse,
    LowConfidenceTicketItem,
    ManagerAnalyticsResponse,
    ManagerOverrideRequest,
    ManagerOverrideResponse,
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
from app.ticketing import (
    PermissionError as SubmissionPermissionError,
)

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
        authorization: str | None = Header(default=None),
    ) -> CustomerTicketListResponse:
        cust_id = customer_actor(authorization)
        svc = customer_svc()
        try:
            tickets = svc.list_tickets(cust_id)
        except PersistenceError:
            raise ApiError(
                status_code=503,
                code="customer_service_unavailable",
                message="The customer service is unavailable.",
            ) from None
        return CustomerTicketListResponse(tickets=tickets)

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

    return api


app = create_app()
