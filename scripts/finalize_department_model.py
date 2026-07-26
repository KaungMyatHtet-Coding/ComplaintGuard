"""Day 9 validation-only model selection and frozen department model v1."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB

if __package__:
    from scripts.train_department_baseline import (
        DATASET_VERSION,
        LABELS,
        MAPPING_VERSION,
        BaselineConfig,
        BaselineError,
        _counts,
        _evaluate,
        _load_input_manifest,
        _matrix_summary,
        _select_rows,
        balance_training_rows,
        split_selected_rows,
    )
else:
    from train_department_baseline import (  # type: ignore[no-redef]
        DATASET_VERSION,
        LABELS,
        MAPPING_VERSION,
        BaselineConfig,
        BaselineError,
        _counts,
        _evaluate,
        _load_input_manifest,
        _matrix_summary,
        _select_rows,
        balance_training_rows,
        split_selected_rows,
    )

FINAL_MODEL_VERSION = "v1"
FINAL_METRICS_SCHEMA_VERSION = 1
THRESHOLDS = (0.0, 0.35, 0.45, 0.55, 0.65)


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    ngram_range: tuple[int, int]
    min_df: int
    max_features: int
    alpha: float
    train_per_class_cap: int | None


CANDIDATES = (
    Candidate("baseline_reference", (1, 2), 3, 100_000, 1.0, 30_000),
    Candidate("lower_alpha", (1, 2), 3, 100_000, 0.5, 30_000),
    Candidate("unigram_lower_alpha", (1, 1), 3, 100_000, 0.5, 30_000),
    Candidate("stronger_balance", (1, 2), 3, 100_000, 0.5, 20_000),
)


class FinalizationError(RuntimeError):
    """Raised when the final model cannot be selected or published safely."""


@dataclass(frozen=True)
class FinalizationConfig:
    input_path: Path
    input_manifest_path: Path
    baseline_metrics_path: Path
    metrics_path: Path
    model_path: Path
    chunk_size: int = 100_000
    max_rows: int = 200_000
    seed: int = 20260727
    train_ratio: float = 0.70
    validation_ratio: float = 0.15
    test_ratio: float = 0.15
    max_df: float = 0.98


def _validate_config(config: FinalizationConfig) -> dict[str, Any]:
    if config.metrics_path.exists() or config.model_path.exists():
        raise FileExistsError("refusing to overwrite final model or metrics")
    if config.metrics_path.resolve() == config.model_path.resolve():
        raise ValueError("model and metrics destinations must differ")
    baseline = json.loads(config.baseline_metrics_path.read_text(encoding="utf-8"))
    if baseline.get("status") != "completed":
        raise FinalizationError("Day 8 baseline metrics are not completed")
    if baseline.get("dataset_version") != DATASET_VERSION:
        raise FinalizationError("Day 8 dataset version differs")
    if baseline.get("mapping_version") != MAPPING_VERSION:
        raise FinalizationError("Day 8 mapping version differs")
    if baseline.get("configuration", {}).get("seed") != config.seed:
        raise FinalizationError("Day 8 seed differs from the frozen Day 9 seed")
    if baseline.get("selection", {}).get("selected_rows") != config.max_rows:
        raise FinalizationError("Day 8 selected-row boundary differs")
    return baseline


def apply_confidence_threshold(
    model: MultinomialNB,
    probabilities: np.ndarray[Any, Any],
    threshold: float,
) -> np.ndarray[Any, Any]:
    """Return one allowed label, routing low confidence to general_support."""
    if not 0 <= threshold <= 1:
        raise ValueError("confidence threshold must be between zero and one")
    class_labels = np.asarray(model.classes_, dtype=object)
    predictions = class_labels[np.argmax(probabilities, axis=1)]
    predictions = predictions.astype(object, copy=True)
    predictions[np.max(probabilities, axis=1) < threshold] = "general_support"
    if set(predictions.tolist()) - set(LABELS):
        raise FinalizationError("threshold routing emitted an invalid label")
    return predictions


def select_threshold(
    model: MultinomialNB,
    probabilities: np.ndarray[Any, Any],
    true_labels: list[str],
) -> tuple[float, dict[str, Any], list[dict[str, Any]]]:
    """Choose a fixed threshold using validation macro-F1 only."""
    results: list[dict[str, Any]] = []
    best: tuple[float, dict[str, Any]] | None = None
    for threshold in THRESHOLDS:
        predictions = apply_confidence_threshold(model, probabilities, threshold)
        metrics = _evaluate(true_labels, predictions)
        results.append(
            {
                "threshold": threshold,
                "accuracy": metrics["accuracy"],
                "balanced_accuracy": metrics["balanced_accuracy"],
                "macro_f1": metrics["macro"]["f1"],
                "manual_review_routed": int(
                    np.sum(np.max(probabilities, axis=1) < threshold)
                ),
            }
        )
        score = metrics["macro"]["f1"]
        if best is None or score > best[1]["macro"]["f1"]:
            best = (threshold, metrics)
    if best is None:
        raise FinalizationError("no confidence threshold was evaluated")
    return best[0], best[1], results


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _candidate_vectorizer(candidate: Candidate, max_df: float) -> TfidfVectorizer:
    return TfidfVectorizer(
        lowercase=False,
        analyzer="word",
        ngram_range=candidate.ngram_range,
        min_df=candidate.min_df,
        max_df=max_df,
        max_features=candidate.max_features,
        sublinear_tf=True,
        dtype=np.float32,
    )


def finalize_model(config: FinalizationConfig) -> dict[str, Any]:
    """Select by validation only, test once, and atomically publish model v1."""
    started = time.perf_counter()
    baseline = _validate_config(config)
    input_manifest = _load_input_manifest(
        BaselineConfig(
            input_path=config.input_path,
            input_manifest_path=config.input_manifest_path,
            metrics_path=config.metrics_path,
            model_path=config.model_path,
            chunk_size=config.chunk_size,
            max_rows=config.max_rows,
            seed=config.seed,
            train_ratio=config.train_ratio,
            validation_ratio=config.validation_ratio,
            test_ratio=config.test_ratio,
        )
    )
    selection_config = BaselineConfig(
        input_path=config.input_path,
        input_manifest_path=config.input_manifest_path,
        metrics_path=config.metrics_path,
        model_path=config.model_path,
        chunk_size=config.chunk_size,
        max_rows=config.max_rows,
        seed=config.seed,
        train_ratio=config.train_ratio,
        validation_ratio=config.validation_ratio,
        test_ratio=config.test_ratio,
    )
    selected_rows, source_counts, chunks = _select_rows(
        selection_config, input_manifest["output"]["rows"]
    )
    partitions = split_selected_rows(selected_rows, selection_config)
    natural_train = partitions["train"]
    validation_rows = partitions["validation"]
    test_rows = partitions["test"]
    validation_text = [text for text, _ in validation_rows]
    validation_labels = [label for _, label in validation_rows]
    test_text = [text for text, _ in test_rows]
    test_labels = [label for _, label in test_rows]

    candidate_results: list[dict[str, Any]] = []
    best_score = -1.0
    best_bundle: (
        tuple[
            Candidate,
            TfidfVectorizer,
            MultinomialNB,
            list[tuple[str, str]],
            float,
            dict[str, Any],
        ]
        | None
    ) = None
    selection_started = time.perf_counter()
    for candidate in CANDIDATES:
        candidate_config = BaselineConfig(
            input_path=config.input_path,
            input_manifest_path=config.input_manifest_path,
            metrics_path=config.metrics_path,
            model_path=config.model_path,
            chunk_size=config.chunk_size,
            max_rows=config.max_rows,
            train_per_class_cap=candidate.train_per_class_cap,
            seed=config.seed,
            train_ratio=config.train_ratio,
            validation_ratio=config.validation_ratio,
            test_ratio=config.test_ratio,
            max_features=candidate.max_features,
            min_df=candidate.min_df,
            max_df=config.max_df,
            alpha=candidate.alpha,
        )
        training_rows = balance_training_rows(natural_train, candidate_config)
        vectorizer = _candidate_vectorizer(candidate, config.max_df)
        training_matrix = vectorizer.fit_transform([text for text, _ in training_rows])
        validation_matrix = vectorizer.transform(validation_text)
        model = MultinomialNB(alpha=candidate.alpha)
        model.fit(training_matrix, [label for _, label in training_rows])
        validation_probabilities = model.predict_proba(validation_matrix)
        threshold, validation_metrics, threshold_results = select_threshold(
            model, validation_probabilities, validation_labels
        )
        result = {
            "candidate": asdict(candidate),
            "training_rows": len(training_rows),
            "training_label_counts": _counts(training_rows),
            "vocabulary_size": len(vectorizer.vocabulary_),
            "train_matrix": _matrix_summary(training_matrix),
            "validation_matrix": _matrix_summary(validation_matrix),
            "selected_threshold": threshold,
            "threshold_search": threshold_results,
            "validation_metrics": validation_metrics,
        }
        candidate_results.append(result)
        score = validation_metrics["macro"]["f1"]
        if score > best_score:
            best_score = score
            best_bundle = (
                candidate,
                vectorizer,
                model,
                training_rows,
                threshold,
                result,
            )
    selection_finished = time.perf_counter()
    if best_bundle is None:
        raise FinalizationError("no candidate model was selected")
    candidate, vectorizer, model, training_rows, threshold, selected_result = (
        best_bundle
    )

    test_transform_started = time.perf_counter()
    test_matrix = vectorizer.transform(test_text)
    test_transform_finished = time.perf_counter()
    test_prediction_started = test_transform_finished
    test_probabilities = model.predict_proba(test_matrix)
    test_predictions = apply_confidence_threshold(model, test_probabilities, threshold)
    test_prediction_finished = time.perf_counter()
    test_metrics = _evaluate(test_labels, test_predictions)
    if sum(test_metrics["true_label_counts"].values()) != len(test_rows):
        raise FinalizationError("true-label test counts do not reconcile")
    if sum(test_metrics["predicted_label_counts"].values()) != len(test_rows):
        raise FinalizationError("predicted-label test counts do not reconcile")
    if sum(sum(row) for row in test_metrics["confusion_matrix"]["values"]) != len(
        test_rows
    ):
        raise FinalizationError("test confusion matrix does not reconcile")

    metrics: dict[str, Any] = {
        "metrics_schema_version": FINAL_METRICS_SCHEMA_VERSION,
        "status": "completed",
        "model_version": FINAL_MODEL_VERSION,
        "dataset_version": DATASET_VERSION,
        "mapping_version": MAPPING_VERSION,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "source": {
            "file_name": config.input_path.name,
            "manifest_file_name": config.input_manifest_path.name,
            "rows": input_manifest["output"]["rows"],
            "label_counts": {label: source_counts[label] for label in LABELS},
            "chunks_processed": chunks,
        },
        "locked_day8_baseline": {
            "metrics_file_name": config.baseline_metrics_path.name,
            "test_accuracy": baseline["test_metrics"]["accuracy"],
            "test_balanced_accuracy": baseline["test_metrics"]["balanced_accuracy"],
            "test_macro_f1": baseline["test_metrics"]["macro"]["f1"],
        },
        "selection_policy": {
            "selection_metric": "validation macro-F1",
            "candidate_order_tiebreak": True,
            "threshold_candidates": list(THRESHOLDS),
            "test_used_for_selection": False,
            "test_evaluations": 1,
        },
        "data_partitions": {
            "selected_rows": len(selected_rows),
            "selected_label_counts": _counts(selected_rows),
            "natural_train": {
                "rows": len(natural_train),
                "label_counts": _counts(natural_train),
            },
            "final_training": {
                "rows": len(training_rows),
                "label_counts": _counts(training_rows),
            },
            "validation": {
                "rows": len(validation_rows),
                "label_counts": _counts(validation_rows),
            },
            "test": {
                "rows": len(test_rows),
                "label_counts": _counts(test_rows),
            },
        },
        "candidate_validation_results": candidate_results,
        "selected_candidate": {
            **selected_result,
            "confidence_threshold": threshold,
        },
        "final_test_features": _matrix_summary(test_matrix),
        "final_test_metrics": test_metrics,
        "comparison": {
            "day8_test_macro_f1": baseline["test_metrics"]["macro"]["f1"],
            "day9_test_macro_f1": test_metrics["macro"]["f1"],
            "absolute_macro_f1_change": (
                test_metrics["macro"]["f1"] - baseline["test_metrics"]["macro"]["f1"]
            ),
            "target_macro_f1": 0.70,
            "target_achieved": test_metrics["macro"]["f1"] >= 0.70,
        },
        "timings_seconds": {
            "candidate_selection": selection_finished - selection_started,
            "final_test_transform": test_transform_finished - test_transform_started,
            "final_test_prediction": test_prediction_finished - test_prediction_started,
            "total": test_prediction_finished - started,
        },
        "environment": {
            "python": platform.python_version(),
            "pandas": pd.__version__,
            "numpy": np.__version__,
            "scikit_learn": sklearn.__version__,
            "joblib": joblib.__version__,
        },
        "privacy": {
            "aggregate_only_metrics": True,
            "contains_narratives": False,
            "contains_vocabulary": False,
            "contains_row_predictions": False,
            "contains_complaint_ids": False,
            "contains_private_absolute_paths": False,
        },
        "limitations": [
            "Labels are deterministic Product/Issue policy proxies, not institutional ground truth.",
            "Candidate selection uses one fixed, predeclared search rather than exhaustive tuning.",
            "Training-only undersampling changes learned class priors.",
            "Exact normalized duplicates are grouped; near-duplicates are not detected.",
            "Low-confidence routing uses general_support as the manual-review-compatible fallback.",
        ],
    }

    config.model_path.parent.mkdir(parents=True, exist_ok=True)
    config.metrics_path.parent.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    model_temp = config.model_path.with_name(f".{config.model_path.name}.{token}.tmp")
    metrics_temp = config.metrics_path.with_name(
        f".{config.metrics_path.name}.{token}.tmp"
    )
    published_model = False
    try:
        joblib.dump(
            {
                "model_version": FINAL_MODEL_VERSION,
                "dataset_version": DATASET_VERSION,
                "mapping_version": MAPPING_VERSION,
                "vectorizer": vectorizer,
                "classifier": model,
                "labels": LABELS,
                "confidence_threshold": threshold,
                "fallback_label": "general_support",
                "normalization": "NFKC + casefold + whitespace collapse",
                "candidate": asdict(candidate),
            },
            model_temp,
        )
        metrics["generated_model"] = {
            "file_name": config.model_path.name,
            "size_bytes": model_temp.stat().st_size,
            "sha256": _sha256(model_temp),
        }
        metrics_temp.write_text(
            json.dumps(metrics, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        os.replace(model_temp, config.model_path)
        published_model = True
        os.replace(metrics_temp, config.metrics_path)
    except Exception:
        for path in (model_temp, metrics_temp):
            if path.exists():
                path.unlink()
        if published_model and config.model_path.exists():
            config.model_path.unlink()
        raise
    return metrics


def _parse_args() -> FinalizationConfig:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--input-manifest", required=True, type=Path)
    parser.add_argument("--baseline-metrics", required=True, type=Path)
    parser.add_argument("--metrics", required=True, type=Path)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--chunk-size", type=int, default=100_000)
    parser.add_argument("--max-rows", type=int, default=200_000)
    parser.add_argument("--seed", type=int, default=20260727)
    args = parser.parse_args()
    return FinalizationConfig(
        input_path=args.input,
        input_manifest_path=args.input_manifest,
        baseline_metrics_path=args.baseline_metrics,
        metrics_path=args.metrics,
        model_path=args.model,
        chunk_size=args.chunk_size,
        max_rows=args.max_rows,
        seed=args.seed,
    )


def main() -> int:
    config = _parse_args()
    try:
        metrics = finalize_model(config)
    except (
        BaselineError,
        FinalizationError,
        FileExistsError,
        OSError,
        ValueError,
        json.JSONDecodeError,
        pd.errors.ParserError,
    ) as exc:
        print(f"Finalization failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    comparison = metrics["comparison"]
    print(
        f"Model v1 completed: candidate="
        f"{metrics['selected_candidate']['candidate']['candidate_id']} "
        f"test_macro_f1={comparison['day9_test_macro_f1']:.6f} "
        f"change={comparison['absolute_macro_f1_change']:+.6f}"
    )
    print(f"Wrote aggregate metrics to {config.metrics_path}")
    print(f"Wrote ignored final model to {config.model_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
