"""Day 17 trusted inference and routing policy tests."""

from pathlib import Path

import pytest
from app.config import MODEL_SHA256
from app.model import FrozenDepartmentClassifier, Prediction
from app.routing import (
    OfflineMyanmarTranslator,
    RoutingInferenceError,
    TrustedRoutingInference,
)
from app.schemas import SubmitComplaintRequest
from app.ticketing import ComplaintSubmissionService


class StubClassifier:
    model_version = "v1"

    def __init__(self, prediction: Prediction | Exception) -> None:
        self.prediction = prediction

    def predict(self, _text: str) -> Prediction:
        if isinstance(self.prediction, Exception):
            raise self.prediction
        return self.prediction


class StubTranslator:
    def __init__(self, translated: str) -> None:
        self.translated = translated

    def translate(self, _text: str) -> str:
        return self.translated


class RecordingBackend:
    server_timestamp = "server-time"

    def __init__(self) -> None:
        self.document = None
        self.failure = None

    def verify_id_token(self, _token: str) -> str:
        return "customer-1"

    def get_user_profile(self, _uid: str):
        return {"active": True, "role": "customer"}

    def create_ticket(self, document, *, idempotency_key):
        assert idempotency_key == "submission-action-001"
        self.document = document
        return "ticket-1"

    def persist_prediction(self, _ticket_id, _prediction):
        raise AssertionError("failure path must not persist a prediction")

    def persist_inference_failure(self, ticket_id, *, code, detected_language):
        self.failure = (ticket_id, code, detected_language)


def inference(confidence: float, *, department: str = "card_atm"):
    return TrustedRoutingInference(
        StubClassifier(Prediction(department, confidence, False, None)),
        confidence_threshold=0.60,
    )


def test_high_confidence_english_prediction_is_eligible_for_routing():
    result = inference(0.91).predict("The ATM retained my debit card")
    assert result.department_id == "card_atm"
    assert result.detected_language == "en"
    assert result.requires_manual_review is False


def test_low_confidence_english_prediction_requires_manual_review():
    result = inference(0.59).predict("I do not understand this charge")
    assert result.department_id == "card_atm"
    assert result.confidence == 0.59
    assert result.requires_manual_review is True
    assert result.manual_review_reason == "low_prediction_confidence"


def test_myanmar_uses_translation_and_never_auto_routes_before_approval():
    pipeline = TrustedRoutingInference(
        StubClassifier(Prediction("transfer_payment", 0.95, False, None)),
        confidence_threshold=0.60,
        translator=StubTranslator("The recipient has not received my transfer"),
    )
    result = pipeline.predict(
        "\u1004\u103d\u1031\u101c\u103d\u103e\u1032\u1019\u101b\u101b\u103e\u102d\u1015\u102b"
    )
    assert result.department_id == "transfer_payment"
    assert result.detected_language == "my"
    assert result.requires_manual_review is True
    assert result.manual_review_reason == "myanmar_translation_not_approved"


def test_classifier_failure_is_sanitized_and_unrouted():
    pipeline = TrustedRoutingInference(
        StubClassifier(ValueError("sensitive internal error")),
        confidence_threshold=0.60,
    )
    with pytest.raises(RoutingInferenceError) as caught:
        pipeline.predict("A valid English complaint")
    assert caught.value.code == "classification_failed"
    assert "sensitive" not in str(caught.value)


def test_submission_survives_classifier_failure_and_records_manual_review():
    backend = RecordingBackend()
    pipeline = TrustedRoutingInference(
        StubClassifier(RuntimeError("internal classifier detail")),
        confidence_threshold=0.60,
    )
    result = ComplaintSubmissionService(backend, pipeline).submit(
        authorization="Bearer valid-token",
        payload=SubmitComplaintRequest(
            complaintText="A valid English complaint about my account",
            inputLocale="en",
            actionId="submission-action-001",
        ),
    )
    assert result.complaint_id == "ticket-1"
    assert backend.document["routingSource"] == "pending"
    assert backend.document["departmentId"] is None
    assert backend.failure == ("ticket-1", "classification_failed", "en")


def test_unknown_classifier_label_is_rejected_without_substitution():
    pipeline = TrustedRoutingInference(
        StubClassifier(Prediction("unknown_department", 0.99, False, None)),
        confidence_threshold=0.60,
    )
    with pytest.raises(RoutingInferenceError) as caught:
        pipeline.predict("A valid English complaint")
    assert caught.value.code == "unknown_prediction_label"


def test_real_frozen_model_classifies_synthetic_english_complaint():
    artifact = (
        Path(__file__).resolve().parents[2]
        / "models"
        / "generated"
        / "cfpb_department_model_v1.joblib"
    )
    if not artifact.is_file():
        pytest.skip("ignored frozen model artifact is not installed")
    classifier = FrozenDepartmentClassifier.load(artifact, expected_sha256=MODEL_SHA256)
    result = TrustedRoutingInference(classifier, confidence_threshold=0.60).predict(
        "My credit report contains accounts caused by identity theft and fraud."
    )
    assert result.department_id == "fraud_security"
    assert result.confidence > 0.60
    assert result.requires_manual_review is False


def test_real_local_myanmar_translation_and_classifier_require_review():
    artifact = (
        Path(__file__).resolve().parents[2]
        / "models"
        / "generated"
        / "cfpb_department_model_v1.joblib"
    )
    cache = Path.home() / ".cache" / "complaintguard" / "huggingface"
    if not artifact.is_file() or not cache.is_dir():
        pytest.skip("ignored classifier or local translation artifact is not installed")
    classifier = FrozenDepartmentClassifier.load(artifact, expected_sha256=MODEL_SHA256)
    pipeline = TrustedRoutingInference(
        classifier,
        confidence_threshold=0.60,
        translator=OfflineMyanmarTranslator(cache),
    )
    result = pipeline.predict(
        "\u1004\u103d\u1031\u101c\u103d\u103e\u1032\u1015\u103c\u102e\u1038\u101e\u1031\u102c\u103a\u101c\u100a\u103a\u1038 "
        "\u101c\u1000\u103a\u1001\u1036\u101e\u1030\u1000 \u1004\u103d\u1031\u1019\u101b\u101b\u103e\u102d\u101e\u1031\u1038\u1015\u102b\u104b"
    )
    assert result.department_id in {
        "transfer_payment",
        "account_support",
        "card_atm",
        "fraud_security",
        "loan_credit",
        "general_support",
    }
    assert 0.0 <= result.confidence <= 1.0
    assert result.detected_language == "my"
    assert result.requires_manual_review is True
    assert result.manual_review_reason == "myanmar_translation_not_approved"
