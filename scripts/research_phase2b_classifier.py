"""Bounded Phase 2B classifier research over Phase 2A development data only."""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import math
import platform
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.frozen import FrozenEstimator
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support
from sklearn.naive_bayes import ComplementNB, MultinomialNB
from sklearn.neighbors import NearestNeighbors
from sklearn.pipeline import FeatureUnion

try:
    from cfpb_label_mapping import load_mapping_policy, map_department, normalize_category
    from train_department_baseline import (
        LABELS,
        BaselineConfig,
        _select_rows,
        balance_training_rows,
        normalize_text,
        split_selected_rows,
    )
except ModuleNotFoundError:  # pragma: no cover
    from scripts.cfpb_label_mapping import (
        load_mapping_policy,
        map_department,
        normalize_category,
    )
    from scripts.train_department_baseline import (
        LABELS,
        BaselineConfig,
        _select_rows,
        balance_training_rows,
        normalize_text,
        split_selected_rows,
    )


SCHEMA_VERSION = 1
AUDIT_SCHEMA_VERSION = 1
LOCKED_RESERVOIR_SEED = 20260727
DEVELOPMENT_SEED = 20260810
EXPECTED_DATASET_SHA256 = (
    "71a5ffda7914664a2b6803d92a6327bbe8e2438036e4420d3b30b95928241848"
)
MAX_PER_CLASS_F1_REGRESSION = 0.03
CONFIDENCE_THRESHOLDS = (0.60, 0.70, 0.80, 0.90)
LENGTH_BUCKETS = ((0, 100), (101, 300), (301, 1000), (1001, None))
NEAR_DUPLICATE_NGRAM_RANGE = (4, 5)
NEAR_DUPLICATE_THRESHOLD = 0.98
NEAR_DUPLICATE_MAX_FEATURES = 50_000
AUDIT_CHUNK_SIZE = 100_000
INPUT_COLUMNS = ("Product", "Issue")


class ResearchError(RuntimeError):
    """Raised when a Phase 2B integrity contract is not satisfied."""


@dataclass(frozen=True)
class CandidateSpec:
    matrix_id: str
    candidate_id: str
    vectorizer: str
    classifier: str
    training_variant: str = "d0"
    alpha: float | None = None
    c: float | None = None
    norm: bool | None = None
    sample_weight: bool = False
    fraud_cap: int | None = 30_000
    hierarchical: bool = False


CORE_MATRIX_IDS = (
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


REGRESSION_CASES = (
    (
        "mobile_transfer_short",
        "Mobile transfer failed",
        "transfer_payment",
    ),
    (
        "mobile_transfer_clear",
        "I transferred money through mobile banking. The amount was deducted from my account, but the recipient did not receive it.",
        "transfer_payment",
    ),
    (
        "account_access",
        "I cannot access my mobile banking account.",
        "account_support",
    ),
    (
        "card_payment",
        "My debit card payment was declined at the store.",
        "card_atm",
    ),
    (
        "fraud",
        "A transaction I did not authorize appeared on my account.",
        "fraud_security",
    ),
    (
        "loan",
        "My loan payment was applied incorrectly and interest increased.",
        "loan_credit",
    ),
    (
        "general",
        "I need help understanding a financial service problem.",
        "general_support",
    ),
    ("short_transfer", "Transfer failed", "transfer_payment"),
    ("short_account", "Cannot log in", "account_support"),
    ("short_card", "Card declined", "card_atm"),
    ("short_fraud", "Not my transaction", "fraud_security"),
    ("short_loan", "Loan payment wrong", "loan_credit"),
    ("short_general", "Need help", "general_support"),
)


class ProbabilityEstimator(ClassifierMixin, BaseEstimator):
    """Frozen probability passthrough for calibrating composite models."""

    def __init__(self, classes: tuple[str, ...] | list[str]) -> None:
        self.classes_ = np.asarray(classes)

    def fit(self, _features: Any, _labels: Any) -> "ProbabilityEstimator":
        return self

    def predict_proba(self, features: Any) -> np.ndarray[Any, Any]:
        return np.asarray(features, dtype=float)

    def predict(self, features: Any) -> np.ndarray[Any, Any]:
        probabilities = self.predict_proba(features)
        return self.classes_[np.argmax(probabilities, axis=1)]

    def get_params(self, deep: bool = True) -> dict[str, Any]:
        del deep
        return {"classes": tuple(self.classes_.tolist())}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def development_partition(normalized: str, seed: int = DEVELOPMENT_SEED) -> str:
    """Use the exact Phase 2A fit/calibration/validation grouping contract."""
    digest = hashlib.sha256(f"phase2a\0{seed}\0{normalized}".encode()).digest()
    fraction = int.from_bytes(digest[:8], "big") / 2**64
    if fraction < 0.70:
        return "fit"
    if fraction < 0.85:
        return "calibration"
    return "validation"


def split_development_rows(
    rows: list[tuple[str, str]], seed: int = DEVELOPMENT_SEED
) -> dict[str, list[tuple[str, str]]]:
    partitions = {"fit": [], "calibration": [], "validation": []}
    seen: dict[str, str] = {}
    for text, label in rows:
        normalized = normalize_text(text)
        partition = development_partition(normalized, seed)
        prior = seen.setdefault(normalized, partition)
        if prior != partition:
            raise ResearchError("exact normalized duplicate crossed development splits")
        partitions[partition].append((normalized, label))
    for name, values in partitions.items():
        if {label for _, label in values} != set(LABELS):
            raise ResearchError(f"development {name} does not contain all labels")
    return partitions


def make_vectorizer(kind: str) -> TfidfVectorizer | FeatureUnion:
    word = TfidfVectorizer(
        lowercase=False,
        ngram_range=(1, 2),
        min_df=3,
        max_df=0.98,
        max_features=100_000,
        sublinear_tf=True,
        dtype=np.float32,
    )
    if kind == "word":
        return word
    if kind != "word_char":
        raise ValueError(f"unknown vectorizer kind: {kind}")
    char = TfidfVectorizer(
        lowercase=False,
        analyzer="char_wb",
        ngram_range=(3, 5),
        min_df=3,
        max_features=75_000,
        sublinear_tf=True,
        dtype=np.float32,
    )
    return FeatureUnion((("word", word), ("char", char)))


def make_classifier(spec: CandidateSpec) -> Any:
    if spec.classifier == "MultinomialNB":
        return MultinomialNB(alpha=spec.alpha)
    if spec.classifier == "ComplementNB":
        return ComplementNB(alpha=spec.alpha, norm=spec.norm)
    if spec.classifier == "LogisticRegression":
        return LogisticRegression(
            C=spec.c,
            class_weight="balanced",
            max_iter=2_000,
            random_state=DEVELOPMENT_SEED,
            solver="lbfgs",
        )
    raise ValueError(f"unknown classifier: {spec.classifier}")


def candidate_specs() -> list[CandidateSpec]:
    specs = [
        CandidateSpec("MNB-0", "mnb_0", "word", "MultinomialNB", alpha=0.5),
        CandidateSpec("CNB-0", "cnb_0", "word", "ComplementNB", alpha=0.5, norm=False),
        CandidateSpec(
            "LR-W",
            "lr_w",
            "word",
            "LogisticRegression",
            c=2.0,
        ),
        CandidateSpec(
            "LR-WC",
            "lr_wc",
            "word_char",
            "LogisticRegression",
            c=2.0,
        ),
        CandidateSpec(
            "HIER-WC",
            "hier_wc",
            "word_char",
            "LogisticRegression",
            c=2.0,
            hierarchical=True,
        ),
        CandidateSpec(
            "MNB-SW",
            "mnb_sw",
            "word",
            "MultinomialNB",
            alpha=0.5,
            sample_weight=True,
        ),
        CandidateSpec(
            "MNB-C15",
            "mnb_c15",
            "word",
            "MultinomialNB",
            alpha=0.5,
            fraud_cap=15_000,
        ),
        CandidateSpec(
            "CNB-SET",
            "cnb_set_alpha_01",
            "word",
            "ComplementNB",
            alpha=0.1,
            norm=False,
        ),
        CandidateSpec(
            "CNB-SET",
            "cnb_set_alpha_10",
            "word",
            "ComplementNB",
            alpha=1.0,
            norm=False,
        ),
        CandidateSpec(
            "CNB-SET",
            "cnb_set_norm_true",
            "word",
            "ComplementNB",
            alpha=0.5,
            norm=True,
        ),
        CandidateSpec(
            "DQ-EXACT",
            "dq_exact",
            "word",
            "MultinomialNB",
            training_variant="exact",
            alpha=0.5,
        ),
        CandidateSpec(
            "DQ-CONFLICT",
            "dq_conflict",
            "word",
            "MultinomialNB",
            training_variant="conflict",
            alpha=0.5,
        ),
        CandidateSpec(
            "DQ-NEAR",
            "dq_near",
            "word",
            "MultinomialNB",
            training_variant="near",
            alpha=0.5,
        ),
    ]
    if {spec.matrix_id for spec in specs} != set(CORE_MATRIX_IDS):
        raise ResearchError("Phase 2B matrix IDs do not match the predeclared matrix")
    return specs


def metric_summary(
    y_true: list[str], y_pred: np.ndarray[Any, Any]
) -> dict[str, Any]:
    macro = precision_recall_fscore_support(
        y_true, y_pred, labels=LABELS, average="macro", zero_division=0
    )
    weighted = precision_recall_fscore_support(
        y_true, y_pred, labels=LABELS, average="weighted", zero_division=0
    )
    per_class = precision_recall_fscore_support(
        y_true, y_pred, labels=LABELS, average=None, zero_division=0
    )
    matrix = confusion_matrix(y_true, y_pred, labels=LABELS).astype(int)
    return {
        "macro_f1": float(macro[2]),
        "weighted_f1": float(weighted[2]),
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
            "values": matrix.tolist(),
        },
        "transfer_as_account": int(matrix[0, 1]),
        "account_as_transfer": int(matrix[1, 0]),
    }


def confidence_metrics(
    y_true: list[str],
    probabilities: np.ndarray[Any, Any],
    classes: np.ndarray[Any, Any],
) -> dict[str, Any]:
    indices = np.argmax(probabilities, axis=1)
    predictions = classes[indices]
    confidence = np.max(probabilities, axis=1)
    correct = predictions == np.asarray(y_true)
    one_hot = np.zeros_like(probabilities)
    class_index = {label: index for index, label in enumerate(classes)}
    for row, label in enumerate(y_true):
        one_hot[row, class_index[label]] = 1.0
    brier = float(np.mean(np.sum((probabilities - one_hot) ** 2, axis=1)))
    bins = []
    ece = 0.0
    for lower in np.arange(0.0, 1.0, 0.1):
        upper = float(lower + 0.1)
        mask = (confidence >= lower) & (
            confidence <= upper if math.isclose(upper, 1.0) else confidence < upper
        )
        count = int(np.sum(mask))
        accuracy = float(np.mean(correct[mask])) if count else None
        mean_confidence = float(np.mean(confidence[mask])) if count else None
        if count:
            ece += (count / len(y_true)) * abs(accuracy - mean_confidence)
        bins.append(
            {
                "lower": float(lower),
                "upper": upper,
                "count": count,
                "accuracy": accuracy,
                "mean_confidence": mean_confidence,
            }
        )
    wrong_high = {
        str(threshold): int(np.sum((confidence >= threshold) & ~correct))
        for threshold in CONFIDENCE_THRESHOLDS
    }
    return {
        "ece": float(ece),
        "multiclass_brier": brier,
        "bins": bins,
        "wrong_high_confidence": wrong_high,
    }


def length_metrics(
    texts: list[str], y_true: list[str], y_pred: np.ndarray[Any, Any]
) -> list[dict[str, Any]]:
    lengths = np.asarray([len(text) for text in texts])
    truth = np.asarray(y_true)
    rows = []
    for lower, upper in LENGTH_BUCKETS:
        mask = lengths >= lower
        if upper is not None:
            mask &= lengths <= upper
        count = int(np.sum(mask))
        if count == 0:
            raise ResearchError(f"length bucket {lower}-{upper} is empty")
        macro = precision_recall_fscore_support(
            truth[mask], y_pred[mask], labels=LABELS, average="macro", zero_division=0
        )
        per_class = precision_recall_fscore_support(
            truth[mask],
            y_pred[mask],
            labels=LABELS,
            average=None,
            zero_division=0,
        )
        matrix = confusion_matrix(truth[mask], y_pred[mask], labels=LABELS)
        rows.append(
            {
                "minimum_characters": lower,
                "maximum_characters": upper,
                "count": count,
                "accuracy": float(np.mean(truth[mask] == y_pred[mask])),
                "macro_f1": float(macro[2]),
                "transfer_recall": float(per_class[1][0]),
                "account_recall": float(per_class[1][1]),
                "transfer_as_account": int(matrix[0, 1]),
                "account_as_transfer": int(matrix[1, 0]),
            }
        )
    return rows


def fraud_metrics(
    y_true: list[str], y_pred: np.ndarray[Any, Any]
) -> dict[str, Any]:
    truth = np.asarray(y_true)
    non_fraud = truth != "fraud_security"
    fraud = ~non_fraud
    false_positive = int(np.sum(non_fraud & (y_pred == "fraud_security")))
    false_negative = int(np.sum(fraud & (y_pred != "fraud_security")))
    return {
        "false_positives": false_positive,
        "false_negatives": false_negative,
        "non_fraud_support": int(np.sum(non_fraud)),
        "fraud_support": int(np.sum(fraud)),
        "false_positive_rate": float(false_positive / np.sum(non_fraud)),
        "false_negative_rate": float(false_negative / np.sum(fraud)),
    }


def _feature_masks(vectorizer: Any) -> dict[str, np.ndarray[Any, Any]]:
    names = np.asarray(vectorizer.get_feature_names_out(), dtype=object)
    if any(str(name).startswith("word__") for name in names):
        word_mask = np.asarray(
            [str(name).startswith("word__") for name in names], dtype=bool
        )
        char_mask = ~word_mask
    else:
        word_mask = np.ones(len(names), dtype=bool)
        char_mask = np.zeros(len(names), dtype=bool)
    return {"word": word_mask, "character": char_mask}


def boundary_overlap_metrics(
    vectorizer: Any,
    fit_matrix: Any,
    fit_labels: list[str],
    validation_matrix: Any,
    y_true: list[str],
    y_pred: np.ndarray[Any, Any],
) -> dict[str, Any]:
    fit_label_array = np.asarray(fit_labels)
    truth = np.asarray(y_true)
    masks = _feature_masks(vectorizer)
    output: dict[str, Any] = {}
    for feature_kind, feature_mask in masks.items():
        if not np.any(feature_mask):
            continue
        transfer_present = (
            fit_matrix[fit_label_array == "transfer_payment"][:, feature_mask]
            .getnnz(axis=0)
            .ravel()
            > 0
        )
        account_present = (
            fit_matrix[fit_label_array == "account_support"][:, feature_mask]
            .getnnz(axis=0)
            .ravel()
            > 0
        )
        shared = transfer_present & account_present
        union = transfer_present | account_present
        validation_active_shared = (
            validation_matrix[:, feature_mask][:, shared].getnnz(axis=1) > 0
            if np.any(shared)
            else np.zeros(validation_matrix.shape[0], dtype=bool)
        )
        transfer_error = (truth == "transfer_payment") & (
            y_pred == "account_support"
        )
        account_error = (truth == "account_support") & (
            y_pred == "transfer_payment"
        )
        output[feature_kind] = {
            "feature_count": int(np.sum(feature_mask)),
            "transfer_features": int(np.sum(transfer_present)),
            "account_features": int(np.sum(account_present)),
            "shared_features": int(np.sum(shared)),
            "union_features": int(np.sum(union)),
            "shared_fraction_of_union": float(
                np.sum(shared) / np.sum(union) if np.sum(union) else 0.0
            ),
            "transfer_account_errors": int(np.sum(transfer_error)),
            "transfer_account_errors_with_shared_feature": int(
                np.sum(transfer_error & validation_active_shared)
            ),
            "account_transfer_errors": int(np.sum(account_error)),
            "account_transfer_errors_with_shared_feature": int(
                np.sum(account_error & validation_active_shared)
            ),
        }
    return output


def _sorted_group_rows(rows: list[tuple[str, str]]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for text, label in rows:
        groups[text].append(label)
    return groups


def conflicting_groups(rows: list[tuple[str, str]]) -> set[str]:
    return {
        text for text, labels in _sorted_group_rows(rows).items() if len(set(labels)) > 1
    }


def exact_duplicate_variant(rows: list[tuple[str, str]]) -> list[tuple[str, str]]:
    groups = _sorted_group_rows(rows)
    output: list[tuple[str, str]] = []
    for text, labels in groups.items():
        if len(set(labels)) > 1:
            output.extend((text, label) for label in labels)
        else:
            output.append((text, labels[0]))
    return sorted(output, key=lambda row: (row[0], row[1]))


def conflict_variant(rows: list[tuple[str, str]]) -> list[tuple[str, str]]:
    conflicts = conflicting_groups(rows)
    return [row for row in rows if row[0] not in conflicts]


def near_duplicate_variant(
    rows: list[tuple[str, str]],
    threshold: float = NEAR_DUPLICATE_THRESHOLD,
) -> tuple[list[tuple[str, str]], dict[str, Any]]:
    exact_rows = exact_duplicate_variant(rows)
    ordered = sorted(
        exact_rows,
        key=lambda row: (hashlib.sha256(row[0].encode()).digest(), row[0], row[1]),
    )
    if len(ordered) < 2:
        return ordered, {
            "method": "char_wb_tfidf_4_5_mutual_nearest_neighbor",
            "threshold_cosine_similarity": threshold,
            "fit_rows_before": len(rows),
            "fit_rows_after_exact_collapse": len(exact_rows),
            "candidate_pairs": 0,
            "same_label_pairs_collapsed": 0,
            "near_conflicting_pairs_retained": 0,
            "fit_rows_after_near_collapse": len(ordered),
        }
    texts = [text for text, _ in ordered]
    labels = [label for _, label in ordered]
    vectorizer = TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=NEAR_DUPLICATE_NGRAM_RANGE,
        min_df=1,
        max_features=NEAR_DUPLICATE_MAX_FEATURES,
        dtype=np.float32,
    )
    matrix = vectorizer.fit_transform(texts)
    neighbors = NearestNeighbors(n_neighbors=2, metric="cosine").fit(matrix)
    distances, indices = neighbors.kneighbors(matrix)
    consumed: set[int] = set()
    dropped: set[int] = set()
    candidate_pairs = 0
    same_label_pairs = 0
    conflicting_pairs = 0
    for index in range(len(ordered)):
        neighbor = int(indices[index, 1])
        similarity = 1.0 - float(distances[index, 1])
        if index in consumed or neighbor in consumed or similarity < threshold:
            continue
        if int(indices[neighbor, 1]) != index:
            continue
        candidate_pairs += 1
        consumed.update((index, neighbor))
        if labels[index] == labels[neighbor]:
            same_label_pairs += 1
            dropped.add(max(index, neighbor))
        else:
            conflicting_pairs += 1
    output = [row for index, row in enumerate(ordered) if index not in dropped]
    summary = {
        "method": "char_wb_tfidf_4_5_mutual_nearest_neighbor",
        "threshold_cosine_similarity": threshold,
        "clustering_rule": "sort by SHA-256(normalized text), use disjoint reciprocal nearest-neighbor pairs, and drop the later hash only for same-label pairs",
        "fit_rows_before": len(rows),
        "fit_rows_after_exact_collapse": len(exact_rows),
        "candidate_pairs": candidate_pairs,
        "same_label_pairs_collapsed": same_label_pairs,
        "near_conflicting_pairs_retained": conflicting_pairs,
        "fit_rows_after_near_collapse": len(output),
    }
    del vectorizer, matrix, neighbors, distances, indices
    gc.collect()
    return output, summary


def near_duplicate_sample(
    fit_rows: list[tuple[str, str]], validation_rows: list[tuple[str, str]]
) -> dict[str, Any]:
    def sampled(rows: list[tuple[str, str]]) -> list[str]:
        return [
            text
            for text, _ in sorted(
                rows,
                key=lambda row: hashlib.sha256(row[0].encode()).digest(),
            )[:2_000]
        ]

    fit_text = sampled(fit_rows)
    validation_text = sampled(validation_rows)
    vectorizer = TfidfVectorizer(
        analyzer="char_wb", ngram_range=(4, 5), min_df=2, max_features=50_000
    )
    fit_matrix = vectorizer.fit_transform(fit_text)
    validation_matrix = vectorizer.transform(validation_text)
    distances, _ = (
        NearestNeighbors(n_neighbors=1, metric="cosine")
        .fit(fit_matrix)
        .kneighbors(validation_matrix)
    )
    similarities = 1.0 - distances[:, 0]
    return {
        "method": "deterministic 2,000-by-2,000 char 4-5 gram nearest-neighbor sample",
        "fit_sample": len(fit_text),
        "validation_sample": len(validation_text),
        "maximum_cosine_similarity": float(np.max(similarities)),
        "at_or_above_0_90": int(np.sum(similarities >= 0.90)),
        "at_or_above_0_95": int(np.sum(similarities >= 0.95)),
        "limitation": "sampled development-only risk estimate; not exhaustive proof",
    }


def training_weights(rows: list[tuple[str, str]]) -> np.ndarray[Any, Any]:
    counts = Counter(label for _, label in rows)
    total = len(rows)
    return np.asarray(
        [total / (len(LABELS) * counts[label]) for _, label in rows], dtype=np.float64
    )


def _variant_rows(
    base_fit_rows: list[tuple[str, str]], variant: str
) -> tuple[list[tuple[str, str]], dict[str, Any]]:
    if variant == "d0":
        return list(base_fit_rows), {"variant": "D0", "rows": len(base_fit_rows)}
    if variant == "exact":
        rows = exact_duplicate_variant(base_fit_rows)
        return rows, {
            "variant": "DQ-EXACT",
            "rows_before": len(base_fit_rows),
            "rows_after": len(rows),
            "rule": "collapse same-label normalized duplicates in fit only; retain conflicts",
        }
    if variant == "conflict":
        rows = conflict_variant(base_fit_rows)
        return rows, {
            "variant": "DQ-CONFLICT",
            "rows_before": len(base_fit_rows),
            "rows_after": len(rows),
            "conflicting_groups_removed_from_fit": len(conflicting_groups(base_fit_rows)),
            "rule": "exclude conflicting groups from fit only; do not relabel",
        }
    if variant == "near":
        return near_duplicate_variant(base_fit_rows)
    raise ResearchError(f"unknown training variant: {variant}")


def _calibrated_validation_metrics(
    model: Any,
    calibration_matrix: Any,
    calibration_labels: list[str],
    validation_matrix: Any,
    validation_labels: list[str],
) -> dict[str, Any]:
    calibrated = CalibratedClassifierCV(FrozenEstimator(model), method="sigmoid")
    calibrated.fit(calibration_matrix, calibration_labels)
    probabilities = calibrated.predict_proba(validation_matrix)
    return confidence_metrics(
        validation_labels, probabilities, calibrated.classes_
    )


def _fit_flat(
    spec: CandidateSpec,
    fit_rows: list[tuple[str, str]],
    calibration_rows: list[tuple[str, str]],
    validation_rows: list[tuple[str, str]],
) -> dict[str, Any]:
    fit_text = [text for text, _ in fit_rows]
    fit_labels = [label for _, label in fit_rows]
    calibration_text = [text for text, _ in calibration_rows]
    calibration_labels = [label for _, label in calibration_rows]
    validation_text = [text for text, _ in validation_rows]
    validation_labels = [label for _, label in validation_rows]
    vectorizer = make_vectorizer(spec.vectorizer)
    fit_matrix = vectorizer.fit_transform(fit_text)
    calibration_matrix = vectorizer.transform(calibration_text)
    validation_matrix = vectorizer.transform(validation_text)
    model = make_classifier(spec)
    weights = training_weights(fit_rows) if spec.sample_weight else None
    if weights is None:
        model.fit(fit_matrix, fit_labels)
    else:
        model.fit(fit_matrix, fit_labels, sample_weight=weights)
    predictions = model.predict(validation_matrix)
    probabilities = model.predict_proba(validation_matrix)
    metrics = metric_summary(validation_labels, predictions)
    result: dict[str, Any] = {
        "matrix_id": spec.matrix_id,
        "candidate": asdict(spec),
        "feature_count": int(fit_matrix.shape[1]),
        "validation_metrics": metrics,
        "text_length_metrics": length_metrics(
            validation_text, validation_labels, predictions
        ),
        "fraud_metrics": fraud_metrics(validation_labels, predictions),
        "boundary_overlap": boundary_overlap_metrics(
            vectorizer,
            fit_matrix,
            fit_labels,
            validation_matrix,
            validation_labels,
            predictions,
        ),
        "raw_confidence": confidence_metrics(
            validation_labels, probabilities, model.classes_
        ),
        "synthetic_regression": regression_results(
            vectorizer, model, spec.candidate_id
        ),
        "calibrated_confidence": _calibrated_validation_metrics(
            model,
            calibration_matrix,
            calibration_labels,
            validation_matrix,
            validation_labels,
        ),
        "training_rows": len(fit_rows),
        "calibration_rows": len(calibration_rows),
        "validation_rows": len(validation_rows),
    }
    del vectorizer, fit_matrix, calibration_matrix, validation_matrix, model
    gc.collect()
    return result


def _hierarchical_probabilities(
    stage_one: Any,
    stage_two: Any,
    stage_one_matrix: Any,
    stage_two_matrix: Any,
) -> np.ndarray[Any, Any]:
    stage_one_probabilities = stage_one.predict_proba(stage_one_matrix)
    stage_two_probabilities = stage_two.predict_proba(stage_two_matrix)
    output = np.zeros((stage_one_matrix.shape[0], len(LABELS)), dtype=float)
    stage_one_classes = list(stage_one.classes_)
    fraud_probability = stage_one_probabilities[
        :, stage_one_classes.index("fraud_security")
    ]
    other_probability = stage_one_probabilities[:, stage_one_classes.index("other")]
    output[:, LABELS.index("fraud_security")] = fraud_probability
    for index, label in enumerate(stage_two.classes_):
        output[:, LABELS.index(str(label))] = other_probability * stage_two_probabilities[
            :, index
        ]
    return output


def hierarchy_probability_matrix(
    stage_one_probabilities: np.ndarray[Any, Any],
    stage_one_classes: list[str] | tuple[str, ...],
    stage_two_probabilities: np.ndarray[Any, Any],
    stage_two_classes: list[str] | tuple[str, ...],
) -> np.ndarray[Any, Any]:
    output = np.zeros((stage_one_probabilities.shape[0], len(LABELS)), dtype=float)
    fraud_index = list(stage_one_classes).index("fraud_security")
    other_index = list(stage_one_classes).index("other")
    output[:, LABELS.index("fraud_security")] = stage_one_probabilities[:, fraud_index]
    for index, label in enumerate(stage_two_classes):
        output[:, LABELS.index(str(label))] = (
            stage_one_probabilities[:, other_index] * stage_two_probabilities[:, index]
        )
    return output


def _fit_hierarchical(
    spec: CandidateSpec,
    fit_rows: list[tuple[str, str]],
    calibration_rows: list[tuple[str, str]],
    validation_rows: list[tuple[str, str]],
) -> dict[str, Any]:
    fit_text = [text for text, _ in fit_rows]
    fit_labels = [label for _, label in fit_rows]
    calibration_text = [text for text, _ in calibration_rows]
    calibration_labels = [label for _, label in calibration_rows]
    validation_text = [text for text, _ in validation_rows]
    validation_labels = [label for _, label in validation_rows]
    stage_one_labels = [
        "fraud_security" if label == "fraud_security" else "other"
        for label in fit_labels
    ]
    stage_two_rows = [
        row for row in fit_rows if row[1] != "fraud_security"
    ]
    stage_two_text = [text for text, _ in stage_two_rows]
    stage_two_labels = [label for _, label in stage_two_rows]
    stage_one_vectorizer = make_vectorizer(spec.vectorizer)
    stage_two_vectorizer = make_vectorizer(spec.vectorizer)
    stage_one_fit_matrix = stage_one_vectorizer.fit_transform(fit_text)
    stage_two_fit_matrix = stage_two_vectorizer.fit_transform(stage_two_text)
    stage_one_calibration_matrix = stage_one_vectorizer.transform(calibration_text)
    stage_two_calibration_matrix = stage_two_vectorizer.transform(calibration_text)
    stage_one_validation_matrix = stage_one_vectorizer.transform(validation_text)
    stage_two_validation_matrix = stage_two_vectorizer.transform(validation_text)
    stage_one = LogisticRegression(
        C=spec.c,
        class_weight="balanced",
        max_iter=2_000,
        random_state=DEVELOPMENT_SEED,
        solver="lbfgs",
    )
    stage_two = LogisticRegression(
        C=spec.c,
        class_weight="balanced",
        max_iter=2_000,
        random_state=DEVELOPMENT_SEED,
        solver="lbfgs",
    )
    stage_one.fit(stage_one_fit_matrix, stage_one_labels)
    stage_two.fit(stage_two_fit_matrix, stage_two_labels)
    validation_probabilities = _hierarchical_probabilities(
        stage_one,
        stage_two,
        stage_one_validation_matrix,
        stage_two_validation_matrix,
    )
    predictions = np.asarray(LABELS)[np.argmax(validation_probabilities, axis=1)]
    stage_one_calibration_probabilities = stage_one.predict_proba(
        stage_one_calibration_matrix
    )
    stage_two_calibration_probabilities = stage_two.predict_proba(
        stage_two_calibration_matrix
    )
    calibration_probabilities = hierarchy_probability_matrix(
        stage_one_calibration_probabilities,
        list(stage_one.classes_),
        stage_two_calibration_probabilities,
        list(stage_two.classes_),
    )
    calibrated = CalibratedClassifierCV(
        FrozenEstimator(ProbabilityEstimator(tuple(LABELS))), method="sigmoid"
    )
    calibrated.fit(calibration_probabilities, calibration_labels)
    calibrated_validation_probabilities = calibrated.predict_proba(
        validation_probabilities
    )
    result = {
        "matrix_id": spec.matrix_id,
        "candidate": asdict(spec),
        "feature_count": {
            "stage_one": int(stage_one_fit_matrix.shape[1]),
            "stage_two": int(stage_two_fit_matrix.shape[1]),
            "total": int(stage_one_fit_matrix.shape[1] + stage_two_fit_matrix.shape[1]),
        },
        "stages": {
            "stage_one": "fraud_security_vs_other",
            "stage_two": [label for label in LABELS if label != "fraud_security"],
            "end_to_end_predictions": True,
            "threshold": None,
        },
        "validation_metrics": metric_summary(validation_labels, predictions),
        "text_length_metrics": length_metrics(
            validation_text, validation_labels, predictions
        ),
        "fraud_metrics": fraud_metrics(validation_labels, predictions),
        "boundary_overlap": boundary_overlap_metrics(
            stage_two_vectorizer,
            stage_two_fit_matrix,
            stage_two_labels,
            stage_two_validation_matrix,
            validation_labels,
            predictions,
        ),
        "raw_confidence": confidence_metrics(
            validation_labels, validation_probabilities, np.asarray(LABELS)
        ),
        "calibrated_confidence": confidence_metrics(
            validation_labels,
            calibrated_validation_probabilities,
            calibrated.classes_,
        ),
        "synthetic_regression": hierarchy_regression_results(
            stage_one_vectorizer,
            stage_two_vectorizer,
            stage_one,
            stage_two,
            spec.candidate_id,
        ),
        "training_rows": len(fit_rows),
        "calibration_rows": len(calibration_rows),
        "validation_rows": len(validation_rows),
    }
    del (
        stage_one_vectorizer,
        stage_two_vectorizer,
        stage_one_fit_matrix,
        stage_two_fit_matrix,
        stage_one_calibration_matrix,
        stage_two_calibration_matrix,
        stage_one_validation_matrix,
        stage_two_validation_matrix,
        stage_one,
        stage_two,
        calibrated,
    )
    gc.collect()
    return result


def regression_results(
    vectorizer: Any, model: Any, candidate_id: str
) -> list[dict[str, Any]]:
    matrix = vectorizer.transform(
        [normalize_text(case[1]) for case in REGRESSION_CASES]
    )
    predictions = model.predict(matrix)
    probabilities = model.predict_proba(matrix)
    return [
        {
            "case_id": case[0],
            "expected_department": case[2],
            "predicted_department": str(predictions[index]),
            "raw_max_probability": float(np.max(probabilities[index])),
            "safe_at_0_60": bool(
                predictions[index] == case[2] or np.max(probabilities[index]) < 0.60
            ),
            "candidate_id": candidate_id,
        }
        for index, case in enumerate(REGRESSION_CASES)
    ]


def hierarchy_regression_results(
    stage_one_vectorizer: Any,
    stage_two_vectorizer: Any,
    stage_one: Any,
    stage_two: Any,
    candidate_id: str,
) -> list[dict[str, Any]]:
    texts = [normalize_text(case[1]) for case in REGRESSION_CASES]
    probabilities = _hierarchical_probabilities(
        stage_one,
        stage_two,
        stage_one_vectorizer.transform(texts),
        stage_two_vectorizer.transform(texts),
    )
    predictions = np.asarray(LABELS)[np.argmax(probabilities, axis=1)]
    return [
        {
            "case_id": case[0],
            "expected_department": case[2],
            "predicted_department": str(predictions[index]),
            "raw_max_probability": float(np.max(probabilities[index])),
            "safe_at_0_60": bool(
                predictions[index] == case[2] or np.max(probabilities[index]) < 0.60
            ),
            "candidate_id": candidate_id,
        }
        for index, case in enumerate(REGRESSION_CASES)
    ]


def _baseline_fraud_metrics() -> dict[str, float]:
    return {
        "false_positive_rate": 523 / 5524,
        "false_negative_rate": 2030 / 14148,
    }


def acceptance_gates(
    candidate: dict[str, Any], baseline: dict[str, Any]
) -> dict[str, Any]:
    baseline_metrics = baseline["validation_metrics"]
    metrics = candidate["validation_metrics"]
    baseline_fraud = _baseline_fraud_metrics()
    fraud = candidate["fraud_metrics"]
    short = {
        (row["minimum_characters"], row["maximum_characters"]): row
        for row in candidate["text_length_metrics"]
    }
    baseline_short = {
        (row["minimum_characters"], row["maximum_characters"]): row
        for row in baseline["text_length_metrics"]
    }
    checks: dict[str, bool] = {
        "macro_f1_at_least_0_70": metrics["macro_f1"] >= 0.70,
        "weighted_f1_not_below_phase2a_baseline": metrics["weighted_f1"]
        >= baseline_metrics["weighted_f1"],
        "per_class_f1_regression_within_0_03": all(
            metrics["per_class"][label]["f1"]
            >= baseline_metrics["per_class"][label]["f1"]
            - MAX_PER_CLASS_F1_REGRESSION
            for label in LABELS
        ),
        "transfer_recall_improves_by_0_05": metrics["per_class"][
            "transfer_payment"
        ]["recall"]
        >= baseline_metrics["per_class"]["transfer_payment"]["recall"] + 0.05,
        "transfer_as_account_below_171": metrics["transfer_as_account"] < 171,
        "account_as_transfer_guardrail": metrics["account_as_transfer"] <= 22,
        "fraud_false_positive_rate_guardrail": fraud["false_positive_rate"]
        <= baseline_fraud["false_positive_rate"] + 0.02,
        "fraud_false_negative_rate_guardrail": fraud["false_negative_rate"]
        <= baseline_fraud["false_negative_rate"] + 0.02,
        "loan_f1_protected": metrics["per_class"]["loan_credit"]["f1"]
        >= baseline_metrics["per_class"]["loan_credit"]["f1"] - 0.03,
        "loan_recall_protected": metrics["per_class"]["loan_credit"]["recall"]
        >= baseline_metrics["per_class"]["loan_credit"]["recall"] - 0.03,
        "short_0_100_safety": short[(0, 100)]["macro_f1"]
        >= baseline_short[(0, 100)]["macro_f1"] - 0.03,
        "short_101_300_safety": short[(101, 300)]["macro_f1"]
        >= baseline_short[(101, 300)]["macro_f1"] - 0.03,
        "short_0_100_improvement": short[(0, 100)]["macro_f1"]
        >= baseline_short[(0, 100)]["macro_f1"] + 0.02,
        "calibrated_ece_guardrail": candidate["calibrated_confidence"]["ece"]
        <= baseline["calibrated_confidence"]["ece"] + 0.01,
        "calibrated_brier_guardrail": candidate["calibrated_confidence"][
            "multiclass_brier"
        ]
        <= baseline["calibrated_confidence"]["multiclass_brier"] + 0.02,
        "calibrated_wrong_high_confidence_guardrail": all(
            candidate["calibrated_confidence"]["wrong_high_confidence"][str(threshold)]
            <= baseline["calibrated_confidence"]["wrong_high_confidence"][
                str(threshold)
            ]
            for threshold in CONFIDENCE_THRESHOLDS
        ),
        "synthetic_regression_safety": all(
            bool(row["safe_at_0_60"])
            for row in candidate["synthetic_regression"]
        ),
        "stable_synthetic_cases_preserved": all(
            row["predicted_department"] == row["expected_department"]
            for row in candidate["synthetic_regression"]
            if row["case_id"] in {"account_access", "card_payment", "fraud", "loan"}
        ),
    }
    values = {
        "macro_f1": metrics["macro_f1"],
        "weighted_f1": metrics["weighted_f1"],
        "transfer_recall": metrics["per_class"]["transfer_payment"]["recall"],
        "transfer_as_account": metrics["transfer_as_account"],
        "account_as_transfer": metrics["account_as_transfer"],
        "fraud_false_positive_rate": fraud["false_positive_rate"],
        "fraud_false_negative_rate": fraud["false_negative_rate"],
        "short_0_100_macro_f1": short[(0, 100)]["macro_f1"],
        "short_101_300_macro_f1": short[(101, 300)]["macro_f1"],
        "calibrated_ece": candidate["calibrated_confidence"]["ece"],
        "calibrated_brier": candidate["calibrated_confidence"]["multiclass_brier"],
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "values": values,
        "failed_checks": [name for name, passed in checks.items() if not passed],
    }


def _counts(rows: list[tuple[str, str]]) -> dict[str, int]:
    counter = Counter(label for _, label in rows)
    return {label: counter[label] for label in LABELS}


def _duplicate_audit(rows: list[tuple[str, str]]) -> dict[str, Any]:
    groups = _sorted_group_rows(rows)
    duplicate_groups = [labels for labels in groups.values() if len(labels) > 1]
    conflict_groups = [labels for labels in duplicate_groups if len(set(labels)) > 1]
    return {
        "rows": len(rows),
        "normalized_groups": len(groups),
        "exact_duplicate_groups": len(duplicate_groups),
        "exact_duplicate_extra_rows": sum(len(labels) - 1 for labels in duplicate_groups),
        "same_label_duplicate_groups": sum(
            len(set(labels)) == 1 for labels in duplicate_groups
        ),
        "conflicting_groups": len(conflict_groups),
        "conflicting_group_rows": sum(len(labels) for labels in conflict_groups),
        "maximum_group_size": max((len(labels) for labels in groups.values()), default=0),
    }


def _length_audit(rows: list[tuple[str, str]]) -> dict[str, Any]:
    output: dict[str, dict[str, int]] = {}
    for lower, upper in LENGTH_BUCKETS:
        key = f"{lower}_{upper if upper is not None else 'plus'}"
        output[key] = {label: 0 for label in LABELS}
    for text, label in rows:
        length = len(text)
        for lower, upper in LENGTH_BUCKETS:
            if length >= lower and (upper is None or length <= upper):
                key = f"{lower}_{upper if upper is not None else 'plus'}"
                output[key][label] += 1
                break
    return output


def _category_record() -> dict[str, Any]:
    return {
        "rows": 0,
        "label_counts": {label: 0 for label in LABELS},
        "mapping_method_counts": {
            "exact_product_issue": 0,
            "product_fallback": 0,
            "general_support": 0,
        },
    }


def _update_category(
    categories: dict[str, dict[str, Any]],
    value: str,
    label: str,
    method: str,
) -> None:
    record = categories.setdefault(value, _category_record())
    record["rows"] += 1
    record["label_counts"][label] += 1
    record["mapping_method_counts"][method] += 1


def _cleaned_hash_from_report(report: dict[str, Any]) -> str | None:
    candidates = (
        report.get("output", {}).get("sha256"),
        report.get("output", {}).get("file_sha256"),
        report.get("output", {}).get("csv_sha256"),
        report.get("artifacts", {}).get("cleaned_csv_sha256"),
    )
    return next((value for value in candidates if isinstance(value, str)), None)


def mapping_audit(
    cleaned_path: Path,
    cleaning_report_path: Path,
    mapping_path: Path,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    policy = load_mapping_policy(mapping_path)
    method_counts: Counter[str] = Counter()
    label_counts: Counter[str] = Counter()
    method_labels: dict[str, Counter[str]] = defaultdict(Counter)
    product_categories: dict[str, dict[str, Any]] = {}
    issue_categories: dict[str, dict[str, Any]] = {}
    missing_product = 0
    missing_issue = 0
    rows = 0
    chunks = 0
    reader = pd.read_csv(
        cleaned_path,
        usecols=list(INPUT_COLUMNS),
        dtype={"Product": "string", "Issue": "string"},
        chunksize=AUDIT_CHUNK_SIZE,
        keep_default_na=True,
    )
    for chunk in reader:
        chunks += 1
        for product, issue in zip(chunk["Product"], chunk["Issue"], strict=True):
            product_value = normalize_category(product)
            issue_value = normalize_category(issue)
            if product_value is None:
                missing_product += 1
            if issue_value is None:
                missing_issue += 1
            label, method = map_department(product, issue, policy)
            method_counts[method] += 1
            label_counts[label] += 1
            method_labels[method][label] += 1
            _update_category(
                product_categories,
                product_value or "<missing>",
                label,
                method,
            )
            _update_category(
                issue_categories,
                issue_value or "<missing>",
                label,
                method,
            )
            rows += 1
    expected_rows = int(manifest["output"]["rows"])
    if rows != expected_rows:
        raise ResearchError(
            f"mapping audit processed {rows} rows; expected {expected_rows}"
        )
    if dict(label_counts) != manifest["label_counts"]:
        raise ResearchError("mapping audit label counts differ from locked manifest")
    cleaning_report = json.loads(cleaning_report_path.read_text(encoding="utf-8"))
    return {
        "source_rows": rows,
        "chunks": chunks,
        "mapping_version": policy.mapping_version,
        "mapping_method_counts": dict(sorted(method_counts.items())),
        "mapping_method_label_counts": {
            method: {label: counts[label] for label in LABELS}
            for method, counts in sorted(method_labels.items())
        },
        "label_counts": {label: label_counts[label] for label in LABELS},
        "missing_product": missing_product,
        "missing_issue": missing_issue,
        "product_family": {
            key: product_categories[key] for key in sorted(product_categories)
        },
        "issue_family": {
            key: issue_categories[key] for key in sorted(issue_categories)
        },
        "hashes": {
            "mapped_dataset_sha256": EXPECTED_DATASET_SHA256,
            "mapping_policy_sha256": sha256_file(mapping_path),
            "cleaning_report_sha256": sha256_file(cleaning_report_path),
            "cleaned_source_sha256": _cleaned_hash_from_report(cleaning_report),
        },
        "privacy": {
            "contains_narratives": False,
            "contains_complaint_ids": False,
            "contains_row_level_predictions": False,
            "contains_raw_duplicate_pairs": False,
            "aggregate_only": True,
        },
    }


def _load_development(
    input_path: Path, manifest_path: Path
) -> tuple[dict[str, list[tuple[str, str]]], dict[str, Any], list[tuple[str, str]]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["output"]["sha256"] != EXPECTED_DATASET_SHA256:
        raise ResearchError("mapped dataset SHA-256 differs from Phase 2A lock")
    selection = BaselineConfig(
        input_path=input_path,
        input_manifest_path=manifest_path,
        metrics_path=input_path.with_suffix(".phase2b.unused.json"),
        model_path=input_path.with_suffix(".phase2b.unused.joblib"),
    )
    selected, source_counts, chunks = _select_rows(
        selection, int(manifest["output"]["rows"])
    )
    original = split_selected_rows(selected, selection)
    if len(original["train"]) != 140_781:
        raise ResearchError("locked original training partition did not reconstruct")
    development = split_development_rows(original["train"])
    expected = {"fit": 99_200, "calibration": 21_909, "validation": 19_672}
    if {name: len(rows) for name, rows in development.items()} != expected:
        raise ResearchError("Phase 2A development partition sizes changed")
    if dict(source_counts) != manifest["label_counts"]:
        raise ResearchError("source label counts differ from locked manifest")
    metadata = {
        "locked_reservoir_rows": len(selected),
        "source_rows": int(manifest["output"]["rows"]),
        "source_chunks": chunks,
        "original_training_rows": len(original["train"]),
        "development_partitions": {
            name: {"rows": len(rows), "label_counts": _counts(rows)}
            for name, rows in development.items()
        },
        "fit_after_fraud_cap": {
            "rows": len(balance_training_rows(
                development["fit"],
                BaselineConfig(
                    input_path=input_path,
                    input_manifest_path=manifest_path,
                    metrics_path=input_path.with_suffix(".phase2b.cap.json"),
                    model_path=input_path.with_suffix(".phase2b.cap.joblib"),
                    train_per_class_cap=30_000,
                    seed=DEVELOPMENT_SEED,
                ),
            )),
        },
        "source_label_counts": {label: source_counts[label] for label in LABELS},
        "locked_original_validation_rows": len(original["validation"]),
        "locked_held_out_test_rows": len(original["test"]),
        "development_seed": DEVELOPMENT_SEED,
        "locked_reservoir_seed": LOCKED_RESERVOIR_SEED,
    }
    del original, selected
    gc.collect()
    return development, metadata, manifest


def _fit_rows_for_spec(
    spec: CandidateSpec,
    base_fit_rows: list[tuple[str, str]],
    input_path: Path,
    manifest_path: Path,
) -> tuple[list[tuple[str, str]], dict[str, Any]]:
    config = BaselineConfig(
        input_path=input_path,
        input_manifest_path=manifest_path,
        metrics_path=input_path.with_suffix(".phase2b.fit.json"),
        model_path=input_path.with_suffix(".phase2b.fit.joblib"),
        train_per_class_cap=spec.fraud_cap,
        seed=DEVELOPMENT_SEED,
    )
    capped = balance_training_rows(
        base_fit_rows,
        config,
    )
    return _variant_rows(capped, spec.training_variant)


def _quality_audit(
    development: dict[str, list[tuple[str, str]]],
    base_fit_rows: list[tuple[str, str]],
) -> dict[str, Any]:
    exact_rows = exact_duplicate_variant(base_fit_rows)
    near_rows, near_summary = near_duplicate_variant(base_fit_rows)
    return {
        "original_training": _duplicate_audit(
            development["fit"]
            + development["calibration"]
            + development["validation"]
        ),
        "development_fit_before_cap": _duplicate_audit(development["fit"]),
        "fit_after_phase2a_cap": _duplicate_audit(base_fit_rows),
        "conflicting_group_count": len(conflicting_groups(development["fit"])),
        "exact_duplicate_sensitivity": {
            "fit_rows_before": len(base_fit_rows),
            "fit_rows_after": len(exact_rows),
            "rows_collapsed": len(base_fit_rows) - len(exact_rows),
            "conflicting_groups_retained": len(conflicting_groups(base_fit_rows)),
        },
        "near_duplicate_sensitivity": near_summary,
        "cross_partition_near_duplicate_sample": near_duplicate_sample(
            base_fit_rows, development["validation"]
        ),
        "short_text_counts_by_label": _length_audit(development["validation"]),
    }


def run_research(
    input_path: Path,
    manifest_path: Path,
    cleaned_path: Path,
    cleaning_report_path: Path,
    mapping_path: Path,
    output_path: Path,
    audit_output_path: Path,
) -> dict[str, Any]:
    if output_path.exists() or audit_output_path.exists():
        raise FileExistsError("refusing to overwrite existing Phase 2B artifacts")
    development, partition_metadata, manifest = _load_development(
        input_path, manifest_path
    )
    base_fit_rows = balance_training_rows(
        development["fit"],
        BaselineConfig(
            input_path=input_path,
            input_manifest_path=manifest_path,
            metrics_path=input_path.with_suffix(".phase2b.base.json"),
            model_path=input_path.with_suffix(".phase2b.base.joblib"),
            train_per_class_cap=30_000,
            seed=DEVELOPMENT_SEED,
        ),
    )
    calibration_rows = development["calibration"]
    validation_rows = development["validation"]
    quality_audit = _quality_audit(development, base_fit_rows)
    mapping_evidence = mapping_audit(
        cleaned_path, cleaning_report_path, mapping_path, manifest
    )
    audit = {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "status": "completed",
        "research_only": True,
        "partitions": partition_metadata,
        "mapping": mapping_evidence,
        "data_quality": quality_audit,
        "privacy": {
            "contains_narratives": False,
            "contains_complaint_ids": False,
            "contains_row_level_predictions": False,
            "contains_raw_duplicate_pairs": False,
            "aggregate_or_synthetic_only": True,
        },
    }
    candidates: list[dict[str, Any]] = []
    specs = candidate_specs()
    baseline_result: dict[str, Any] | None = None
    for spec in specs:
        fit_rows, variant_metadata = _fit_rows_for_spec(
            spec, base_fit_rows, input_path, manifest_path
        )
        if set(label for _, label in fit_rows) != set(LABELS):
            raise ResearchError(f"{spec.candidate_id} fit rows lost a department")
        if spec.hierarchical:
            result = _fit_hierarchical(
                spec, fit_rows, calibration_rows, validation_rows
            )
        else:
            result = _fit_flat(spec, fit_rows, calibration_rows, validation_rows)
        result["training_variant_metadata"] = variant_metadata
        if baseline_result is None:
            if spec.candidate_id != "mnb_0":
                raise ResearchError("MNB-0 must be the first Phase 2B candidate")
            baseline_result = result
        result["gate_results"] = acceptance_gates(result, baseline_result)
        candidates.append(result)
        del fit_rows, result
        gc.collect()
    if baseline_result is None:
        raise ResearchError("Phase 2B did not produce the MNB baseline")
    finalists = [row for row in candidates if row["gate_results"]["passed"]]
    finalist = max(
        finalists,
        key=lambda row: (
            row["validation_metrics"]["per_class"]["transfer_payment"]["recall"],
            row["validation_metrics"]["macro_f1"],
        ),
        default=None,
    )
    result = {
        "schema_version": SCHEMA_VERSION,
        "status": "completed",
        "research_only": True,
        "held_out_test_evaluated": False,
        "original_validation_evaluated": False,
        "finalist": None if finalist is None else finalist["candidate"]["candidate_id"],
        "seeds": {
            "locked_reservoir": LOCKED_RESERVOIR_SEED,
            "development": DEVELOPMENT_SEED,
        },
        "source": {
            "dataset_file": input_path.name,
            "dataset_sha256": EXPECTED_DATASET_SHA256,
            "rows": int(manifest["output"]["rows"]),
            "development_only": True,
        },
        "locked_partitions": partition_metadata,
        "matrix": {
            "predeclared_group_ids": list(CORE_MATRIX_IDS),
            "expanded_candidate_count": len(candidates),
            "no_cartesian_product_for_data_quality": True,
        },
        "candidates": candidates,
        "acceptance_gate_definition": {
            "max_per_class_f1_regression": MAX_PER_CLASS_F1_REGRESSION,
            "transfer_recall_absolute_gain": 0.05,
            "transfer_as_account_hard_limit": 171,
            "account_as_transfer_hard_limit": 22,
            "fraud_rate_guardrail_absolute_delta": 0.02,
            "short_0_100_required_gain": 0.02,
            "confidence_thresholds_diagnostic_only": list(CONFIDENCE_THRESHOLDS),
            "operational_threshold_unchanged": 0.60,
        },
        "privacy": {
            "contains_narratives": False,
            "contains_complaint_ids": False,
            "contains_row_level_predictions": False,
            "contains_raw_duplicate_pairs": False,
            "aggregate_or_synthetic_only": True,
        },
        "environment": {
            "python": platform.python_version(),
            "scikit_learn": sklearn.__version__,
            "joblib": joblib.__version__,
        },
        "limitations": [
            "Original validation and held-out test narratives were not transformed or predicted.",
            "Near-duplicate cross-partition evidence is a deterministic sample and is not exhaustive.",
            "Mapping labels are Product/Issue proxy labels rather than institutional ground truth.",
            "No SMOTE, embeddings, keyword overrides, threshold tuning, or mapping relabeling was used.",
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    audit_output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    audit_output_path.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--cleaned-source", type=Path, required=True)
    parser.add_argument("--cleaning-report", type=Path, required=True)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit-output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_research(
        args.input,
        args.manifest,
        args.cleaned_source,
        args.cleaning_report,
        args.mapping,
        args.output,
        args.audit_output,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "candidate_count": len(result["candidates"]),
                "finalist": result["finalist"],
                "held_out_test_evaluated": result["held_out_test_evaluated"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
