from pathlib import Path

import pytest
import scripts.controlled_synthetic_test as controlled_test
from app.model import ModelArtifactError, Prediction
from scripts.controlled_synthetic_test import (
    CASES,
    EXPECTED_LABELS,
    EXPECTED_OPERATIONAL_THRESHOLD,
    evaluate_cases,
    prepare_case_definition,
    validate_cases,
    write_artifact,
)


class FakePredictor:
    model_version = "v1"
    threshold = 0.0

    def __init__(self, predictions: list[Prediction]) -> None:
        self.predictions = iter(predictions)

    def predict(self, text: str) -> Prediction:
        assert text.startswith("A synthetic")
        return next(self.predictions)


def prediction(department: str, confidence: float) -> Prediction:
    return Prediction(department, confidence, False, None)


def test_cases_have_exact_frozen_order_and_predefined_expected_labels() -> None:
    validate_cases()
    assert tuple(case.expected_department_id for case in CASES) == EXPECTED_LABELS
    assert all(case.input_locale == "en" for case in CASES)
    assert all(case.case_id.startswith("synthetic-") for case in CASES)


def test_evaluation_separates_automatic_and_manual_review() -> None:
    predictor = FakePredictor(
        [
            prediction(label, 0.91) for label in EXPECTED_LABELS[:2]
        ]
        + [prediction("card_atm", 0.59)]
        + [prediction(label, 0.88) for label in EXPECTED_LABELS[3:]]
    )
    artifact = evaluate_cases(
        predictor,
        generated_at_utc="2026-08-21T00:00:00Z",
        case_definition_sha256=prepare_case_definition(),
    )
    results = artifact["cases"]
    assert artifact["summary"] == {
        "totalCases": 6,
        "classifierPredictionMatchCount": 6,
        "classifierPredictionMatchRate": 100.0,
        "automaticRouteCount": 5,
        "correctAutomaticRouteCount": 5,
        "automaticRoutingSuccessRate": 100.0,
        "manualReviewCount": 1,
        "correctPredictionsSentToManualReview": 1,
        "incorrectPredictionsSentToManualReview": 0,
        "managerOverrideCount": 0,
    }
    assert results[2]["manualReview"] is True
    assert results[2]["finalRouteDepartmentId"] is None
    assert results[2]["correctPrediction"] is True
    assert results[2]["classifierPredictionMatches"] is True
    assert results[2]["correctAutomaticRoute"] is False
    assert results[2]["correctFinalRoute"] is None
    assert results[2]["operationalThreshold"] == EXPECTED_OPERATIONAL_THRESHOLD


def test_result_contains_controlled_contract_and_disclosures() -> None:
    artifact = evaluate_cases(
        FakePredictor([prediction(label, 0.9) for label in EXPECTED_LABELS]),
        generated_at_utc="2026-08-21T00:00:00Z",
        case_definition_sha256=prepare_case_definition(),
    )
    required_case_fields = {
        "caseId",
        "inputLocale",
        "textLengthCategory",
        "expectedDepartmentId",
        "expectedDepartmentLabel",
        "syntheticInput",
        "predictedDepartmentId",
        "predictionConfidence",
        "finalRouteDepartmentId",
        "routingSource",
        "manualReview",
        "manualReviewReason",
        "managerOverride",
        "classifierPredictionMatches",
        "correctPrediction",
        "correctAutomaticRoute",
        "correctFinalRoute",
        "modelVersion",
        "operationalThreshold",
    }
    assert all(required_case_fields <= result.keys() for result in artifact["cases"])
    assert artifact["evidenceType"] == "controlled synthetic demonstration"
    assert artifact["reproducibility"]["expectedLabelsFrozenBeforeInference"] is True
    assert artifact["summary"]["managerOverrideCount"] == 0
    assert any("Not official model accuracy" in limitation for limitation in artifact["limitations"])
    assert any("uncalibrated" in limitation for limitation in artifact["limitations"])


def test_case_hash_is_ready_before_first_prediction() -> None:
    events: list[str] = []

    class OrderingPredictor(FakePredictor):
        def predict(self, text: str) -> Prediction:
            events.append("prediction")
            assert "hash" in events
            return super().predict(text)

    case_hash = prepare_case_definition()
    events.append("hash")
    artifact = evaluate_cases(
        OrderingPredictor([prediction(label, 0.9) for label in EXPECTED_LABELS]),
        generated_at_utc="2026-08-21T00:00:00Z",
        case_definition_sha256=case_hash,
    )
    assert events[0] == "hash"
    assert artifact["reproducibility"]["caseDefinitionSha256"] == case_hash
    assert artifact["reproducibility"]["caseDefinitionHashComputedBeforeModelLoad"] is True


def test_run_orders_hash_before_model_load_and_prediction(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []

    original_hash = controlled_test._request_fingerprint

    def record_hash(cases: tuple[object, ...]) -> str:
        events.append("hash")
        return original_hash(cases)  # type: ignore[arg-type]

    class FakeLoadedPredictor(FakePredictor):
        def predict(self, text: str) -> Prediction:
            events.append("prediction")
            return super().predict(text)

    def fake_load(_path: Path, *, expected_sha256: str) -> FakeLoadedPredictor:
        events.append("model_load")
        assert expected_sha256 == controlled_test.EXPECTED_MODEL_SHA256
        return FakeLoadedPredictor([prediction(label, 0.9) for label in EXPECTED_LABELS])

    captured: dict[str, object] = {}

    def fake_write(artifact: dict[str, object], _output: Path, *, repository_root: Path) -> None:
        captured["artifact"] = artifact

    monkeypatch.setattr(controlled_test, "_request_fingerprint", record_hash)
    monkeypatch.setattr(controlled_test.FrozenDepartmentClassifier, "load", fake_load)
    monkeypatch.setattr(controlled_test, "write_artifact", fake_write)
    controlled_test.run(generated_at_utc="2026-08-21T00:00:00Z")

    assert events[0:2] == ["hash", "model_load"]
    assert events[2] == "prediction"
    assert captured["artifact"]["reproducibility"]["caseDefinitionHashComputedBeforeModelLoad"] is True  # type: ignore[index]


def test_model_contract_drift_fails_closed() -> None:
    predictor = FakePredictor([prediction(label, 0.9) for label in EXPECTED_LABELS])
    predictor.model_version = "v2"
    with pytest.raises(ModelArtifactError, match="version"):
        evaluate_cases(
            predictor,
            generated_at_utc="2026-08-21T00:00:00Z",
            case_definition_sha256=prepare_case_definition(),
        )

    predictor.model_version = "v1"
    predictor.threshold = 0.60
    with pytest.raises(ModelArtifactError, match="threshold"):
        evaluate_cases(
            predictor,
            generated_at_utc="2026-08-21T00:00:00Z",
            case_definition_sha256=prepare_case_definition(),
        )


def test_write_artifact_refuses_official_or_existing_destinations(tmp_path: Path) -> None:
    artifact = {"evidenceType": "controlled synthetic demonstration"}
    root = tmp_path
    with pytest.raises(ValueError):
        write_artifact(artifact, root / "evaluation" / "day18" / "bad.json", repository_root=root)

    output = root / "evaluation" / "controlled" / "result.json"
    write_artifact(artifact, output, repository_root=root)
    with pytest.raises(FileExistsError):
        write_artifact(artifact, output, repository_root=root)


def test_validation_rejects_duplicate_or_private_case_content() -> None:
    duplicate = CASES[:-1] + (CASES[0],)
    with pytest.raises(ValueError, match="authoritative order"):
        validate_cases(duplicate)

    private_case = CASES[:-1] + (
        CASES[-1].__class__(
            **{**CASES[-1].__dict__, "synthetic_input": "A synthetic account number 123456 needs help."}
        ),
    )
    with pytest.raises(ValueError, match="numeric identifiers"):
        validate_cases(private_case)
