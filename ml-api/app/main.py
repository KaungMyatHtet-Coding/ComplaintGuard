"""ComplaintGuard Day 11 FastAPI application."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import MODEL_VERSION, Settings
from app.language import detect_language
from app.model import FrozenDepartmentClassifier, ModelArtifactError
from app.schemas import (
    ErrorDetail,
    ErrorResponse,
    HealthResponse,
    PredictRequest,
    PredictResponse,
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
) -> FastAPI:
    runtime_settings = settings or Settings.default()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.classifier = None
        app.state.model_error_code = None
        try:
            app.state.classifier = model_loader(
                runtime_settings.model_path,
                expected_sha256=runtime_settings.expected_model_sha256,
            )
        except (ModelArtifactError, OSError, ValueError, TypeError):
            app.state.model_error_code = "model_unavailable"
        yield
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

    return api


app = create_app()
