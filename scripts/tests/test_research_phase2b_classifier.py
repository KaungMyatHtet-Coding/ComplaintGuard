from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.frozen import FrozenEstimator

from scripts.research_phase2b_classifier import (
    CORE_MATRIX_IDS,
    LABELS,
    NEAR_DUPLICATE_THRESHOLD,
    acceptance_gates,
    candidate_specs,
    confidence_metrics,
    development_partition,
    exact_duplicate_variant,
    hierarchy_probability_matrix,
    near_duplicate_variant,
    ProbabilityEstimator,
    split_development_rows,
)


def _development_rows() -> list[tuple[str, str]]:
    rows = []
    for index, label in enumerate(LABELS):
        for suffix in range(240):
            rows.append((f"{label} synthetic narrative {index} {suffix}", label))
    return rows


def test_predeclared_matrix_groups_are_exact() -> None:
    assert tuple(CORE_MATRIX_IDS) == (
        "MNB-0",
        "CNB-0",
        "LR-W",
        "LR-WC",
        "HIER-WC",
        "MNB-SW",
        "MNB-C15",
        "CNB-SET",
        "DQ-EXACT",
        "DQ-CONFLICT",
        "DQ-NEAR",
    )
    assert {spec.matrix_id for spec in candidate_specs()} == set(CORE_MATRIX_IDS)


def test_development_partition_is_deterministic() -> None:
    assert development_partition("same text") == development_partition("same text")


def test_exact_groups_stay_in_one_development_partition() -> None:
    rows = _development_rows()
    rows.extend(("Repeated narrative", "transfer_payment") for _ in range(3))
    split = split_development_rows(rows)
    containing = [
        name
        for name, values in split.items()
        if any(text == "repeated narrative" for text, _ in values)
    ]
    assert len(containing) == 1


def test_conflicting_groups_stay_together_without_relabeling() -> None:
    rows = _development_rows()
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
    assert {
        label
        for values in split.values()
        for text, label in values
        if text == "same conflict"
    } == {"transfer_payment", "account_support"}


def test_exact_duplicate_variant_only_collapses_same_label_groups() -> None:
    rows = [
        ("same text", "transfer_payment"),
        ("same text", "transfer_payment"),
        ("conflict", "transfer_payment"),
        ("conflict", "account_support"),
    ]
    result = exact_duplicate_variant(rows)
    assert result.count(("same text", "transfer_payment")) == 1
    assert ("conflict", "transfer_payment") in result
    assert ("conflict", "account_support") in result


def test_near_duplicate_rule_is_fixed_and_deterministic() -> None:
    rows = [
        ("transfer payment failed for recipient", "transfer_payment"),
        ("transfer payment failed for the recipient", "transfer_payment"),
        ("cannot access my checking account", "account_support"),
        ("my debit card was declined", "card_atm"),
    ]
    first_rows, first_summary = near_duplicate_variant(rows)
    second_rows, second_summary = near_duplicate_variant(rows)
    assert first_rows == second_rows
    assert first_summary == second_summary
    assert first_summary["threshold_cosine_similarity"] == NEAR_DUPLICATE_THRESHOLD
    assert first_summary["method"] == "char_wb_tfidf_4_5_mutual_nearest_neighbor"
    assert first_summary["fit_rows_after_near_collapse"] <= len(rows)


def test_hierarchical_probabilities_reconcile() -> None:
    stage_one = np.asarray([[0.8, 0.2], [0.1, 0.9]])
    stage_two = np.asarray(
        [
            [0.5, 0.2, 0.1, 0.1, 0.1],
            [0.1, 0.4, 0.2, 0.2, 0.1],
        ]
    )
    probabilities = hierarchy_probability_matrix(
        stage_one,
        ["fraud_security", "other"],
        stage_two,
        [
            "transfer_payment",
            "account_support",
            "card_atm",
            "loan_credit",
            "general_support",
        ],
    )
    assert np.allclose(probabilities.sum(axis=1), 1.0)
    assert probabilities[0, LABELS.index("fraud_security")] == 0.8


def test_composite_probability_calibration_is_prefit_and_deterministic() -> None:
    labels = np.repeat(np.asarray(LABELS), 5)
    probabilities = np.tile(
        np.eye(len(LABELS), dtype=float) * 0.9 + 0.1 / len(LABELS), (5, 1)
    )
    calibrated = CalibratedClassifierCV(
        FrozenEstimator(ProbabilityEstimator(tuple(LABELS))), method="sigmoid"
    )
    calibrated.fit(probabilities, labels)
    assert calibrated.predict_proba(probabilities).shape == probabilities.shape


def test_confidence_summary_reconciles() -> None:
    labels = np.asarray(LABELS)
    probabilities = np.eye(len(LABELS), dtype=float) * 0.9 + 0.1 / len(LABELS)
    summary = confidence_metrics(labels.tolist(), probabilities, labels)
    assert sum(row["count"] for row in summary["bins"]) == len(LABELS)
    assert summary["wrong_high_confidence"]["0.9"] == 0
    assert summary["multiclass_brier"] >= 0


def _gate_fixture() -> tuple[dict, dict]:
    per_class = {
        label: {"precision": 0.8, "recall": 0.8, "f1": 0.8, "support": 100}
        for label in LABELS
    }
    metrics = {
        "macro_f1": 0.8,
        "weighted_f1": 0.84,
        "per_class": per_class,
        "transfer_as_account": 10,
        "account_as_transfer": 5,
    }
    lengths = [
        {"minimum_characters": 0, "maximum_characters": 100, "macro_f1": 0.6},
        {"minimum_characters": 101, "maximum_characters": 300, "macro_f1": 0.6},
        {"minimum_characters": 301, "maximum_characters": 1000, "macro_f1": 0.7},
        {"minimum_characters": 1001, "maximum_characters": None, "macro_f1": 0.7},
    ]
    confidence = {
        "ece": 0.03,
        "multiclass_brier": 0.20,
        "wrong_high_confidence": {str(value): 1 for value in (0.6, 0.7, 0.8, 0.9)},
    }
    synthetic = [
        {
            "case_id": case_id,
            "expected_department": expected,
            "predicted_department": expected,
            "safe_at_0_60": True,
        }
        for case_id, _text, expected in (
            ("account_access", "", "account_support"),
            ("card_payment", "", "card_atm"),
            ("fraud", "", "fraud_security"),
            ("loan", "", "loan_credit"),
        )
    ]
    baseline = {
        "validation_metrics": {
            **metrics,
            "per_class": {
                label: {
                    **values,
                    "f1": 0.75,
                    "recall": 0.75,
                }
                for label, values in per_class.items()
            },
        },
        "text_length_metrics": lengths,
        "fraud_metrics": {
            "false_positive_rate": 0.094,
            "false_negative_rate": 0.143,
        },
        "calibrated_confidence": {
            "ece": 0.037,
            "multiclass_brier": 0.221,
            "wrong_high_confidence": {
                str(value): 2 for value in (0.6, 0.7, 0.8, 0.9)
            },
        },
    }
    candidate = {
        "validation_metrics": metrics,
        "text_length_metrics": lengths,
        "fraud_metrics": {
            "false_positive_rate": 0.094,
            "false_negative_rate": 0.143,
        },
        "calibrated_confidence": confidence,
        "synthetic_regression": synthetic,
    }
    return baseline, candidate


def test_acceptance_gate_rejects_short_text_regression() -> None:
    baseline, candidate = _gate_fixture()
    candidate["text_length_metrics"][0]["macro_f1"] = 0.50
    result = acceptance_gates(candidate, baseline)
    assert result["passed"] is False
    assert "short_0_100_improvement" in result["failed_checks"]


def test_acceptance_gate_rejects_loan_regression() -> None:
    baseline, candidate = _gate_fixture()
    candidate["validation_metrics"]["per_class"]["loan_credit"]["f1"] = 0.60
    result = acceptance_gates(candidate, baseline)
    assert result["passed"] is False
    assert "loan_f1_protected" in result["failed_checks"]


def test_completed_artifacts_are_development_only_and_privacy_safe() -> None:
    root = Path(__file__).resolve().parents[2]
    experiment_path = root / "evaluation" / "research" / "phase2b_classifier_experiments.json"
    audit_path = root / "data" / "processed" / "phase2b_data_quality_audit.json"
    experiment = json.loads(experiment_path.read_text(encoding="utf-8"))
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert experiment["status"] == "completed"
    assert experiment["held_out_test_evaluated"] is False
    assert experiment["original_validation_evaluated"] is False
    assert experiment["finalist"] is None
    assert len(experiment["candidates"]) == 13
    assert experiment["privacy"]["aggregate_or_synthetic_only"] is True
    assert audit["privacy"]["aggregate_or_synthetic_only"] is True
    serialized = experiment_path.read_text(encoding="utf-8").casefold()
    assert "i transferred money through mobile banking" not in serialized
    assert "consumer complaint narrative" not in serialized
    assert "complaint id" not in serialized
