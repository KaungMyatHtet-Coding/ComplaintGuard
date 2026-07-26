"""Reproducible, privacy-safe Day 8 TF-IDF + MultinomialNB baseline."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import random
import sys
import time
import unicodedata
import uuid
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    precision_recall_fscore_support,
)
from sklearn.naive_bayes import MultinomialNB

TEXT_COLUMN = "Consumer complaint narrative"
LABEL_COLUMN = "department_label"
INPUT_COLUMNS = (TEXT_COLUMN, LABEL_COLUMN)
LABELS = (
    "transfer_payment",
    "account_support",
    "card_atm",
    "fraud_security",
    "loan_credit",
    "general_support",
)
DATASET_VERSION = "v1"
MAPPING_VERSION = "v1"
METRICS_SCHEMA_VERSION = 1


class BaselineError(RuntimeError):
    """Raised when validated baseline construction cannot complete."""


@dataclass(frozen=True)
class BaselineConfig:
    input_path: Path
    input_manifest_path: Path
    metrics_path: Path
    model_path: Path
    chunk_size: int = 100_000
    max_rows: int = 200_000
    train_ratio: float = 0.70
    validation_ratio: float = 0.15
    test_ratio: float = 0.15
    train_per_class_cap: int | None = 30_000
    seed: int = 20260727
    max_features: int = 100_000
    min_df: int = 3
    max_df: float = 0.98
    alpha: float = 1.0


def normalize_text(value: str) -> str:
    """Conservatively normalize text without changing financial meaning."""
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _validate_config(config: BaselineConfig) -> None:
    if config.chunk_size <= 0 or config.max_rows < len(LABELS):
        raise ValueError(
            "chunk_size must be positive and max_rows must preserve all labels"
        )
    if config.train_per_class_cap is not None and config.train_per_class_cap <= 0:
        raise ValueError("train_per_class_cap must be positive or omitted")
    if config.max_features <= 0 or config.min_df <= 0:
        raise ValueError("TF-IDF feature limits must be positive")
    if not 0 < config.max_df <= 1 or config.alpha <= 0:
        raise ValueError(
            "max_df and alpha must be positive; max_df must not exceed one"
        )
    if not math.isclose(
        config.train_ratio + config.validation_ratio + config.test_ratio,
        1.0,
        abs_tol=1e-12,
    ):
        raise ValueError("split ratios must sum to one")
    if min(config.train_ratio, config.validation_ratio, config.test_ratio) <= 0:
        raise ValueError("every split ratio must be positive")
    if config.metrics_path.resolve() == config.model_path.resolve():
        raise ValueError("metrics and model destinations must differ")
    if config.metrics_path.exists() or config.model_path.exists():
        raise FileExistsError(
            "refusing to overwrite an existing model or metrics artifact"
        )


def _load_input_manifest(config: BaselineConfig) -> dict[str, Any]:
    manifest = json.loads(config.input_manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "completed":
        raise BaselineError("input manifest is not completed")
    if manifest.get("dataset_version") != DATASET_VERSION:
        raise BaselineError("unexpected dataset version")
    if manifest.get("mapping_version") != MAPPING_VERSION:
        raise BaselineError("unexpected mapping version")
    output = manifest.get("output", {})
    if output.get("schema") != list(INPUT_COLUMNS):
        raise BaselineError("input manifest schema differs from the required schema")
    if output.get("file_name") != config.input_path.name:
        raise BaselineError("input filename differs from the completed manifest")
    if not isinstance(output.get("rows"), int) or isinstance(output.get("rows"), bool):
        raise BaselineError("input manifest row count is invalid")
    if set(manifest.get("label_counts", {})) != set(LABELS):
        raise BaselineError("input manifest label set is invalid")
    if sum(manifest["label_counts"].values()) != output["rows"]:
        raise BaselineError("input manifest label counts do not reconcile")
    return manifest


def _select_rows(
    config: BaselineConfig, expected_rows: int
) -> tuple[list[tuple[str, str]], Counter[str], int]:
    """Validate every row and retain a deterministic uniform reservoir."""
    header = pd.read_csv(config.input_path, nrows=0).columns.tolist()
    if header != list(INPUT_COLUMNS):
        raise BaselineError(f"required input schema is {list(INPUT_COLUMNS)!r}")

    rng = random.Random(config.seed)
    reservoir: list[tuple[str, str]] = []
    source_counts: Counter[str] = Counter()
    processed = 0
    chunks = 0
    reader = pd.read_csv(
        config.input_path,
        usecols=list(INPUT_COLUMNS),
        dtype={TEXT_COLUMN: "string", LABEL_COLUMN: "string"},
        chunksize=config.chunk_size,
        keep_default_na=True,
    )
    for chunk in reader:
        chunks += 1
        if chunk[TEXT_COLUMN].isna().any():
            raise BaselineError("null narrative encountered")
        if chunk[LABEL_COLUMN].isna().any():
            raise BaselineError("null label encountered")
        texts = chunk[TEXT_COLUMN].astype(str)
        labels = chunk[LABEL_COLUMN].astype(str)
        if texts.str.strip().eq("").any():
            raise BaselineError("empty narrative encountered")
        invalid = set(labels.unique()) - set(LABELS)
        if invalid:
            raise BaselineError(
                "input contains a label outside the six-label allowlist"
            )
        source_counts.update(labels.tolist())
        for text, label in zip(texts, labels, strict=True):
            processed += 1
            item = (text, label)
            if len(reservoir) < config.max_rows:
                reservoir.append(item)
            else:
                position = rng.randrange(processed)
                if position < config.max_rows:
                    reservoir[position] = item
    if processed != expected_rows:
        raise BaselineError(
            f"processed {processed} rows but completed manifest requires {expected_rows}"
        )
    if set(source_counts) != set(LABELS):
        raise BaselineError("source input does not represent all six labels")
    return reservoir, source_counts, chunks


def _partition_for(normalized: str, config: BaselineConfig) -> str:
    digest = hashlib.sha256(f"{config.seed}\0{normalized}".encode()).digest()
    fraction = int.from_bytes(digest[:8], "big") / 2**64
    if fraction < config.train_ratio:
        return "train"
    if fraction < config.train_ratio + config.validation_ratio:
        return "validation"
    return "test"


def split_selected_rows(
    rows: list[tuple[str, str]], config: BaselineConfig
) -> dict[str, list[tuple[str, str]]]:
    """Group exact normalized duplicates into a deterministic partition."""
    partitions: dict[str, list[tuple[str, str]]] = {
        "train": [],
        "validation": [],
        "test": [],
    }
    seen_partition: dict[str, str] = {}
    for text, label in rows:
        normalized = normalize_text(text)
        if not normalized:
            raise BaselineError("narrative is empty after normalization")
        partition = _partition_for(normalized, config)
        prior = seen_partition.setdefault(normalized, partition)
        if prior != partition:
            raise BaselineError("duplicate narrative crossed partitions")
        partitions[partition].append((normalized, label))
    for name, values in partitions.items():
        if not values:
            raise BaselineError(f"{name} partition is empty")
        if {label for _, label in values} != set(LABELS):
            raise BaselineError(f"{name} partition does not represent all six labels")
    return partitions


def balance_training_rows(
    train_rows: list[tuple[str, str]], config: BaselineConfig
) -> list[tuple[str, str]]:
    """Apply deterministic undersampling only to the training partition."""
    if config.train_per_class_cap is None:
        return list(train_rows)
    grouped: dict[str, list[tuple[str, str]]] = {label: [] for label in LABELS}
    for text, label in train_rows:
        grouped[label].append((text, label))
    selected: list[tuple[str, str]] = []
    for label in LABELS:
        ranked = sorted(
            grouped[label],
            key=lambda item: hashlib.sha256(
                f"{config.seed}\0{label}\0{item[0]}".encode()
            ).digest(),
        )
        selected.extend(ranked[: config.train_per_class_cap])
    return selected


def _counts(rows: list[tuple[str, str]]) -> dict[str, int]:
    counter = Counter(label for _, label in rows)
    return {label: counter[label] for label in LABELS}


def _matrix_summary(matrix: Any) -> dict[str, Any]:
    total = int(matrix.shape[0] * matrix.shape[1])
    nnz = int(matrix.nnz)
    return {
        "shape": [int(matrix.shape[0]), int(matrix.shape[1])],
        "non_zero": nnz,
        "density": (nnz / total) if total else 0.0,
    }


def _evaluate(y_true: list[str], y_pred: np.ndarray[Any, Any]) -> dict[str, Any]:
    macro = precision_recall_fscore_support(
        y_true, y_pred, labels=LABELS, average="macro", zero_division=0
    )
    weighted = precision_recall_fscore_support(
        y_true, y_pred, labels=LABELS, average="weighted", zero_division=0
    )
    per_class = precision_recall_fscore_support(
        y_true, y_pred, labels=LABELS, average=None, zero_division=0
    )
    matrix = confusion_matrix(y_true, y_pred, labels=LABELS)
    true_counts = Counter(y_true)
    predicted_counts = Counter(y_pred.tolist())
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "macro": {
            "precision": float(macro[0]),
            "recall": float(macro[1]),
            "f1": float(macro[2]),
        },
        "weighted": {
            "precision": float(weighted[0]),
            "recall": float(weighted[1]),
            "f1": float(weighted[2]),
        },
        "per_class": {
            label: {
                "precision": float(per_class[0][index]),
                "recall": float(per_class[1][index]),
                "f1": float(per_class[2][index]),
                "support": int(per_class[3][index]),
            }
            for index, label in enumerate(LABELS)
        },
        "confusion_matrix": {
            "label_order": list(LABELS),
            "values": matrix.astype(int).tolist(),
        },
        "true_label_counts": {label: true_counts[label] for label in LABELS},
        "predicted_label_counts": {label: predicted_counts[label] for label in LABELS},
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run_baseline(config: BaselineConfig) -> dict[str, Any]:
    """Run and atomically publish one validated aggregate-only baseline."""
    _validate_config(config)
    input_manifest = _load_input_manifest(config)
    started = time.perf_counter()
    rows, source_counts, chunks = _select_rows(config, input_manifest["output"]["rows"])
    selection_finished = time.perf_counter()
    partitions = split_selected_rows(rows, config)
    natural_train = partitions["train"]
    balanced_train = balance_training_rows(natural_train, config)
    validation_rows = partitions["validation"]
    test_rows = partitions["test"]

    vectorizer = TfidfVectorizer(
        lowercase=False,
        ngram_range=(1, 2),
        min_df=config.min_df,
        max_df=config.max_df,
        max_features=config.max_features,
        sublinear_tf=True,
        dtype=np.float32,
    )
    train_text = [text for text, _ in balanced_train]
    train_labels = [label for _, label in balanced_train]
    validation_text = [text for text, _ in validation_rows]
    validation_labels = [label for _, label in validation_rows]
    test_text = [text for text, _ in test_rows]
    test_labels = [label for _, label in test_rows]

    fit_started = time.perf_counter()
    train_matrix = vectorizer.fit_transform(train_text)
    fit_finished = time.perf_counter()
    transform_started = fit_finished
    validation_matrix = vectorizer.transform(validation_text)
    test_matrix = vectorizer.transform(test_text)
    transform_finished = time.perf_counter()
    model = MultinomialNB(alpha=config.alpha)
    train_started = transform_finished
    model.fit(train_matrix, train_labels)
    train_finished = time.perf_counter()
    predict_started = train_finished
    validation_predictions = model.predict(validation_matrix)
    test_predictions = model.predict(test_matrix)
    predict_finished = time.perf_counter()
    if set(model.classes_) != set(LABELS):
        raise BaselineError("trained model class set is invalid")
    if set(test_predictions) - set(LABELS):
        raise BaselineError("model emitted an invalid label")

    metrics = {
        "metrics_schema_version": METRICS_SCHEMA_VERSION,
        "status": "completed",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "dataset_version": DATASET_VERSION,
        "mapping_version": MAPPING_VERSION,
        "source": {
            "file_name": config.input_path.name,
            "manifest_file_name": config.input_manifest_path.name,
            "rows": input_manifest["output"]["rows"],
            "label_counts": {label: source_counts[label] for label in LABELS},
        },
        "configuration": {
            **asdict(config),
            "input_path": config.input_path.name,
            "input_manifest_path": config.input_manifest_path.name,
            "metrics_path": config.metrics_path.name,
            "model_path": config.model_path.name,
            "normalization": "Unicode NFKC, case-folding, whitespace collapse",
            "sampling": "single-pass seeded uniform reservoir over source rows",
            "split": "SHA-256 group assignment by normalized narrative",
            "balancing": "deterministic per-class cap on training partition only",
            "tfidf": {
                "analyzer": "word",
                "ngram_range": [1, 2],
                "lowercase": False,
                "min_df": config.min_df,
                "max_df": config.max_df,
                "max_features": config.max_features,
                "sublinear_tf": True,
                "dtype": "float32",
            },
            "model": {"type": "MultinomialNB", "alpha": config.alpha},
        },
        "selection": {
            "selected_rows": len(rows),
            "chunks_processed": chunks,
            "selected_label_counts": _counts(rows),
        },
        "partitions": {
            "natural_train": {
                "rows": len(natural_train),
                "label_counts": _counts(natural_train),
            },
            "balanced_train": {
                "rows": len(balanced_train),
                "label_counts": _counts(balanced_train),
            },
            "validation": {
                "rows": len(validation_rows),
                "label_counts": _counts(validation_rows),
            },
            "test": {"rows": len(test_rows), "label_counts": _counts(test_rows)},
        },
        "features": {
            "vocabulary_size": len(vectorizer.vocabulary_),
            "train": _matrix_summary(train_matrix),
            "validation": _matrix_summary(validation_matrix),
            "test": _matrix_summary(test_matrix),
        },
        "validation_metrics": _evaluate(validation_labels, validation_predictions),
        "test_metrics": _evaluate(test_labels, test_predictions),
        "timings_seconds": {
            "source_selection": selection_finished - started,
            "feature_fit": fit_finished - fit_started,
            "held_out_transform": transform_finished - transform_started,
            "model_training": train_finished - train_started,
            "prediction": predict_finished - predict_started,
            "total": predict_finished - started,
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
        },
        "limitations": [
            "Labels are deterministic Product/Issue policy proxies, not institutional ground truth.",
            "The source distribution is strongly imbalanced.",
            "The experiment uses a bounded sample rather than the complete corpus.",
            "Training-only undersampling changes model priors; validation and test are unchanged.",
        ],
    }
    test_support = sum(
        item["support"] for item in metrics["test_metrics"]["per_class"].values()
    )
    confusion_total = sum(
        sum(row) for row in metrics["test_metrics"]["confusion_matrix"]["values"]
    )
    if test_support != len(test_rows) or confusion_total != len(test_rows):
        raise BaselineError("test metrics do not reconcile")

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
                "vectorizer": vectorizer,
                "model": model,
                "labels": LABELS,
                "normalization": "NFKC + casefold + whitespace collapse",
                "dataset_version": DATASET_VERSION,
                "mapping_version": MAPPING_VERSION,
            },
            model_temp,
        )
        model_metadata = {
            "file_name": config.model_path.name,
            "size_bytes": model_temp.stat().st_size,
            "sha256": _sha256(model_temp),
        }
        metrics["generated_model"] = model_metadata
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


def _parse_args() -> BaselineConfig:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--input-manifest", type=Path, required=True)
    parser.add_argument("--metrics", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--chunk-size", type=int, default=100_000)
    parser.add_argument("--max-rows", type=int, default=200_000)
    parser.add_argument("--train-per-class-cap", type=int, default=30_000)
    parser.add_argument("--seed", type=int, default=20260727)
    parser.add_argument("--max-features", type=int, default=100_000)
    parser.add_argument("--min-df", type=int, default=3)
    parser.add_argument("--max-df", type=float, default=0.98)
    parser.add_argument("--alpha", type=float, default=1.0)
    args = parser.parse_args()
    return BaselineConfig(
        input_path=args.input,
        input_manifest_path=args.input_manifest,
        metrics_path=args.metrics,
        model_path=args.model,
        chunk_size=args.chunk_size,
        max_rows=args.max_rows,
        train_per_class_cap=args.train_per_class_cap,
        seed=args.seed,
        max_features=args.max_features,
        min_df=args.min_df,
        max_df=args.max_df,
        alpha=args.alpha,
    )


def main() -> int:
    config = _parse_args()
    try:
        metrics = run_baseline(config)
    except (
        BaselineError,
        FileExistsError,
        OSError,
        ValueError,
        json.JSONDecodeError,
        pd.errors.ParserError,
    ) as exc:
        print(f"Baseline failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    test = metrics["test_metrics"]
    print(
        f"Baseline completed: selected={metrics['selection']['selected_rows']} "
        f"test={metrics['partitions']['test']['rows']} "
        f"macro_f1={test['macro']['f1']:.6f}"
    )
    print(f"Wrote aggregate metrics to {config.metrics_path}")
    print(f"Wrote ignored model artifact to {config.model_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
