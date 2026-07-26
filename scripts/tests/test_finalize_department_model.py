from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.naive_bayes import MultinomialNB

from scripts.finalize_department_model import (
    CANDIDATES,
    THRESHOLDS,
    FinalizationConfig,
    FinalizationError,
    apply_confidence_threshold,
    finalize_model,
    select_threshold,
)
from scripts.train_department_baseline import INPUT_COLUMNS, LABELS, normalize_text


def synthetic_rows(per_label: int = 120) -> list[tuple[str, str]]:
    return [
        (
            "Fictional {0} help topic {0} sequence {1}".format(
                label.replace("_", " "), index
            ),
            label,
        )
        for label in LABELS
        for index in range(per_label)
    ]


def write_inputs(root: Path, rows: list[tuple[str, str]]) -> FinalizationConfig:
    input_path = root / "training_v1.csv"
    pd.DataFrame(rows, columns=list(INPUT_COLUMNS)).to_csv(input_path, index=False)
    counts = {
        label: sum(row_label == label for _, row_label in rows) for label in LABELS
    }
    manifest_path = root / "training_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "status": "completed",
                "dataset_version": "v1",
                "mapping_version": "v1",
                "output": {
                    "file_name": input_path.name,
                    "schema": list(INPUT_COLUMNS),
                    "rows": len(rows),
                },
                "label_counts": counts,
            }
        ),
        encoding="utf-8",
    )
    baseline_path = root / "baseline_metrics.json"
    baseline_path.write_text(
        json.dumps(
            {
                "status": "completed",
                "dataset_version": "v1",
                "mapping_version": "v1",
                "configuration": {"seed": 20260727},
                "selection": {"selected_rows": len(rows)},
                "test_metrics": {
                    "accuracy": 0.5,
                    "balanced_accuracy": 0.5,
                    "macro": {"f1": 0.5},
                },
            }
        ),
        encoding="utf-8",
    )
    return FinalizationConfig(
        input_path=input_path,
        input_manifest_path=manifest_path,
        baseline_metrics_path=baseline_path,
        metrics_path=root / "final_metrics.json",
        model_path=root / "final_model.joblib",
        chunk_size=31,
        max_rows=len(rows),
    )


def test_candidate_search_is_fixed_and_contains_baseline() -> None:
    assert len(CANDIDATES) == 4
    assert CANDIDATES[0].candidate_id == "baseline_reference"
    assert CANDIDATES[0].alpha == 1.0
    assert CANDIDATES[0].ngram_range == (1, 2)
    assert THRESHOLDS == (0.0, 0.35, 0.45, 0.55, 0.65)


def test_confidence_threshold_routes_only_low_confidence() -> None:
    model = MultinomialNB()
    model.classes_ = np.asarray(LABELS, dtype=object)
    probabilities = np.asarray(
        [
            [0.8, 0.04, 0.04, 0.04, 0.04, 0.04],
            [0.2, 0.2, 0.2, 0.1, 0.2, 0.1],
        ]
    )
    predictions = apply_confidence_threshold(model, probabilities, 0.5)
    assert predictions.tolist() == ["transfer_payment", "general_support"]


@pytest.mark.parametrize("threshold", [-0.1, 1.1])
def test_invalid_confidence_threshold_rejected(threshold: float) -> None:
    model = MultinomialNB()
    model.classes_ = np.asarray(LABELS, dtype=object)
    with pytest.raises(ValueError, match="threshold"):
        apply_confidence_threshold(model, np.full((1, 6), 1 / 6), threshold)


def test_threshold_selection_uses_fixed_candidates_and_macro_f1() -> None:
    model = MultinomialNB()
    model.classes_ = np.asarray(LABELS, dtype=object)
    probabilities = np.eye(6) * 0.8 + np.full((6, 6), 0.2 / 6)
    threshold, metrics, results = select_threshold(model, probabilities, list(LABELS))
    assert threshold in THRESHOLDS
    assert metrics["macro"]["f1"] == 1.0
    assert [item["threshold"] for item in results] == list(THRESHOLDS)


def test_finalization_is_validation_selected_and_tested_once(tmp_path: Path) -> None:
    config = write_inputs(tmp_path, synthetic_rows())
    metrics = finalize_model(config)
    assert metrics["status"] == "completed"
    assert metrics["model_version"] == "v1"
    assert len(metrics["candidate_validation_results"]) == len(CANDIDATES)
    assert metrics["selection_policy"]["selection_metric"] == "validation macro-F1"
    assert metrics["selection_policy"]["test_used_for_selection"] is False
    assert metrics["selection_policy"]["test_evaluations"] == 1
    assert metrics["selected_candidate"]["confidence_threshold"] in THRESHOLDS


def test_final_metrics_reconcile_in_fixed_label_order(tmp_path: Path) -> None:
    metrics = finalize_model(write_inputs(tmp_path, synthetic_rows()))
    test_rows = metrics["data_partitions"]["test"]["rows"]
    test_metrics = metrics["final_test_metrics"]
    assert test_metrics["confusion_matrix"]["label_order"] == list(LABELS)
    assert (
        sum(sum(row) for row in test_metrics["confusion_matrix"]["values"]) == test_rows
    )
    assert sum(test_metrics["true_label_counts"].values()) == test_rows
    assert sum(test_metrics["predicted_label_counts"].values()) == test_rows
    assert (
        sum(item["support"] for item in test_metrics["per_class"].values()) == test_rows
    )


def test_final_artifact_round_trip_contains_inference_contract(tmp_path: Path) -> None:
    config = write_inputs(tmp_path, synthetic_rows())
    finalize_model(config)
    artifact = joblib.load(config.model_path)
    assert artifact["model_version"] == "v1"
    assert artifact["labels"] == LABELS
    assert artifact["fallback_label"] == "general_support"
    matrix = artifact["vectorizer"].transform(
        [normalize_text("Fictional account support request")]
    )
    probabilities = artifact["classifier"].predict_proba(matrix)
    prediction = apply_confidence_threshold(
        artifact["classifier"], probabilities, artifact["confidence_threshold"]
    )
    assert len(prediction) == 1
    assert prediction[0] in LABELS


def test_metrics_are_aggregate_only(tmp_path: Path) -> None:
    config = write_inputs(tmp_path, synthetic_rows())
    finalize_model(config)
    serialized = config.metrics_path.read_text(encoding="utf-8").lower()
    assert "fictional transfer payment help" not in serialized
    assert "sequence 119" not in serialized
    assert "complaint id" not in serialized
    assert "row_predictions" in serialized
    assert '"contains_row_predictions": false' in serialized


def test_overwrite_protection_preserves_existing_metrics(tmp_path: Path) -> None:
    config = write_inputs(tmp_path, synthetic_rows())
    config.metrics_path.write_text("preserve", encoding="utf-8")
    with pytest.raises(FileExistsError):
        finalize_model(config)
    assert config.metrics_path.read_text(encoding="utf-8") == "preserve"
    assert not config.model_path.exists()


def test_baseline_version_mismatch_stops_before_publication(tmp_path: Path) -> None:
    config = write_inputs(tmp_path, synthetic_rows())
    baseline = json.loads(config.baseline_metrics_path.read_text(encoding="utf-8"))
    baseline["dataset_version"] = "unexpected"
    config.baseline_metrics_path.write_text(json.dumps(baseline), encoding="utf-8")
    with pytest.raises(FinalizationError, match="dataset version"):
        finalize_model(config)
    assert not config.metrics_path.exists()
    assert not config.model_path.exists()


def test_repeated_runs_select_same_candidate_and_threshold(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    first = finalize_model(write_inputs(first_root, synthetic_rows()))
    second = finalize_model(write_inputs(second_root, synthetic_rows()))
    assert (
        first["selected_candidate"]["candidate"]
        == second["selected_candidate"]["candidate"]
    )
    assert (
        first["selected_candidate"]["confidence_threshold"]
        == second["selected_candidate"]["confidence_threshold"]
    )
    assert first["final_test_metrics"] == second["final_test_metrics"]
