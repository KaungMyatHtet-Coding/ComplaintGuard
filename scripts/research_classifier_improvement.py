"""Phase 2A validation-only classifier research.

The runner reconstructs the locked Day 8/9 reservoir, retains only the original
natural-training partition, and creates new exact-duplicate-grouped development
partitions. It never transforms or predicts the original validation or test rows.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import sklearn
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.frozen import FrozenEstimator
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support
from sklearn.naive_bayes import ComplementNB, MultinomialNB
from sklearn.neighbors import NearestNeighbors
from sklearn.pipeline import FeatureUnion
from sklearn.svm import LinearSVC

try:
    from train_department_baseline import (
        LABELS,
        BaselineConfig,
        _select_rows,
        balance_training_rows,
        normalize_text,
        split_selected_rows,
    )
except ModuleNotFoundError:  # pragma: no cover - package-style test import
    from scripts.train_department_baseline import (
        LABELS,
        BaselineConfig,
        _select_rows,
        balance_training_rows,
        normalize_text,
        split_selected_rows,
    )

SCHEMA_VERSION = 1
RESEARCH_SEED = 20260810
MAX_PER_CLASS_F1_REGRESSION = 0.03
EXPECTED_DATASET_SHA256 = (
    "71a5ffda7914664a2b6803d92a6327bbe8e2438036e4420d3b30b95928241848"
)
LENGTH_BUCKETS = ((0, 100), (101, 300), (301, 1000), (1001, None))


class ResearchError(RuntimeError):
    """Raised when a research integrity contract cannot be satisfied."""


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    vectorizer: str
    classifier: str
    c: float | None = None
    alpha: float | None = None


CANDIDATES = (
    Candidate("word_mnb_baseline", "word", "MultinomialNB", alpha=0.5),
    Candidate("word_complement_nb", "word", "ComplementNB", alpha=0.5),
    Candidate("word_balanced_logreg", "word", "LogisticRegression", c=2.0),
    Candidate("word_char_balanced_logreg", "word_char", "LogisticRegression", c=2.0),
    Candidate("word_char_linear_svc", "word_char", "LinearSVC", c=1.0),
)

REGRESSION_CASES = (
    ("mobile_transfer_short", "Mobile transfer failed", "transfer_payment"),
    (
        "mobile_transfer_clear",
        "I transferred money through mobile banking. The amount was deducted from my account, but the recipient did not receive it.",
        "transfer_payment",
    ),
    ("account_access", "I cannot access my mobile banking account.", "account_support"),
    ("card_payment", "My debit card payment was declined at the store.", "card_atm"),
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
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def development_partition(normalized: str, seed: int = RESEARCH_SEED) -> str:
    """Assign an original-training duplicate group to fit/calibration/validation."""
    digest = hashlib.sha256(f"phase2a\0{seed}\0{normalized}".encode()).digest()
    fraction = int.from_bytes(digest[:8], "big") / 2**64
    if fraction < 0.70:
        return "fit"
    if fraction < 0.85:
        return "calibration"
    return "validation"


def split_development_rows(
    rows: list[tuple[str, str]], seed: int = RESEARCH_SEED
) -> dict[str, list[tuple[str, str]]]:
    partitions = {"fit": [], "calibration": [], "validation": []}
    seen: dict[str, str] = {}
    labels_by_text: dict[str, set[str]] = {}
    for text, label in rows:
        normalized = normalize_text(text)
        partition = development_partition(normalized, seed)
        if seen.setdefault(normalized, partition) != partition:
            raise ResearchError("exact normalized duplicate crossed development splits")
        labels_by_text.setdefault(normalized, set()).add(label)
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


def make_classifier(candidate: Candidate) -> Any:
    if candidate.classifier == "MultinomialNB":
        return MultinomialNB(alpha=candidate.alpha)
    if candidate.classifier == "ComplementNB":
        return ComplementNB(alpha=candidate.alpha)
    if candidate.classifier == "LogisticRegression":
        return LogisticRegression(
            C=candidate.c,
            class_weight="balanced",
            max_iter=2_000,
            random_state=RESEARCH_SEED,
            solver="lbfgs",
        )
    if candidate.classifier == "LinearSVC":
        return LinearSVC(
            C=candidate.c,
            class_weight="balanced",
            random_state=RESEARCH_SEED,
            max_iter=5_000,
        )
    raise ValueError(f"unknown classifier: {candidate.classifier}")


def metric_summary(y_true: list[str], y_pred: np.ndarray[Any, Any]) -> dict[str, Any]:
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
        for threshold in (0.6, 0.7, 0.8, 0.9)
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
        macro = precision_recall_fscore_support(
            truth[mask], y_pred[mask], labels=LABELS, average="macro", zero_division=0
        )
        rows.append(
            {
                "minimum_characters": lower,
                "maximum_characters": upper,
                "count": count,
                "accuracy": float(np.mean(truth[mask] == y_pred[mask])),
                "macro_f1": float(macro[2]),
            }
        )
    return rows


def regression_results(vectorizer: Any, model: Any) -> list[dict[str, Any]]:
    matrix = vectorizer.transform(
        [normalize_text(case[1]) for case in REGRESSION_CASES]
    )
    predictions = model.predict(matrix)
    probabilities = (
        model.predict_proba(matrix) if hasattr(model, "predict_proba") else None
    )
    decisions = (
        model.decision_function(matrix) if hasattr(model, "decision_function") else None
    )
    rows = []
    for index, (case_id, _text, expected) in enumerate(REGRESSION_CASES):
        row: dict[str, Any] = {
            "case_id": case_id,
            "expected_department": expected,
            "predicted_department": str(predictions[index]),
        }
        if probabilities is not None:
            row["raw_max_probability"] = float(np.max(probabilities[index]))
        elif decisions is not None:
            row["decision_score"] = float(np.max(decisions[index]))
        rows.append(row)
    return rows


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
        "limitation": "sampled risk estimate; not an exhaustive near-duplicate proof",
    }


def feature_analysis(vectorizer: Any, model: Any, complaint: str) -> dict[str, Any]:
    matrix = vectorizer.transform([normalize_text(complaint)])
    names = np.asarray(vectorizer.get_feature_names_out())
    account = int(np.where(model.classes_ == "account_support")[0][0])
    transfer = int(np.where(model.classes_ == "transfer_payment")[0][0])
    if hasattr(model, "feature_log_prob_"):
        weights = model.feature_log_prob_[account] - model.feature_log_prob_[transfer]
    elif hasattr(model, "coef_"):
        weights = model.coef_[account] - model.coef_[transfer]
    else:
        return {"available": False}
    contributions = matrix.multiply(weights).toarray()[0]
    nonzero = np.flatnonzero(contributions)
    toward_account = sorted(
        nonzero, key=lambda index: contributions[index], reverse=True
    )[:12]
    toward_transfer = sorted(nonzero, key=lambda index: contributions[index])[:12]
    return {
        "available": True,
        "toward_account_support": [
            {"feature": str(names[index]), "contribution": float(contributions[index])}
            for index in toward_account
            if contributions[index] > 0
        ],
        "toward_transfer_payment": [
            {"feature": str(names[index]), "contribution": float(contributions[index])}
            for index in toward_transfer
            if contributions[index] < 0
        ],
    }


def train_counts(rows: list[tuple[str, str]]) -> dict[str, int]:
    counts = Counter(label for _, label in rows)
    return {label: counts[label] for label in LABELS}


def conflicting_label_group_count(rows: list[tuple[str, str]]) -> int:
    labels_by_text: dict[str, set[str]] = {}
    for text, label in rows:
        labels_by_text.setdefault(text, set()).add(label)
    return sum(len(labels) > 1 for labels in labels_by_text.values())


def development_data_audit(
    fit_rows: list[tuple[str, str]], config: BaselineConfig
) -> dict[str, Any]:
    lengths: dict[str, dict[str, float | int]] = {}
    for label in LABELS:
        values = np.asarray(
            [
                len(text)
                for text, candidate_label in fit_rows
                if candidate_label == label
            ]
        )
        lengths[label] = {
            "count": len(values),
            "minimum": int(np.min(values)),
            "p10": float(np.percentile(values, 10)),
            "median": float(np.median(values)),
            "p90": float(np.percentile(values, 90)),
            "maximum": int(np.max(values)),
            "mean": float(np.mean(values)),
        }
    balanced = balance_training_rows(fit_rows, config)
    texts = [text for text, _ in balanced]
    labels = np.asarray([label for _, label in balanced])
    vectorizer = make_vectorizer("word")
    matrix = vectorizer.fit_transform(texts)
    names = np.asarray(vectorizer.get_feature_names_out())
    transfer_mean = np.asarray(
        matrix[labels == "transfer_payment"].mean(axis=0)
    ).ravel()
    account_mean = np.asarray(matrix[labels == "account_support"].mean(axis=0)).ravel()
    shared_score = np.minimum(transfer_mean, account_mean)
    difference = transfer_mean - account_mean

    def terms(
        indices: np.ndarray[Any, Any], values: np.ndarray[Any, Any]
    ) -> list[dict[str, Any]]:
        return [
            {"term": str(names[index]), "score": float(values[index])}
            for index in indices[:25]
            if values[index] > 0
        ]

    return {
        "text_length_characters_by_department": lengths,
        "term_method": "mean fit-only TF-IDF over the fit-only balanced word 1-2 gram matrix",
        "account_transfer_terms": {
            "shared": terms(np.argsort(shared_score)[::-1], shared_score),
            "toward_transfer_payment": terms(np.argsort(difference)[::-1], difference),
            "toward_account_support": terms(np.argsort(-difference)[::-1], -difference),
        },
    }


def select_finalist(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    baseline = next(
        row
        for row in candidates
        if row["candidate"]["candidate_id"] == "word_mnb_baseline"
    )
    baseline_metrics = baseline["validation_metrics"]
    eligible = []
    for row in candidates:
        metrics = row["validation_metrics"]
        regressions = {case["case_id"]: case for case in row["regression_suite"]}
        confirmed = regressions["mobile_transfer_clear"]
        confirmed_safe = confirmed["predicted_department"] == "transfer_payment" or (
            confirmed.get("raw_max_probability", 1.0) < 0.60
        )
        required_regressions = all(
            regressions[case_id]["predicted_department"] == expected
            for case_id, expected in (
                ("account_access", "account_support"),
                ("card_payment", "card_atm"),
            )
        )
        raw_confidence = row.get("raw_confidence")
        baseline_raw = baseline["raw_confidence"]
        wrong_high_decreased = raw_confidence is not None and all(
            raw_confidence["wrong_high_confidence"][threshold]
            < baseline_raw["wrong_high_confidence"][threshold]
            for threshold in ("0.6", "0.7", "0.8", "0.9")
        )
        no_unacceptable_class_regression = all(
            metrics["per_class"][label]["f1"]
            >= baseline_metrics["per_class"][label]["f1"] - MAX_PER_CLASS_F1_REGRESSION
            for label in LABELS
            if label != "transfer_payment"
        )
        if (
            metrics["per_class"]["transfer_payment"]["recall"]
            > baseline_metrics["per_class"]["transfer_payment"]["recall"] + 0.05
            and metrics["macro_f1"] >= baseline_metrics["macro_f1"] - 0.01
            and metrics["per_class"]["account_support"]["recall"] >= 0.70
            and metrics["transfer_as_account"] < baseline_metrics["transfer_as_account"]
            and required_regressions
            and confirmed_safe
            and wrong_high_decreased
            and no_unacceptable_class_regression
        ):
            eligible.append(row)
    return max(
        eligible,
        key=lambda row: (
            row["validation_metrics"]["per_class"]["transfer_payment"]["recall"],
            row["validation_metrics"]["macro_f1"],
        ),
        default=None,
    )


def run_research(
    input_path: Path, manifest_path: Path, output_path: Path
) -> dict[str, Any]:
    if output_path.exists():
        raise FileExistsError("refusing to overwrite existing research metrics")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_rows = manifest["output"]["rows"]
    if sha256_file(input_path) != EXPECTED_DATASET_SHA256:
        raise ResearchError("mapped dataset SHA-256 differs from the locked manifest")
    selection = BaselineConfig(
        input_path=input_path,
        input_manifest_path=manifest_path,
        metrics_path=output_path.with_suffix(".unused.json"),
        model_path=output_path.with_suffix(".unused.joblib"),
    )
    started = time.perf_counter()
    selected, source_counts, chunks = _select_rows(selection, expected_rows)
    original = split_selected_rows(selected, selection)
    if len(original["test"]) != 29_942 or len(original["validation"]) != 29_277:
        raise ResearchError("locked original partitions did not reconstruct exactly")
    development = split_development_rows(original["train"])
    fit_config = BaselineConfig(
        input_path=input_path,
        input_manifest_path=manifest_path,
        metrics_path=output_path.with_suffix(".unused.json"),
        model_path=output_path.with_suffix(".unused.joblib"),
        train_per_class_cap=30_000,
        seed=RESEARCH_SEED,
    )
    fit_rows = balance_training_rows(development["fit"], fit_config)
    fit_text = [text for text, _ in fit_rows]
    fit_labels = [label for _, label in fit_rows]
    calibration_text = [text for text, _ in development["calibration"]]
    calibration_labels = [label for _, label in development["calibration"]]
    validation_text = [text for text, _ in development["validation"]]
    validation_labels = [label for _, label in development["validation"]]
    candidates = []
    fitted: dict[str, tuple[Any, Any]] = {}
    for candidate in CANDIDATES:
        candidate_started = time.perf_counter()
        vectorizer = make_vectorizer(candidate.vectorizer)
        fit_matrix = vectorizer.fit_transform(fit_text)
        calibration_matrix = vectorizer.transform(calibration_text)
        validation_matrix = vectorizer.transform(validation_text)
        model = make_classifier(candidate)
        model.fit(fit_matrix, fit_labels)
        predictions = model.predict(validation_matrix)
        metrics = metric_summary(validation_labels, predictions)
        result: dict[str, Any] = {
            "candidate": asdict(candidate),
            "feature_count": int(fit_matrix.shape[1]),
            "validation_metrics": metrics,
            "text_length_metrics": length_metrics(
                validation_text, validation_labels, predictions
            ),
            "regression_suite": regression_results(vectorizer, model),
            "native_score_type": "probability"
            if hasattr(model, "predict_proba")
            else "decision_score",
            "runtime_seconds": time.perf_counter() - candidate_started,
        }
        if hasattr(model, "predict_proba"):
            result["raw_confidence"] = confidence_metrics(
                validation_labels,
                model.predict_proba(validation_matrix),
                model.classes_,
            )
        calibrated = CalibratedClassifierCV(FrozenEstimator(model), method="sigmoid")
        calibrated.fit(calibration_matrix, calibration_labels)
        result["sigmoid_calibration"] = confidence_metrics(
            validation_labels,
            calibrated.predict_proba(validation_matrix),
            calibrated.classes_,
        )
        candidates.append(result)
        fitted[candidate.candidate_id] = (vectorizer, model)
    strongest = select_finalist(candidates)
    confirmed = REGRESSION_CASES[1][1]
    explained_ids = ["word_mnb_baseline"]
    if strongest is not None:
        explained_ids.append(strongest["candidate"]["candidate_id"])
    result = {
        "schema_version": SCHEMA_VERSION,
        "status": "completed",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "research_only": True,
        "held_out_test_evaluated": False,
        "original_validation_evaluated": False,
        "seeds": {"locked_reservoir": 20260727, "development": RESEARCH_SEED},
        "environment": {
            "python": platform.python_version(),
            "scikit_learn": sklearn.__version__,
            "joblib": joblib.__version__,
        },
        "source": {
            "dataset_file": input_path.name,
            "dataset_sha256": EXPECTED_DATASET_SHA256,
            "rows": expected_rows,
            "source_label_counts": {label: source_counts[label] for label in LABELS},
            "chunks": chunks,
        },
        "locked_partitions": {
            name: {"rows": len(rows), "label_counts": train_counts(rows)}
            for name, rows in original.items()
        },
        "development_partitions": {
            **{
                name: {"rows": len(rows), "label_counts": train_counts(rows)}
                for name, rows in development.items()
            },
            "fit_after_training_only_cap": {
                "rows": len(fit_rows),
                "label_counts": train_counts(fit_rows),
            },
        },
        "development_data_audit": development_data_audit(
            development["fit"], fit_config
        ),
        "duplicate_controls": {
            "exact_normalized_cross_split": 0,
            "conflicting_normalized_label_groups": conflicting_label_group_count(
                original["train"]
            ),
            "normalization": "Unicode NFKC, casefold, whitespace collapse",
            "near_duplicate_sample": near_duplicate_sample(
                fit_rows, development["validation"]
            ),
        },
        "candidates": candidates,
        "recommended_finalist": None
        if strongest is None
        else strongest["candidate"]["candidate_id"],
        "feature_explanations": {
            candidate_id: feature_analysis(*fitted[candidate_id], confirmed)
            for candidate_id in explained_ids
        },
        "privacy": {
            "contains_narratives": False,
            "contains_complaint_ids": False,
            "aggregate_or_synthetic_only": True,
        },
        "runtime_seconds": time.perf_counter() - started,
        "limitations": [
            "The held-out test and original validation partitions were reconstructed only for counts and were never transformed or predicted.",
            "Near-duplicate analysis is sampled and cannot prove the absence of all semantic duplicates.",
            "CFPB Product/Issue proxy labels are not institutional ground truth.",
            "Validation-only calibration does not repair incorrect class boundaries.",
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = run_research(args.input, args.manifest, args.output)
    except (ResearchError, FileExistsError, ValueError, KeyError) as exc:
        print(f"research failed: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "status": result["status"],
                "recommended_finalist": result["recommended_finalist"],
                "runtime_seconds": result["runtime_seconds"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
