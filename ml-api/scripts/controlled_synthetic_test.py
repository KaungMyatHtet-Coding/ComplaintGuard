"""Offline, reproducible six-department controlled model demonstration.

This runner uses the existing prediction-only frozen-model boundary. It never
imports Firebase, starts a service, writes application data, or overwrites an
official evaluation artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import (
    DEFAULT_ROUTING_CONFIDENCE_THRESHOLD,
    MODEL_SHA256,
    MODEL_VERSION,
)
from app.model import LABELS, FrozenDepartmentClassifier, ModelArtifactError

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
EXPECTED_HISTORICAL_THRESHOLD = 0.0
EXPECTED_OPERATIONAL_THRESHOLD = 0.60
EVIDENCE_TYPE = "controlled synthetic demonstration"
DEFAULT_OUTPUT = Path("evaluation/controlled/six_department_synthetic_v1.json")

DEPARTMENT_LABELS = {
    "transfer_payment": "Transfer & Payment",
    "account_support": "Account Support",
    "card_atm": "Card & ATM",
    "fraud_security": "Fraud & Security",
    "loan_credit": "Loan & Credit",
    "general_support": "General Support",
}


@dataclass(frozen=True)
class ControlledCase:
    case_id: str
    input_locale: str
    text_length_category: str
    expected_department_id: str
    expected_department_label: str
    synthetic_input: str


class Predictor(Protocol):
    model_version: str
    threshold: float

    def predict(self, text: str) -> Any: ...


CASES = (
    ControlledCase(
        "synthetic-transfer-payment-001",
        "en",
        "short",
        "transfer_payment",
        DEPARTMENT_LABELS["transfer_payment"],
        "A synthetic transfer shows completed, but the recipient has not received the funds.",
    ),
    ControlledCase(
        "synthetic-account-support-001",
        "en",
        "short",
        "account_support",
        DEPARTMENT_LABELS["account_support"],
        "A synthetic banking account is locked and needs help updating its profile.",
    ),
    ControlledCase(
        "synthetic-card-atm-001",
        "en",
        "short",
        "card_atm",
        DEPARTMENT_LABELS["card_atm"],
        "A synthetic debit card was declined at an ATM during a cash withdrawal.",
    ),
    ControlledCase(
        "synthetic-fraud-security-001",
        "en",
        "short",
        "fraud_security",
        DEPARTMENT_LABELS["fraud_security"],
        "A synthetic card purchase was not authorized and should be reported as suspected fraud.",
    ),
    ControlledCase(
        "synthetic-loan-credit-001",
        "en",
        "short",
        "loan_credit",
        DEPARTMENT_LABELS["loan_credit"],
        "A synthetic loan statement shows an unexpected interest charge on the repayment amount.",
    ),
    ControlledCase(
        "synthetic-general-support-001",
        "en",
        "medium",
        "general_support",
        DEPARTMENT_LABELS["general_support"],
        "A synthetic banking customer needs general help understanding which service can answer a question.",
    ),
)


def validate_environment_contract() -> None:
    """Fail closed if the committed frozen-model contract has drifted."""

    if MODEL_SHA256 != EXPECTED_MODEL_SHA256:
        raise ModelArtifactError("committed model hash constant is incompatible")
    if MODEL_VERSION != EXPECTED_MODEL_VERSION:
        raise ModelArtifactError("committed model version is incompatible")
    if tuple(LABELS) != EXPECTED_LABELS:
        raise ModelArtifactError("committed department label order is incompatible")
    if DEFAULT_ROUTING_CONFIDENCE_THRESHOLD != EXPECTED_OPERATIONAL_THRESHOLD:
        raise ModelArtifactError("operational threshold is incompatible")


def validate_cases(cases: tuple[ControlledCase, ...] = CASES) -> None:
    """Validate immutable, synthetic, exactly-once department coverage."""

    if len(cases) != len(EXPECTED_LABELS):
        raise ValueError("controlled test must contain exactly six cases")
    if tuple(case.expected_department_id for case in cases) != EXPECTED_LABELS:
        raise ValueError("expected departments must use the authoritative order")
    seen_ids: set[str] = set()
    for case in cases:
        if case.case_id in seen_ids or not case.case_id.startswith("synthetic-"):
            raise ValueError("case IDs must be unique synthetic identifiers")
        seen_ids.add(case.case_id)
        if case.input_locale != "en":
            raise ValueError("this controlled slice accepts English cases only")
        if case.expected_department_label != DEPARTMENT_LABELS[case.expected_department_id]:
            raise ValueError("department label does not match its stable ID")
        if not case.synthetic_input.strip() or len(case.synthetic_input) > 500:
            raise ValueError("synthetic case text is empty or too long")
        if any(character.isdigit() for character in case.synthetic_input):
            raise ValueError("synthetic case text must not contain numeric identifiers")
        lowered = case.synthetic_input.casefold()
        if any(marker in lowered for marker in ("@", "phone", "account number", "card number")):
            raise ValueError("synthetic case text contains a private-identifier marker")


def _request_fingerprint(cases: tuple[ControlledCase, ...]) -> str:
    payload = json.dumps([asdict(case) for case in cases], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def prepare_case_definition(cases: tuple[ControlledCase, ...] = CASES) -> str:
    """Validate and hash the frozen case definition before model loading."""

    validate_cases(cases)
    return _request_fingerprint(cases)


def evaluate_cases(
    predictor: Predictor,
    *,
    generated_at_utc: str,
    case_definition_sha256: str,
    cases: tuple[ControlledCase, ...] = CASES,
) -> dict[str, Any]:
    """Evaluate cases without mutating the predictor or any application store."""

    validate_cases(cases)
    if not re.fullmatch(r"[0-9a-f]{64}", case_definition_sha256):
        raise ValueError("case definition hash must be lowercase SHA-256")
    if predictor.model_version != EXPECTED_MODEL_VERSION:
        raise ModelArtifactError("loaded model version is incompatible")
    if predictor.threshold != EXPECTED_HISTORICAL_THRESHOLD:
        raise ModelArtifactError("loaded historical threshold is incompatible")

    results: list[dict[str, Any]] = []
    for case in cases:
        prediction = predictor.predict(case.synthetic_input)
        predicted_id = str(prediction.department_id)
        confidence = float(prediction.confidence)
        if predicted_id not in EXPECTED_LABELS or not 0.0 <= confidence <= 1.0:
            raise ModelArtifactError("prediction is outside the controlled contract")
        manual_review = confidence < EXPECTED_OPERATIONAL_THRESHOLD
        final_route = None if manual_review else predicted_id
        routing_source = "manual_review" if manual_review else "model"
        raw_prediction_matches = predicted_id == case.expected_department_id
        correct_automatic_route = (
            raw_prediction_matches
            and routing_source == "model"
            and confidence >= EXPECTED_OPERATIONAL_THRESHOLD
            and final_route == case.expected_department_id
        )
        results.append(
            {
                "caseId": case.case_id,
                "inputLocale": case.input_locale,
                "textLengthCategory": case.text_length_category,
                "expectedDepartmentId": case.expected_department_id,
                "expectedDepartmentLabel": case.expected_department_label,
                "syntheticInput": case.synthetic_input,
                "predictedDepartmentId": predicted_id,
                "predictionConfidence": confidence,
                "finalRouteDepartmentId": final_route,
                "routingSource": routing_source,
                "manualReview": manual_review,
                "manualReviewReason": "low_prediction_confidence" if manual_review else None,
                "managerOverride": False,
                "classifierPredictionMatches": raw_prediction_matches,
                "correctPrediction": raw_prediction_matches,
                "correctAutomaticRoute": correct_automatic_route,
                "correctFinalRoute": None if final_route is None else final_route == case.expected_department_id,
                "modelVersion": EXPECTED_MODEL_VERSION,
                "operationalThreshold": EXPECTED_OPERATIONAL_THRESHOLD,
            }
        )

    classifier_match_count = sum(bool(result["classifierPredictionMatches"]) for result in results)
    automatic_count = sum(result["routingSource"] == "model" for result in results)
    correct_automatic_count = sum(bool(result["correctAutomaticRoute"]) for result in results)
    manual_count = len(results) - automatic_count
    correct_manual_count = sum(
        result["manualReview"] and result["classifierPredictionMatches"] for result in results
    )
    return {
        "evidenceType": EVIDENCE_TYPE,
        "generatedAtUtc": generated_at_utc,
        "reproducibility": {
            "caseDefinitionSha256": case_definition_sha256,
            "expectedLabelsFrozenBeforeInference": True,
            "caseDefinitionHashComputedBeforeModelLoad": True,
            "networkAccess": False,
            "writesApplicationData": False,
        },
        "frozenModel": {
            "modelVersion": EXPECTED_MODEL_VERSION,
            "modelSha256": EXPECTED_MODEL_SHA256,
            "historicalValidationSelectedThreshold": EXPECTED_HISTORICAL_THRESHOLD,
            "operationalThreshold": EXPECTED_OPERATIONAL_THRESHOLD,
            "labelOrder": list(EXPECTED_LABELS),
        },
        "cases": results,
        "summary": {
            "totalCases": len(results),
            "classifierPredictionMatchCount": classifier_match_count,
            "classifierPredictionMatchRate": round(classifier_match_count / len(results) * 100, 4),
            "automaticRouteCount": automatic_count,
            "correctAutomaticRouteCount": correct_automatic_count,
            "automaticRoutingSuccessRate": round(correct_automatic_count / automatic_count * 100, 4)
            if automatic_count
            else 0.0,
            "manualReviewCount": manual_count,
            "correctPredictionsSentToManualReview": correct_manual_count,
            "incorrectPredictionsSentToManualReview": manual_count - correct_manual_count,
            "managerOverrideCount": 0,
        },
        "limitations": [
            "Controlled six-case synthetic demonstration; one predefined English case per department.",
            "Not official model accuracy, frozen held-out evaluation, or live-user performance.",
            "Expected labels were predefined before inference and are demonstration labels only.",
            "Confidence values are uncalibrated and manual review is not counted as a correct automatic prediction.",
            "Myanmar and mixed-language policy behavior is not evaluated in this six-case percentage.",
        ],
    }


def write_artifact(artifact: dict[str, Any], output_path: Path, *, repository_root: Path) -> None:
    """Write only to the dedicated controlled-evidence directory, once."""

    controlled_root = (repository_root / "evaluation" / "controlled").resolve()
    destination = output_path if output_path.is_absolute() else repository_root / output_path
    destination = destination.resolve()
    if controlled_root not in destination.parents or destination.suffix != ".json":
        raise ValueError("controlled output must be a JSON file under evaluation/controlled")
    if destination.exists():
        raise FileExistsError("controlled evidence already exists; refusing overwrite")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def run(output_path: Path = DEFAULT_OUTPUT, *, generated_at_utc: str | None = None) -> dict[str, Any]:
    validate_environment_contract()
    case_definition_sha256 = prepare_case_definition()
    repository_root = Path(__file__).resolve().parents[2]
    model_path = repository_root / "models" / "generated" / "cfpb_department_model_v1.joblib"
    classifier = FrozenDepartmentClassifier.load(model_path, expected_sha256=EXPECTED_MODEL_SHA256)
    artifact = evaluate_cases(
        classifier,
        generated_at_utc=generated_at_utc or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        case_definition_sha256=case_definition_sha256,
    )
    write_artifact(artifact, output_path, repository_root=repository_root)
    return artifact


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    artifact = run(args.output)
    print(f"Controlled synthetic demonstration complete: {artifact['summary']['totalCases']} cases")
    print(
        "Automatic-routing success: "
        f"{artifact['summary']['correctAutomaticRouteCount']}/{artifact['summary']['automaticRouteCount']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
