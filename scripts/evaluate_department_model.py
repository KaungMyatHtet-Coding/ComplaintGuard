"""Reproduce Day 18 held-out evaluation for the immutable model-v1 artifact."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import sklearn

if __package__:
    from scripts.train_department_baseline import (
        LABELS,
        BaselineConfig,
        _counts,
        _evaluate,
        _load_input_manifest,
        _select_rows,
        split_selected_rows,
    )
else:
    from train_department_baseline import (  # type: ignore[no-redef]
        LABELS,
        BaselineConfig,
        _counts,
        _evaluate,
        _load_input_manifest,
        _select_rows,
        split_selected_rows,
    )

SCHEMA_VERSION = 1
MODEL_VERSION = "v1"
DATASET_VERSION = "v1"
MAPPING_VERSION = "v1"
OPERATIONAL_THRESHOLD = 0.60
CONFIDENCE_BINS = (0.0, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)
EXAMPLES_PER_OUTCOME = 12


class EvaluationError(RuntimeError):
    """Raised when frozen evaluation evidence cannot be reproduced safely."""


@dataclass(frozen=True)
class EvaluationConfig:
    input_path: Path
    input_manifest_path: Path
    model_path: Path
    locked_metrics_path: Path
    snapshot_profile_path: Path
    cleaning_report_path: Path
    output_dir: Path
    similarity_index_path: Path | None = None
    chunk_size: int = 100_000
    max_rows: int = 200_000
    seed: int = 20260727


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def confidence_analysis(
    true_labels: list[str],
    predictions: np.ndarray[Any, Any],
    confidences: np.ndarray[Any, Any],
) -> dict[str, Any]:
    """Summarize uncalibrated maximum class probabilities without calling them accuracy."""
    if not (len(true_labels) == len(predictions) == len(confidences)):
        raise ValueError("confidence inputs must have equal length")
    if not len(true_labels):
        raise ValueError("confidence analysis requires records")
    if not np.isfinite(confidences).all() or np.any(
        (confidences < 0) | (confidences > 1)
    ):
        raise ValueError("confidence values must be finite and between zero and one")
    correct = np.asarray(true_labels, dtype=object) == predictions
    bins: list[dict[str, Any]] = []
    for index, lower in enumerate(CONFIDENCE_BINS[:-1]):
        upper = CONFIDENCE_BINS[index + 1]
        mask = (confidences >= lower) & (
            confidences <= upper if upper == 1.0 else confidences < upper
        )
        count = int(mask.sum())
        bins.append(
            {
                "lower_inclusive": lower,
                "upper": upper,
                "upper_inclusive": upper == 1.0,
                "count": count,
                "percentage": count / len(confidences),
                "correct": int(correct[mask].sum()),
                "incorrect": int(count - correct[mask].sum()),
                "empirical_accuracy": float(correct[mask].mean()) if count else None,
            }
        )
    below = confidences < OPERATIONAL_THRESHOLD
    return {
        "definition": "maximum MultinomialNB class probability; not calibrated reliability",
        "operational_analysis_threshold": OPERATIONAL_THRESHOLD,
        "threshold_origin": "Day 17 routing policy; not selected by held-out test performance",
        "minimum": float(confidences.min()),
        "median": float(np.median(confidences)),
        "mean": float(confidences.mean()),
        "maximum": float(confidences.max()),
        "below_operational_threshold": {
            "count": int(below.sum()),
            "percentage": float(below.mean()),
            "correct": int(correct[below].sum()),
            "incorrect": int((~correct[below]).sum()),
        },
        "at_or_above_operational_threshold": {
            "count": int((~below).sum()),
            "percentage": float((~below).mean()),
            "correct": int(correct[~below].sum()),
            "incorrect": int((~correct[~below]).sum()),
        },
        "bins": bins,
    }


def example_metadata(
    rows: list[tuple[str, str]],
    predictions: np.ndarray[Any, Any],
    confidences: np.ndarray[Any, Any],
) -> dict[str, list[dict[str, Any]]]:
    """Return deterministic, non-narrative examples from the held-out test set."""
    values: dict[str, list[dict[str, Any]]] = {"correct": [], "misclassified": []}
    candidates: dict[str, list[tuple[bytes, dict[str, Any]]]] = {
        "correct": [],
        "misclassified": [],
    }
    for (text, true_label), predicted, confidence in zip(
        rows, predictions.tolist(), confidences.tolist(), strict=True
    ):
        digest = hashlib.sha256(f"day18-example\0{text}".encode()).digest()
        outcome = "correct" if true_label == predicted else "misclassified"
        candidates[outcome].append(
            (
                digest,
                {
                    "example_id": digest.hex()[:16],
                    "true_department": true_label,
                    "predicted_department": predicted,
                    "confidence": float(confidence),
                    "normalized_character_count": len(text),
                    "contains_narrative": False,
                },
            )
        )
    for outcome, items in candidates.items():
        values[outcome] = [
            item
            for _, item in sorted(items, key=lambda candidate: candidate[0])[
                :EXAMPLES_PER_OUTCOME
            ]
        ]
    return values


def validate_public_artifact(artifact: dict[str, Any]) -> None:
    """Validate stable public schema and key reconciliation constraints."""
    required = {
        "schema_version",
        "status",
        "metadata",
        "dataset_pipeline",
        "partitions",
        "class_distribution",
        "metrics",
        "confidence_analysis",
        "examples",
        "historical_similarity",
        "privacy",
        "limitations",
    }
    if set(artifact) != required:
        raise EvaluationError("evaluation artifact top-level schema is invalid")
    if (
        artifact["schema_version"] != SCHEMA_VERSION
        or artifact["status"] != "completed"
    ):
        raise EvaluationError("evaluation artifact status or version is invalid")
    test_rows = artifact["partitions"]["test"]["rows"]
    metrics = artifact["metrics"]
    if sum(item["support"] for item in metrics["per_department"].values()) != test_rows:
        raise EvaluationError("per-department supports do not reconcile")
    if sum(sum(row) for row in metrics["confusion_matrix"]["values"]) != test_rows:
        raise EvaluationError("confusion matrix does not reconcile")
    if (
        sum(item["count"] for item in artifact["confidence_analysis"]["bins"])
        != test_rows
    ):
        raise EvaluationError("confidence bins do not reconcile")
    if artifact["privacy"]["contains_narratives"]:
        raise EvaluationError("public evaluation artifact must not contain narratives")


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise EvaluationError(f"{path.name} must contain a JSON object")
    return value


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _write_csvs(output_dir: Path, artifact: dict[str, Any]) -> None:
    with (output_dir / "per_department_metrics.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow(("department_id", "precision", "recall", "f1", "support"))
        for label in LABELS:
            item = artifact["metrics"]["per_department"][label]
            writer.writerow(
                (label, item["precision"], item["recall"], item["f1"], item["support"])
            )
    with (output_dir / "confusion_matrix.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow(("true_department", *LABELS))
        for label, row in zip(
            LABELS, artifact["metrics"]["confusion_matrix"]["values"], strict=True
        ):
            writer.writerow((label, *row))


def run_evaluation(config: EvaluationConfig) -> dict[str, Any]:
    """Evaluate only the reconstructed held-out test set with the frozen artifact."""
    if config.output_dir.exists():
        raise FileExistsError("refusing to overwrite an existing evaluation directory")
    locked = _load_json(config.locked_metrics_path)
    expected_model = locked.get("generated_model", {})
    if sha256_file(config.model_path) != expected_model.get("sha256"):
        raise EvaluationError("frozen model checksum differs from locked Day 9 metrics")
    artifact = joblib.load(config.model_path)
    if not isinstance(artifact, dict):
        raise EvaluationError("model artifact is not a dictionary")
    for key, expected in (
        ("model_version", MODEL_VERSION),
        ("dataset_version", DATASET_VERSION),
        ("mapping_version", MAPPING_VERSION),
    ):
        if artifact.get(key) != expected:
            raise EvaluationError(f"model {key} is incompatible")
    if tuple(artifact.get("labels", ())) != LABELS:
        raise EvaluationError("model labels are incompatible")

    selection_config = BaselineConfig(
        input_path=config.input_path,
        input_manifest_path=config.input_manifest_path,
        metrics_path=config.output_dir / "unused-metrics.json",
        model_path=config.output_dir / "unused-model.joblib",
        chunk_size=config.chunk_size,
        max_rows=config.max_rows,
        seed=config.seed,
    )
    manifest = _load_input_manifest(selection_config)
    started = time.perf_counter()
    selected, source_counts, chunks = _select_rows(
        selection_config, manifest["output"]["rows"]
    )
    partitions = split_selected_rows(selected, selection_config)
    test_rows = partitions["test"]
    test_text = [text for text, _ in test_rows]
    test_labels = [label for _, label in test_rows]
    matrix = artifact["vectorizer"].transform(test_text)
    probabilities = np.asarray(artifact["classifier"].predict_proba(matrix))
    indices = np.argmax(probabilities, axis=1)
    predictions = np.asarray(artifact["classifier"].classes_, dtype=object)[indices]
    confidences = probabilities[np.arange(len(probabilities)), indices]
    evaluated = _evaluate(test_labels, predictions)
    locked_test = locked.get("final_test_metrics")
    if evaluated != locked_test:
        raise EvaluationError(
            "reproduced held-out metrics differ from locked Day 9 evidence"
        )

    profile = _load_json(config.snapshot_profile_path)
    cleaning = _load_json(config.cleaning_report_path)
    raw_rows = profile["csv"]["row_count"]
    raw_non_null = (
        raw_rows - profile["csv"]["missing"]["Consumer complaint narrative"]["count"]
    )
    usable = cleaning["counts"]["retained_rows"]
    similarity = {
        "status": "not_built",
        "method": "cosine similarity over frozen model-v1 TF-IDF vectors",
        "reference_partition": "held-out test",
        "reference_records": len(test_rows),
        "covers_all_raw_records": False,
        "separate_from_prediction_confidence": True,
        "contains_narratives": False,
    }
    if config.similarity_index_path is not None:
        config.similarity_index_path.parent.mkdir(parents=True, exist_ok=True)
        if config.similarity_index_path.exists():
            raise FileExistsError("refusing to overwrite similarity index")
        example_ids = [
            hashlib.sha256(f"day18-example\0{text}".encode()).hexdigest()[:16]
            for text in test_text
        ]
        joblib.dump(
            {
                "schema_version": 1,
                "method": "cosine_similarity_on_l2_normalized_tfidf",
                "model_version": MODEL_VERSION,
                "dataset_version": DATASET_VERSION,
                "mapping_version": MAPPING_VERSION,
                "reference_partition": "held-out_test",
                "matrix": matrix,
                "labels": tuple(test_labels),
                "example_ids": tuple(example_ids),
                "contains_narratives": False,
            },
            config.similarity_index_path,
            compress=3,
        )
        similarity.update(
            {
                "status": "built_local_ignored_index",
                "index_file_name": config.similarity_index_path.name,
                "index_size_bytes": config.similarity_index_path.stat().st_size,
                "index_sha256": sha256_file(config.similarity_index_path),
                "feature_count": int(matrix.shape[1]),
            }
        )

    result = {
        "schema_version": SCHEMA_VERSION,
        "status": "completed",
        "metadata": {
            "created_at_utc": datetime.now(UTC).isoformat(),
            "model_version": MODEL_VERSION,
            "dataset_version": DATASET_VERSION,
            "mapping_version": MAPPING_VERSION,
            "model_sha256": expected_model["sha256"],
            "random_seed": config.seed,
            "evaluation_partition": "held-out test",
            "model_retrained": False,
            "locked_metrics_reconciled": True,
            "python": platform.python_version(),
            "pandas": pd.__version__,
            "numpy": np.__version__,
            "scikit_learn": sklearn.__version__,
            "joblib": joblib.__version__,
            "runtime_seconds": time.perf_counter() - started,
        },
        "dataset_pipeline": {
            "raw_records": raw_rows,
            "raw_records_with_non_null_narrative": raw_non_null,
            "usable_narrative_records": usable,
            "successfully_mapped_records": manifest["output"]["rows"],
            "selected_modeling_records": len(selected),
            "filters": cleaning["rejection_reasons"],
            "mapped_label_counts": {label: source_counts[label] for label in LABELS},
        },
        "partitions": {
            "natural_training": {
                "rows": len(partitions["train"]),
                "label_counts": _counts(partitions["train"]),
            },
            "training_used_for_fit": locked["data_partitions"]["final_training"],
            "validation": {
                "rows": len(partitions["validation"]),
                "label_counts": _counts(partitions["validation"]),
            },
            "test": {"rows": len(test_rows), "label_counts": _counts(test_rows)},
            "chunks_processed": chunks,
            "split_method": "SHA-256 assignment by seed and exact normalized narrative",
            "exact_normalized_duplicates_cross_partitions": False,
        },
        "class_distribution": {
            "mapped_corpus": {label: source_counts[label] for label in LABELS},
            "held_out_test_true": evaluated["true_label_counts"],
            "held_out_test_predicted": evaluated["predicted_label_counts"],
        },
        "metrics": {
            "accuracy": evaluated["accuracy"],
            "balanced_accuracy": evaluated["balanced_accuracy"],
            "macro": evaluated["macro"],
            "weighted": evaluated["weighted"],
            "per_department": evaluated["per_class"],
            "confusion_matrix": evaluated["confusion_matrix"],
        },
        "confidence_analysis": confidence_analysis(
            test_labels, predictions, confidences
        ),
        "examples": example_metadata(test_rows, predictions, confidences),
        "historical_similarity": similarity,
        "privacy": {
            "aggregate_outputs": True,
            "contains_narratives": False,
            "contains_complaint_ids": False,
            "example_records_are_non_text_metadata": True,
        },
        "limitations": [
            "Labels are Product/Issue policy proxies rather than verified institutional ground truth.",
            "The 200,000-record reservoir is a bounded sample of the mapped corpus.",
            "The source and held-out test distributions are strongly imbalanced.",
            "Exact normalized duplicates are grouped, but near-duplicates are not detected.",
            "MultinomialNB maximum probabilities are not calibrated reliability estimates.",
            "Real CFPB narratives are omitted from public examples because PII reduction is not anonymization.",
            "Historical similarity covers only the explicitly recorded local reference partition.",
        ],
    }
    validate_public_artifact(result)
    config.output_dir.mkdir(parents=True)
    _write_json(config.output_dir / "model_evaluation_v1.json", result)
    _write_json(
        config.output_dir / "dataset_pipeline_counts.json", result["dataset_pipeline"]
    )
    _write_json(
        config.output_dir / "confidence_analysis.json", result["confidence_analysis"]
    )
    _write_json(
        config.output_dir / "historical_similarity_metadata.json",
        result["historical_similarity"],
    )
    _write_csvs(config.output_dir, result)
    return result


def _parse_args() -> EvaluationConfig:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--input-manifest", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--locked-metrics", type=Path, required=True)
    parser.add_argument("--snapshot-profile", type=Path, required=True)
    parser.add_argument("--cleaning-report", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--similarity-index", type=Path)
    parser.add_argument("--chunk-size", type=int, default=100_000)
    parser.add_argument("--max-rows", type=int, default=200_000)
    parser.add_argument("--seed", type=int, default=20260727)
    args = parser.parse_args()
    return EvaluationConfig(
        input_path=args.input,
        input_manifest_path=args.input_manifest,
        model_path=args.model,
        locked_metrics_path=args.locked_metrics,
        snapshot_profile_path=args.snapshot_profile,
        cleaning_report_path=args.cleaning_report,
        output_dir=args.output_dir,
        similarity_index_path=args.similarity_index,
        chunk_size=args.chunk_size,
        max_rows=args.max_rows,
        seed=args.seed,
    )


def main() -> int:
    try:
        result = run_evaluation(_parse_args())
    except (EvaluationError, FileExistsError, ValueError, KeyError) as exc:
        print(f"evaluation failed: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "status": result["status"],
                "test_rows": result["partitions"]["test"]["rows"],
                "macro_f1": result["metrics"]["macro"]["f1"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
