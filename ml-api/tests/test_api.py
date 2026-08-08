"""Synthetic tests for the ComplaintGuard Day 11 ML API."""

from __future__ import annotations

import hashlib
from pathlib import Path

import joblib
import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter

from app.config import MAX_COMPLAINT_LENGTH, Settings
from app.main import create_app
from app.model import (
    LABELS,
    FrozenDepartmentClassifier,
    ModelArtifactError,
    Prediction,
)
from app.schemas import ErrorResponse, HealthResponse, PredictResponse


class FakeClassifier:
    model_version = "v1"

    def predict(self, _text: str) -> Prediction:
        return Prediction(
            department_id="account_support",
            confidence=0.75,
            fallback=False,
            fallback_reason=None,
        )


class FakeVectorizer:
    def transform(self, values: list[str]) -> np.ndarray:
        return np.ones((len(values), 1), dtype=np.float64)


class FakeProbabilityModel:
    classes_ = np.asarray(LABELS)

    def predict_proba(self, matrix: np.ndarray) -> np.ndarray:
        probabilities = np.zeros((matrix.shape[0], len(LABELS)), dtype=np.float64)
        probabilities[:, 1] = 1.0
        return probabilities


def successful_loader(_path: Path, *, expected_sha256: str) -> FakeClassifier:
    assert expected_sha256
    return FakeClassifier()


def failed_loader(_path: Path, *, expected_sha256: str) -> FakeClassifier:
    assert expected_sha256
    raise ModelArtifactError("synthetic load failure")


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(model_path=tmp_path / "model.joblib", expected_model_sha256="a")


@pytest.fixture
def client(settings: Settings):
    with TestClient(
        create_app(settings=settings, model_loader=successful_loader)
    ) as api:
        yield api


def test_health_reports_loaded_model_without_private_paths(
    client: TestClient,
) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    HealthResponse.model_validate(body)
    assert body == {
        "status": "ok",
        "service": "complaintguard-ml-api",
        "model_loaded": True,
        "model_version": "v1",
        "supported_prediction_languages": ["en"],
        "myanmar_readiness": "development_baseline_not_approved",
    }


def test_predict_returns_documented_schema(client: TestClient) -> None:
    response = client.post(
        "/predict",
        json={"text": "Please help update the settings on this account."},
    )
    assert response.status_code == 200
    body = response.json()
    PredictResponse.model_validate(body)
    assert body == {
        "department_id": "account_support",
        "confidence": 0.75,
        "detected_language": "en",
        "model_version": "v1",
        "fallback": False,
        "fallback_reason": None,
    }
    assert "text" not in body


@pytest.mark.parametrize(
    ("payload", "expected_type"),
    [
        ({}, "missing"),
        ({"text": 123}, "string_type"),
        ({"text": ""}, "value_error"),
        ({"text": "   \t\n "}, "value_error"),
        ({"text": "a" * (MAX_COMPLAINT_LENGTH + 1)}, "string_too_long"),
        ({"text": "valid text", "extra": "forbidden"}, "extra_forbidden"),
    ],
)
def test_invalid_requests_have_structured_errors(
    client: TestClient,
    payload: dict[str, object],
    expected_type: str,
) -> None:
    response = client.post("/predict", json=payload)
    assert response.status_code == 422
    body = response.json()
    ErrorResponse.model_validate(body)
    assert body["error"]["code"] == "request_validation_error"
    assert any(item["type"] == expected_type for item in body["error"]["details"])
    assert "input" not in str(body)


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("ငွေစာရင်းကို ကူညီပေးပါ။", "my"),
        ("account ကို စစ်ပေးပါ။", "mixed"),
    ],
)
def test_myanmar_is_not_claimed_as_production_ready(
    client: TestClient,
    text: str,
    language: str,
) -> None:
    response = client.post("/predict", json={"text": text})
    assert response.status_code == 422
    body = response.json()
    ErrorResponse.model_validate(body)
    assert body["error"]["code"] == "myanmar_not_production_ready"
    assert body["error"]["details"] == [
        {"field": None, "type": None, "detected_language": language}
    ]


def test_punctuation_only_input_is_unsupported(client: TestClient) -> None:
    response = client.post("/predict", json={"text": "... 123 !!!"})
    assert response.status_code == 422
    body = response.json()
    ErrorResponse.model_validate(body)
    assert body["error"]["code"] == "unsupported_input"


def test_model_loading_failure_degrades_health_and_prediction(
    settings: Settings,
) -> None:
    with TestClient(create_app(settings=settings, model_loader=failed_loader)) as api:
        health = api.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] == "degraded"
        assert health.json()["model_loaded"] is False
        prediction = api.post("/predict", json={"text": "A synthetic request."})
        assert prediction.status_code == 503
        assert prediction.json()["error"]["code"] == "model_unavailable"


def test_openapi_uses_response_schemas(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    assert schema["paths"]["/health"]["get"]["responses"]["200"]["content"]
    assert schema["paths"]["/predict"]["post"]["responses"]["200"]["content"]
    adapter = TypeAdapter(PredictResponse)
    for label in LABELS:
        adapter.validate_python(
            {
                "department_id": label,
                "confidence": 0.5,
                "detected_language": "en",
                "model_version": "v1",
                "fallback": False,
                "fallback_reason": None,
            }
        )


def test_frozen_loader_checks_integrity(tmp_path: Path) -> None:
    path = tmp_path / "model.joblib"
    joblib.dump({"not": "a valid model"}, path)
    with pytest.raises(ModelArtifactError, match="integrity"):
        FrozenDepartmentClassifier.load(path, expected_sha256="0" * 64)


def test_frozen_loader_and_prediction_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "model.joblib"
    artifact = {
        "model_version": "v1",
        "dataset_version": "v1",
        "mapping_version": "v1",
        "vectorizer": FakeVectorizer(),
        "classifier": FakeProbabilityModel(),
        "labels": LABELS,
        "confidence_threshold": 0.0,
        "fallback_label": "general_support",
        "normalization": "NFKC + casefold + whitespace collapse",
    }
    joblib.dump(artifact, path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    classifier = FrozenDepartmentClassifier.load(path, expected_sha256=digest)
    prediction = classifier.predict("  FICTIONAL   ACCOUNT request ")
    assert prediction.department_id == "account_support"
    assert prediction.confidence == 1.0
    assert prediction.fallback is False
