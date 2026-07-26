from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import joblib
import pandas as pd
import pytest
from sklearn.feature_extraction.text import TfidfVectorizer

from scripts.train_department_baseline import (
    INPUT_COLUMNS,
    LABELS,
    BaselineConfig,
    BaselineError,
    _evaluate,
    balance_training_rows,
    normalize_text,
    run_baseline,
    split_selected_rows,
)


def synthetic_rows(per_label: int = 40) -> list[tuple[str, str]]:
    return [
        (
            f"Fictional service request {label.replace('_', ' ')} reference {index}",
            label,
        )
        for label in LABELS
        for index in range(per_label)
    ]


def write_input(
    root: Path,
    rows: list[tuple[str, str]],
    *,
    columns: tuple[str, ...] = INPUT_COLUMNS,
) -> tuple[Path, Path]:
    input_path = root / "synthetic_training.csv"
    frame = pd.DataFrame(rows, columns=list(INPUT_COLUMNS))
    if columns != INPUT_COLUMNS:
        frame = frame[list(columns)]
    frame.to_csv(input_path, index=False)
    raw_counts = Counter(label for _, label in rows)
    unknown_count = sum(
        count for label, count in raw_counts.items() if label not in LABELS
    )
    counts = {label: raw_counts[label] for label in LABELS}
    counts[LABELS[0]] += unknown_count
    manifest = {
        "status": "completed",
        "dataset_version": "v1",
        "mapping_version": "v1",
        "output": {
            "file_name": input_path.name,
            "schema": list(columns),
            "rows": len(frame),
        },
        "label_counts": counts,
    }
    manifest_path = root / "input_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return input_path, manifest_path


def config_for(
    root: Path, rows: list[tuple[str, str]] | None = None, **changes: object
) -> BaselineConfig:
    input_path, manifest_path = write_input(root, rows or synthetic_rows())
    values = {
        "input_path": input_path,
        "input_manifest_path": manifest_path,
        "metrics_path": root / "metrics.json",
        "model_path": root / "model.joblib",
        "chunk_size": 17,
        "max_rows": len(rows or synthetic_rows()),
        "train_per_class_cap": 20,
        "max_features": 500,
        "min_df": 1,
        "max_df": 1.0,
    }
    values.update(changes)
    return BaselineConfig(**values)


def test_normalization_is_conservative_and_deterministic() -> None:
    assert (
        normalize_text("  FICTIONAL\u3000Ａccount\nHelp  ") == "fictional account help"
    )
    assert normalize_text("Payment  remains due.") == normalize_text(
        "PAYMENT remains   due."
    )


def test_split_is_deterministic_and_duplicate_safe(tmp_path: Path) -> None:
    config = config_for(tmp_path)
    rows = synthetic_rows(200) + [
        ("Duplicate fictional request", "account_support"),
        ("  DUPLICATE   fictional request ", "account_support"),
    ]
    first = split_selected_rows(rows, config)
    second = split_selected_rows(rows, config)
    assert first == second
    locations = {
        name
        for name, values in first.items()
        if any(text == "duplicate fictional request" for text, _ in values)
    }
    assert len(locations) == 1


def test_training_only_balancing_is_deterministic(tmp_path: Path) -> None:
    config = config_for(tmp_path, train_per_class_cap=3)
    train = [
        (f"fictional {label} {index}", label) for label in LABELS for index in range(9)
    ]
    first = balance_training_rows(train, config)
    assert first == balance_training_rows(train, config)
    assert len(first) == 18
    assert {label: sum(item[1] == label for item in first) for label in LABELS} == {
        label: 3 for label in LABELS
    }


def test_balancing_does_not_mutate_held_out_partitions(tmp_path: Path) -> None:
    config = config_for(tmp_path, train_per_class_cap=2)
    partitions = split_selected_rows(synthetic_rows(200), config)
    validation_before = list(partitions["validation"])
    test_before = list(partitions["test"])
    balance_training_rows(partitions["train"], config)
    assert partitions["validation"] == validation_before
    assert partitions["test"] == test_before


def test_held_out_only_token_is_absent_from_training_vocabulary() -> None:
    vectorizer = TfidfVectorizer()
    vectorizer.fit(["fictional account support", "fictional payment transfer"])
    vectorizer.transform(["heldoutuniquetoken fictional request"])
    assert "heldoutuniquetoken" not in vectorizer.vocabulary_


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"max_rows": 5}, "max_rows"),
        ({"chunk_size": 0}, "chunk_size"),
        ({"alpha": 0.0}, "alpha"),
        ({"train_ratio": 0.8}, "split ratios"),
    ],
)
def test_invalid_configuration_rejected(
    tmp_path: Path, change: dict[str, object], message: str
) -> None:
    config = config_for(tmp_path, **change)
    with pytest.raises(ValueError, match=message):
        run_baseline(config)


def test_missing_column_rejected(tmp_path: Path) -> None:
    input_path, manifest_path = write_input(
        tmp_path, synthetic_rows(), columns=(INPUT_COLUMNS[0],)
    )
    config = BaselineConfig(
        input_path=input_path,
        input_manifest_path=manifest_path,
        metrics_path=tmp_path / "metrics.json",
        model_path=tmp_path / "model.joblib",
        max_rows=100,
        min_df=1,
    )
    with pytest.raises(BaselineError, match="schema"):
        run_baseline(config)


@pytest.mark.parametrize(
    "bad_value",
    [None, "", "   "],
)
def test_null_or_empty_narrative_rejected(
    tmp_path: Path, bad_value: str | None
) -> None:
    rows = synthetic_rows()
    rows[0] = (bad_value, rows[0][1])  # type: ignore[list-item]
    config = config_for(tmp_path, rows)
    with pytest.raises(BaselineError, match="narrative"):
        run_baseline(config)
    assert not config.metrics_path.exists()
    assert not config.model_path.exists()


def test_invalid_label_rejected_without_publication(tmp_path: Path) -> None:
    rows = synthetic_rows()
    rows[0] = (rows[0][0], "fictional_unknown")
    config = config_for(tmp_path, rows)
    with pytest.raises(BaselineError, match="allowlist"):
        run_baseline(config)
    assert not config.metrics_path.exists()
    assert not config.model_path.exists()


def test_end_to_end_is_aggregate_only_and_reconciles(tmp_path: Path) -> None:
    config = config_for(tmp_path, synthetic_rows(200))
    metrics = run_baseline(config)
    assert metrics["status"] == "completed"
    assert metrics["dataset_version"] == "v1"
    assert metrics["mapping_version"] == "v1"
    assert set(metrics["source"]["label_counts"]) == set(LABELS)
    assert set(metrics["test_metrics"]["predicted_label_counts"]) == set(LABELS)
    test_rows = metrics["partitions"]["test"]["rows"]
    assert sum(metrics["test_metrics"]["true_label_counts"].values()) == test_rows
    assert (
        sum(sum(row) for row in metrics["test_metrics"]["confusion_matrix"]["values"])
        == test_rows
    )
    serialized = config.metrics_path.read_text(encoding="utf-8").lower()
    for forbidden in (
        "fictional service request",
        "heldoutuniquetoken",
        "complaint id",
    ):
        assert forbidden not in serialized


def test_model_round_trip_predicts_one_allowed_label_per_row(tmp_path: Path) -> None:
    config = config_for(tmp_path, synthetic_rows(200))
    run_baseline(config)
    artifact = joblib.load(config.model_path)
    matrix = artifact["vectorizer"].transform(
        [normalize_text("Fictional card assistance request")]
    )
    predictions = artifact["model"].predict(matrix)
    assert len(predictions) == 1
    assert predictions[0] in LABELS


def test_overwrite_protection(tmp_path: Path) -> None:
    config = config_for(tmp_path)
    config.metrics_path.write_text("preserve", encoding="utf-8")
    with pytest.raises(FileExistsError):
        run_baseline(config)
    assert config.metrics_path.read_text(encoding="utf-8") == "preserve"
    assert not config.model_path.exists()


def test_metrics_use_fixed_confusion_order() -> None:
    result = _evaluate(list(LABELS), pd.Series(list(reversed(LABELS))).to_numpy())
    assert result["confusion_matrix"]["label_order"] == list(LABELS)
    assert sum(item["support"] for item in result["per_class"].values()) == 6


def test_chunk_boundaries_do_not_change_source_reconciliation(tmp_path: Path) -> None:
    rows = synthetic_rows(100)
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    first = run_baseline(config_for(first_root, rows, chunk_size=7))
    second = run_baseline(config_for(second_root, rows, chunk_size=113))
    assert first["source"]["label_counts"] == second["source"]["label_counts"]
    assert (
        first["selection"]["selected_label_counts"]
        == second["selection"]["selected_label_counts"]
    )
