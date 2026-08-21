import copy
import json
from pathlib import Path

import pytest

import scripts.controlled_synthetic_v2b as v2b


MANIFEST_PATH = (
    Path(__file__).resolve().parents[2]
    / "evaluation"
    / "controlled"
    / "six_department_long_english_v2a_manifest.json"
)


class FakePrediction:
    def __init__(self, department_id: str, confidence: float) -> None:
        self.department_id = department_id
        self.confidence = confidence


class FakePredictor:
    model_version = "v1"
    threshold = 0.0

    def __init__(self, predictions: list[FakePrediction]) -> None:
        self.predictions = iter(predictions)
        self.calls = 0

    def predict(self, _text: str) -> FakePrediction:
        self.calls += 1
        return next(self.predictions)


def manifest() -> tuple[dict, str]:
    return v2b.load_manifest(MANIFEST_PATH)


def test_manifest_hash_mismatch_fails_before_prediction() -> None:
    value, _digest = manifest()
    predictor = FakePredictor([FakePrediction("general_support", 0.9)])
    with pytest.raises(ValueError, match="manifest hash"):
        v2b.evaluate_cases(
            predictor,
            value,
            manifest_sha256="0" * 64,
            generated_at_utc="2026-08-21T00:00:00Z",
        )
    assert predictor.calls == 0


def test_manifest_order_or_label_drift_fails_before_prediction() -> None:
    value, digest = manifest()
    changed = copy.deepcopy(value)
    changed["cases"][0], changed["cases"][1] = changed["cases"][1], changed["cases"][0]
    with pytest.raises(ValueError, match="order"):
        v2b.validate_manifest(changed, digest)

    changed = copy.deepcopy(value)
    changed["cases"][0]["expectedDepartmentId"] = "card_atm"
    with pytest.raises(ValueError, match="order|label"):
        v2b.validate_manifest(changed, digest)


def test_model_version_label_and_threshold_contracts_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(v2b, "MODEL_VERSION", "v2")
    with pytest.raises(v2b.ModelArtifactError, match="version"):
        v2b.validate_frozen_contract()

    monkeypatch.setattr(v2b, "MODEL_VERSION", "v1")
    monkeypatch.setattr(v2b, "LABELS", ("general_support",))
    with pytest.raises(v2b.ModelArtifactError, match="label"):
        v2b.validate_frozen_contract()

    monkeypatch.setattr(v2b, "LABELS", v2b.EXPECTED_LABELS)
    monkeypatch.setattr(v2b, "DEFAULT_ROUTING_CONFIDENCE_THRESHOLD", 0.0)
    with pytest.raises(v2b.ModelArtifactError, match="threshold"):
        v2b.validate_frozen_contract()


def test_result_calculations_separate_matches_and_automatic_routes() -> None:
    value, digest = manifest()
    predictor = FakePredictor(
        [
            FakePrediction("transfer_payment", 0.91),
            FakePrediction("account_support", 0.55),
            FakePrediction("account_support", 0.91),
            FakePrediction("card_atm", 0.40),
            FakePrediction("loan_credit", 0.58),
            FakePrediction("loan_credit", 0.30),
        ]
    )
    result = v2b.evaluate_cases(
        predictor,
        value,
        manifest_sha256=digest,
        generated_at_utc="2026-08-21T00:00:00Z",
    )
    assert result["summary"] == {
        "totalCases": 6,
        "classifierPredictionMatchCount": 3,
        "classifierPredictionMatchRate": 50.0,
        "automaticRouteCount": 2,
        "correctAutomaticRouteCount": 1,
        "automaticRoutingSuccessRate": 50.0,
        "manualReviewCount": 4,
        "correctPredictionsSentToManualReview": 2,
        "incorrectPredictionsSentToManualReview": 2,
        "confidentIncorrectAutomaticRouteCount": 1,
    }
    assert result["cases"][1]["classifierPredictionMatches"] is True
    assert result["cases"][1]["correctAutomaticRoute"] is False
    assert result["cases"][2]["classifierPredictionMatches"] is False
    assert result["cases"][2]["correctAutomaticRoute"] is False


def test_language_policy_manual_review_does_not_call_classifier() -> None:
    value, digest = manifest()
    changed = copy.deepcopy(value)
    changed["cases"][0]["complaintText"] = " ".join(["123"] * 59)
    predictor = FakePredictor(
        [FakePrediction("general_support", 0.4) for _ in range(5)]
    )
    result = v2b.evaluate_cases(
        predictor,
        changed,
        manifest_sha256=digest,
        generated_at_utc="2026-08-21T00:00:00Z",
    )
    first = result["cases"][0]
    assert first["detectedLanguage"] == "unsupported"
    assert first["manualReview"] is True
    assert first["manualReviewReason"] == "unsupported_language"
    assert predictor.calls == 5


def test_result_has_no_complaint_text_or_private_fields() -> None:
    value, digest = manifest()
    result = v2b.evaluate_cases(
        FakePredictor([FakePrediction(label, 0.9) for label in v2b.EXPECTED_LABELS]),
        value,
        manifest_sha256=digest,
        generated_at_utc="2026-08-21T00:00:00Z",
    )
    serialized = json.dumps(result)
    assert "complaintText" not in serialized
    assert "expectedLabelRationale" not in serialized
    assert "predictionConfidence" in serialized
    assert all(case["managerOverride"] is False for case in result["cases"])
