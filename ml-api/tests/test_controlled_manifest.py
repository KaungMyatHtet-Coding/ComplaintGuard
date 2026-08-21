import json
import re
from pathlib import Path

import pytest


MANIFEST_PATH = (
    Path(__file__).resolve().parents[2]
    / "evaluation"
    / "controlled"
    / "six_department_long_english_v2a_manifest.json"
)
EXPECTED_LABELS = (
    "transfer_payment",
    "account_support",
    "card_atm",
    "fraud_security",
    "loan_credit",
    "general_support",
)
EXPECTED_BENCHMARK_PROFILE = "long_english_supported_use_v2a"
RESULT_FIELDS = {
    "predictedDepartmentId",
    "predictionConfidence",
    "finalRouteDepartmentId",
    "routingSource",
    "manualReview",
    "manualReviewReason",
    "managerOverride",
    "correctPrediction",
    "correctAutomaticRoute",
    "correctFinalRoute",
}
PRIVATE_PATTERNS = (
    re.compile(r"\b(?:account|card|transaction|reference)\s*(?:number|id)\b", re.I),
    re.compile(r"\b(?:phone|telephone|email|e-mail|address)\b", re.I),
    re.compile(r"@|\b\d{4,}\b"),
)


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_manifest_has_exact_authoritative_coverage() -> None:
    manifest = load_manifest()
    cases = manifest["cases"]
    assert len(cases) == 6
    assert tuple(case["expectedDepartmentId"] for case in cases) == EXPECTED_LABELS
    assert len({case["caseId"] for case in cases}) == 6
    assert all(case["caseId"].startswith("v2a-") for case in cases)


def test_manifest_cases_are_long_english_synthetic_and_predefined() -> None:
    manifest = load_manifest()
    assert manifest["benchmarkProfile"] == EXPECTED_BENCHMARK_PROFILE
    for case in manifest["cases"]:
        words = case["complaintText"].split()
        assert case["benchmarkProfile"] == EXPECTED_BENCHMARK_PROFILE
        assert case["inputLocale"] == "en"
        assert case["textLengthCategory"] == "long"
        assert 45 <= len(words) <= 90
        assert case["wordCount"] == len(words)
        assert case["synthetic"] is True
        assert case["predefinedBeforeInference"] is True
        assert case["complaintText"].strip()
        assert case["expectedLabelRationale"].strip()


def test_manifest_has_no_result_fields_or_private_identifier_patterns() -> None:
    manifest = load_manifest()
    assert "predictions" not in manifest
    assert "results" not in manifest
    for case in manifest["cases"]:
        assert RESULT_FIELDS.isdisjoint(case)
        assert not any(pattern.search(case["complaintText"]) for pattern in PRIVATE_PATTERNS)


def test_manifest_disclosures_state_definition_only_and_no_inference() -> None:
    manifest = load_manifest()
    disclosures = " ".join(manifest["disclosures"]).casefold()
    assert "intended supported-use benchmark" in disclosures
    assert "six predefined long-english synthetic cases" in disclosures
    assert "not official held-out evaluation" in disclosures
    assert "not live-user performance" in disclosures
    assert "no inference executed" in disclosures


def test_manifest_is_not_v1_or_model_result_artifact() -> None:
    manifest = load_manifest()
    assert all(not case["caseId"].startswith("synthetic-") for case in manifest["cases"])
    assert "frozenModel" not in manifest
    assert "summary" not in manifest


@pytest.mark.parametrize("case_index", range(6))
def test_each_case_has_only_required_definition_authority(case_index: int) -> None:
    case = load_manifest()["cases"][case_index]
    assert case["expectedDepartmentId"] in EXPECTED_LABELS
    assert case["expectedDepartmentLabel"]
    assert set(case) == {
        "caseId",
        "benchmarkProfile",
        "inputLocale",
        "textLengthCategory",
        "wordCount",
        "expectedDepartmentId",
        "expectedDepartmentLabel",
        "complaintText",
        "expectedLabelRationale",
        "synthetic",
        "predefinedBeforeInference",
    }
