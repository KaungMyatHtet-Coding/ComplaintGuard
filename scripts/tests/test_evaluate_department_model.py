from __future__ import annotations

import numpy as np
import pytest

from scripts.evaluate_department_model import (
    confidence_analysis,
    example_metadata,
    validate_public_artifact,
)


def test_confidence_analysis_reconciles_bins_and_threshold_groups() -> None:
    true = ["card_atm", "loan_credit", "card_atm", "general_support"]
    predicted = np.asarray(["card_atm", "card_atm", "card_atm", "loan_credit"])
    confidences = np.asarray([0.39, 0.59, 0.60, 0.95])
    result = confidence_analysis(true, predicted, confidences)
    assert sum(item["count"] for item in result["bins"]) == 4
    assert result["below_operational_threshold"]["count"] == 2
    assert result["at_or_above_operational_threshold"]["count"] == 2
    assert result["definition"].endswith("not calibrated reliability")


@pytest.mark.parametrize(
    "values", [np.asarray([]), np.asarray([float("nan")]), np.asarray([1.1])]
)
def test_confidence_analysis_rejects_invalid_values(values: np.ndarray) -> None:
    with pytest.raises(ValueError):
        confidence_analysis(
            ["card_atm"] * len(values), np.asarray(["card_atm"] * len(values)), values
        )


def test_example_metadata_contains_no_narrative() -> None:
    rows = [("private example one", "card_atm"), ("private example two", "loan_credit")]
    result = example_metadata(
        rows, np.asarray(["card_atm", "card_atm"]), np.asarray([0.8, 0.7])
    )
    serialized = str(result)
    assert "private example" not in serialized
    assert len(result["correct"]) == 1
    assert len(result["misclassified"]) == 1
    assert result["correct"][0]["contains_narrative"] is False


def test_example_metadata_handles_exact_duplicate_text() -> None:
    rows = [("same text", "card_atm"), ("same text", "loan_credit")]
    result = example_metadata(
        rows, np.asarray(["card_atm", "card_atm"]), np.asarray([0.8, 0.8])
    )
    assert len(result["correct"]) == 1
    assert len(result["misclassified"]) == 1


def test_public_schema_reconciles() -> None:
    labels = (
        "transfer_payment",
        "account_support",
        "card_atm",
        "fraud_security",
        "loan_credit",
        "general_support",
    )
    artifact = {
        "schema_version": 1,
        "status": "completed",
        "metadata": {},
        "dataset_pipeline": {},
        "partitions": {"test": {"rows": 6}},
        "class_distribution": {},
        "metrics": {
            "per_department": {label: {"support": 1} for label in labels},
            "confusion_matrix": {"values": np.eye(6, dtype=int).tolist()},
        },
        "confidence_analysis": {"bins": [{"count": 6}]},
        "examples": {},
        "historical_similarity": {},
        "privacy": {"contains_narratives": False},
        "limitations": [],
    }
    validate_public_artifact(artifact)
    artifact["privacy"]["contains_narratives"] = True
    with pytest.raises(RuntimeError):
        validate_public_artifact(artifact)
