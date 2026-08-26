"""Offline V2B evaluator for the committed long-English case manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import DEFAULT_ROUTING_CONFIDENCE_THRESHOLD, MODEL_SHA256, MODEL_VERSION
from app.language import detect_language
from app.model import LABELS, FrozenDepartmentClassifier, ModelArtifactError

EXPECTED_MANIFEST_SHA256 = "6043166a0c5660b201d6aecccb997fb2caa2fac50164415e06190119f38e62c7"
EXPECTED_MODEL_SHA256 = "bafc086fe5b11bdcc5cbc4f04f3f3f222de8cbad27fe66d62a6685cc30f953d5"
EXPECTED_MODEL_VERSION = "v1"
EXPECTED_LABELS = (
    "transfer_payment",
    "account_support",
    "card_atm",
    "fraud_security",
    "loan_credit",
    "general_support",
)
EXPECTED_THRESHOLD = 0.60
EXPECTED_PROFILE = "long_english_supported_use_v2a"
EXPECTED_CASES = (
    ("v2a-transfer-payment-001", 59, "transfer_payment"),
    ("v2a-account-support-001", 54, "account_support"),
    ("v2a-card-atm-001", 57, "card_atm"),
    ("v2a-fraud-security-001", 59, "fraud_security"),
    ("v2a-loan-credit-001", 54, "loan_credit"),
    ("v2a-general-support-001", 56, "general_support"),
)
MANIFEST_RELATIVE_PATH = "evaluation/controlled/six_department_long_english_v2a_manifest.json"
DEFAULT_OUTPUT = Path("evaluation/controlled/six_department_long_english_supported_use_v2b.json")
RESULT_CONTRACT_VERSION = "controlled-result-v2b"
PRIVATE_PATTERNS = (
    re.compile(r"\b(?:account|card|transaction|reference)\s*(?:number|id)\b", re.I),
    re.compile(r"\b(?:phone|telephone|email|e-mail|address)\b", re.I),
    re.compile(r"@|\b\d{4,}\b"),
)


class Predictor(Protocol):
    model_version: str
    threshold: float

    def predict(self, text: str) -> Any: ...


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def validate_frozen_contract() -> None:
    if MODEL_SHA256.casefold() != EXPECTED_MODEL_SHA256:
        raise ModelArtifactError("committed model hash constant is incompatible")
    if MODEL_VERSION != EXPECTED_MODEL_VERSION:
        raise ModelArtifactError("committed model version is incompatible")
    if tuple(LABELS) != EXPECTED_LABELS:
        raise ModelArtifactError("committed department label order is incompatible")
    if DEFAULT_ROUTING_CONFIDENCE_THRESHOLD != EXPECTED_THRESHOLD:
        raise ModelArtifactError("operational threshold is incompatible")


def validate_manifest(manifest: dict[str, Any], manifest_sha256: str) -> None:
    if manifest_sha256 != EXPECTED_MANIFEST_SHA256:
        raise ValueError("V2A manifest hash is incompatible")
    if manifest.get("schemaVersion") != "controlled-case-manifest-v2a":
        raise ValueError("V2A manifest schema is incompatible")
    if manifest.get("benchmarkProfile") != EXPECTED_PROFILE:
        raise ValueError("V2A benchmark profile is incompatible")
    cases = manifest.get("cases")
    if not isinstance(cases, list) or len(cases) != len(EXPECTED_CASES):
        raise ValueError("V2A manifest must contain exactly six cases")
    result_fields = {
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
    for case, expected in zip(cases, EXPECTED_CASES, strict=True):
        if (
            case.get("caseId"),
            case.get("wordCount"),
            case.get("expectedDepartmentId"),
        ) != expected:
            raise ValueError("V2A case order, ID, word count, or label drifted")
        if case.get("benchmarkProfile") != EXPECTED_PROFILE or case.get("inputLocale") != "en":
            raise ValueError("V2A case profile or locale is incompatible")
        if case.get("textLengthCategory") != "long":
            raise ValueError("V2A cases must be long English cases")
        if case.get("synthetic") is not True or case.get("predefinedBeforeInference") is not True:
            raise ValueError("V2A cases must be synthetic and predefined")
        if case.get("wordCount") != len(str(case.get("complaintText", "")).split()):
            raise ValueError("V2A word count does not match complaint text")
        if result_fields.intersection(case):
            raise ValueError("V2A manifest contains result fields")
        text = str(case.get("complaintText", ""))
        if not text.strip() or any(pattern.search(text) for pattern in PRIVATE_PATTERNS):
            raise ValueError("V2A complaint text contains private content")


def load_manifest(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    digest = sha256_bytes(raw)
    manifest = json.loads(raw.decode("utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("V2A manifest must be an object")
    validate_manifest(manifest, digest)
    return manifest, digest


def evaluate_cases(
    predictor: Predictor,
    manifest: dict[str, Any],
    *,
    manifest_sha256: str,
    generated_at_utc: str,
) -> dict[str, Any]:
    validate_manifest(manifest, manifest_sha256)
    if predictor.model_version != EXPECTED_MODEL_VERSION:
        raise ModelArtifactError("loaded model version is incompatible")
    if predictor.threshold != 0.0:
        raise ModelArtifactError("loaded historical threshold is incompatible")

    results: list[dict[str, Any]] = []
    for case in manifest["cases"]:
        detected_language = detect_language(case["complaintText"])
        predicted_id: str | None = None
        confidence: float | None = None
        manual_reason: str | None = None
        if detected_language == "en":
            prediction = predictor.predict(case["complaintText"])
            predicted_id = str(prediction.department_id)
            confidence = float(prediction.confidence)
            if predicted_id not in EXPECTED_LABELS or not 0.0 <= confidence <= 1.0:
                raise ModelArtifactError("prediction is outside the controlled contract")
            manual_review = confidence < EXPECTED_THRESHOLD
            manual_reason = "low_prediction_confidence" if manual_review else None
        else:
            manual_review = True
            manual_reason = "language_policy_manual_review" if detected_language in {"my", "mixed"} else "unsupported_language"

        routing_source = "manual_review" if manual_review else "model"
        final_route = None if manual_review else predicted_id
        classifier_matches = predicted_id == case["expectedDepartmentId"]
        correct_automatic = (
            classifier_matches
            and routing_source == "model"
            and confidence is not None
            and confidence >= EXPECTED_THRESHOLD
            and final_route == case["expectedDepartmentId"]
        )
        results.append(
            {
                "caseId": case["caseId"],
                "expectedDepartmentId": case["expectedDepartmentId"],
                "predictedDepartmentId": predicted_id,
                "predictionConfidence": confidence,
                "detectedLanguage": detected_language,
                "routingSource": routing_source,
                "manualReview": manual_review,
                "manualReviewReason": manual_reason,
                "finalRouteDepartmentId": final_route,
                "classifierPredictionMatches": classifier_matches,
                "correctAutomaticRoute": correct_automatic,
                "managerOverride": False,
                "modelVersion": EXPECTED_MODEL_VERSION,
                "operationalThreshold": EXPECTED_THRESHOLD,
            }
        )

    automatic = [result for result in results if result["routingSource"] == "model"]
    manual = [result for result in results if result["manualReview"]]
    matches = [result for result in results if result["classifierPredictionMatches"]]
    correct_automatic = [result for result in results if result["correctAutomaticRoute"]]
    correct_manual = [result for result in manual if result["classifierPredictionMatches"]]
    confident_incorrect = [
        result
        for result in automatic
        if not result["classifierPredictionMatches"]
        and result["predictionConfidence"] is not None
        and result["predictionConfidence"] >= EXPECTED_THRESHOLD
    ]
    return {
        "evidenceType": "controlled six-case long-English supported-use demonstration",
        "generatedAtUtc": generated_at_utc,
        "inputManifest": {"path": MANIFEST_RELATIVE_PATH, "sha256": manifest_sha256},
        "frozenModel": {
            "modelVersion": EXPECTED_MODEL_VERSION,
            "modelSha256": EXPECTED_MODEL_SHA256,
            "operationalThreshold": EXPECTED_THRESHOLD,
            "labelOrder": list(EXPECTED_LABELS),
        },
        "resultContractVersion": RESULT_CONTRACT_VERSION,
        "cases": results,
        "summary": {
            "totalCases": len(results),
            "classifierPredictionMatchCount": len(matches),
            "classifierPredictionMatchRate": round(len(matches) / len(results) * 100, 4),
            "automaticRouteCount": len(automatic),
            "correctAutomaticRouteCount": len(correct_automatic),
            "automaticRoutingSuccessRate": round(len(correct_automatic) / len(automatic) * 100, 4)
            if automatic
            else 0.0,
            "manualReviewCount": len(manual),
            "correctPredictionsSentToManualReview": len(correct_manual),
            "incorrectPredictionsSentToManualReview": len(manual) - len(correct_manual),
            "confidentIncorrectAutomaticRouteCount": len(confident_incorrect),
        },
        "limitations": [
            "One predefined synthetic long-English case per department; the sample is too small to establish overall performance.",
            "Not official model accuracy, frozen held-out evaluation, or live-user performance.",
            "Expected labels and wording were committed before inference.",
            "Confidence values are uncalibrated.",
            "No Manager override was simulated.",
            "Myanmar and mixed-language behavior remains governed by the manual-review policy and is not evaluated by this English manifest.",
        ],
    }


def write_result(result: dict[str, Any], output_path: Path, repository_root: Path) -> None:
    controlled_root = (repository_root / "evaluation" / "controlled").resolve()
    destination = (repository_root / output_path if not output_path.is_absolute() else output_path).resolve()
    if controlled_root not in destination.parents or destination.suffix != ".json":
        raise ValueError("V2B result must be a JSON file under evaluation/controlled")
    if destination.exists():
        raise FileExistsError("V2B result already exists; refusing overwrite")
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def run(output_path: Path = DEFAULT_OUTPUT, *, generated_at_utc: str | None = None) -> dict[str, Any]:
    repository_root = Path(__file__).resolve().parents[2]
    manifest_path = repository_root / MANIFEST_RELATIVE_PATH
    manifest, manifest_sha256 = load_manifest(manifest_path)
    validate_frozen_contract()
    model_path = repository_root / "models" / "generated" / "cfpb_department_model_v1.joblib"
    classifier = FrozenDepartmentClassifier.load(model_path, expected_sha256=EXPECTED_MODEL_SHA256)
    result = evaluate_cases(
        classifier,
        manifest,
        manifest_sha256=manifest_sha256,
        generated_at_utc=generated_at_utc or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )
    write_result(result, output_path, repository_root)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = run(args.output)
    print(
        "V2B complete: "
        f"{result['summary']['classifierPredictionMatchCount']}/{result['summary']['totalCases']} classifier matches; "
        f"{result['summary']['correctAutomaticRouteCount']}/{result['summary']['automaticRouteCount']} correct automatic routes"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
