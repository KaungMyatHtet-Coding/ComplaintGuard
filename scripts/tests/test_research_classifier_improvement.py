from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from scripts.research_classifier_improvement import (
    CANDIDATES,
    LABELS,
    confidence_metrics,
    development_partition,
    metric_summary,
    select_finalist,
    split_development_rows,
)


def test_candidate_matrix_contains_required_explainable_models() -> None:
    assert [(item.vectorizer, item.classifier) for item in CANDIDATES] == [
        ("word", "MultinomialNB"),
        ("word", "ComplementNB"),
        ("word", "LogisticRegression"),
        ("word_char", "LogisticRegression"),
        ("word_char", "LinearSVC"),
    ]


def test_development_partition_is_deterministic_by_normalized_text() -> None:
    assert development_partition("same text") == development_partition("same text")


def test_duplicate_groups_cannot_cross_development_partitions() -> None:
    rows = []
    for index, label in enumerate(LABELS):
        for suffix in range(200):
            rows.append((f"{label} synthetic example {index} {suffix}", label))
    rows.extend(("Repeated narrative", "transfer_payment") for _ in range(3))
    split = split_development_rows(rows)
    containing = [
        name
        for name, values in split.items()
        if any(text == "repeated narrative" for text, _ in values)
    ]
    assert len(containing) == 1


def test_conflicting_exact_duplicate_labels_stay_in_one_partition() -> None:
    rows = []
    for index, label in enumerate(LABELS):
        for suffix in range(200):
            rows.append((f"{label} synthetic example {index} {suffix}", label))
    rows.extend(
        [
            ("same conflict", "transfer_payment"),
            ("same conflict", "account_support"),
        ]
    )
    split = split_development_rows(rows)
    containing = [
        name
        for name, values in split.items()
        if any(text == "same conflict" for text, _ in values)
    ]
    assert len(containing) == 1


def test_metric_and_calibration_summaries_reconcile() -> None:
    y_true = list(LABELS)
    y_pred = np.asarray(LABELS)
    metrics = metric_summary(y_true, y_pred)
    probabilities = np.eye(len(LABELS), dtype=float) * 0.9 + 0.1 / len(LABELS)
    calibration = confidence_metrics(y_true, probabilities, np.asarray(LABELS))

    assert metrics["macro_f1"] == 1.0
    assert metrics["transfer_as_account"] == 0
    assert sum(row["count"] for row in calibration["bins"]) == len(LABELS)
    assert calibration["wrong_high_confidence"]["0.9"] == 0
    assert calibration["multiclass_brier"] >= 0


def test_finalist_gate_rejects_wrong_card_regression() -> None:
    def candidate(candidate_id: str, *, card: str, transfer_recall: float):
        per_class = {label: {"recall": 0.80, "f1": 0.70} for label in LABELS}
        per_class["transfer_payment"]["recall"] = transfer_recall
        return {
            "candidate": {"candidate_id": candidate_id},
            "validation_metrics": {
                "macro_f1": 0.70,
                "transfer_as_account": 10,
                "per_class": per_class,
            },
            "regression_suite": [
                {
                    "case_id": "mobile_transfer_clear",
                    "predicted_department": "account_support",
                    "raw_max_probability": 0.50,
                },
                {
                    "case_id": "account_access",
                    "predicted_department": "account_support",
                },
                {"case_id": "card_payment", "predicted_department": card},
            ],
            "raw_confidence": {
                "wrong_high_confidence": {
                    key: 5 for key in ("0.6", "0.7", "0.8", "0.9")
                }
            },
        }

    baseline = candidate("word_mnb_baseline", card="card_atm", transfer_recall=0.40)
    baseline["validation_metrics"]["transfer_as_account"] = 20
    baseline["raw_confidence"]["wrong_high_confidence"] = {
        key: 10 for key in ("0.6", "0.7", "0.8", "0.9")
    }
    wrong_card = candidate(
        "strong_but_wrong_card", card="account_support", transfer_recall=0.80
    )
    safe = candidate("safe", card="card_atm", transfer_recall=0.50)

    assert (
        select_finalist([baseline, wrong_card, safe])["candidate"]["candidate_id"]
        == "safe"
    )


def test_finalist_gate_rejects_material_other_class_regression() -> None:
    # Exercise the real completed artifact so the judgment threshold cannot be
    # weakened without changing this evidence-backed test.
    path = (
        Path(__file__).resolve().parents[2]
        / "evaluation"
        / "research"
        / "phase2a_classifier_experiments.json"
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    complement = next(
        row
        for row in data["candidates"]
        if row["candidate"]["candidate_id"] == "word_complement_nb"
    )
    assert complement["validation_metrics"]["per_class"]["loan_credit"]["f1"] < (
        0.7074766355140187 - 0.03
    )
    assert select_finalist(data["candidates"]) is None


def test_research_metrics_are_validation_only_and_privacy_safe() -> None:
    path = (
        Path(__file__).resolve().parents[2]
        / "evaluation"
        / "research"
        / "phase2a_classifier_experiments.json"
    )
    data = json.loads(path.read_text(encoding="utf-8"))

    assert data["schema_version"] == 1
    assert data["status"] == "completed"
    assert data["research_only"] is True
    assert data["held_out_test_evaluated"] is False
    assert data["original_validation_evaluated"] is False
    assert data["locked_partitions"]["test"]["rows"] == 29_942
    assert data["recommended_finalist"] is None
    assert len(data["candidates"]) == 5
    assert data["privacy"] == {
        "contains_narratives": False,
        "contains_complaint_ids": False,
        "aggregate_or_synthetic_only": True,
    }
    serialized = path.read_text(encoding="utf-8").casefold()
    assert "i transferred money through mobile banking" not in serialized
    assert "consumer complaint narrative" not in serialized
