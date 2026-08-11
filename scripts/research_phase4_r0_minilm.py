"""Phase 4 R0: reproducible development-only MiniLM reference experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import sklearn
from sklearn.calibration import CalibratedClassifierCV
from sklearn.frozen import FrozenEstimator
from sklearn.linear_model import LogisticRegression

try:
    from research_phase3_embeddings import (
        atomic_write_json,
        configure_determinism,
    )
except ModuleNotFoundError:  # pragma: no cover
    from scripts.research_phase3_embeddings import (
        atomic_write_json,
        configure_determinism,
    )

try:
    from prepare_phase4_development_data import (
        ARTIFACT_COLUMNS,
        ARTIFACT_MANIFEST_RELATIVE_PATH,
        ARTIFACT_RELATIVE_PATH,
        EXPECTED_ARTIFACT_ROWS,
        PARTITION_COLUMN,
        SOURCE_RELATIVE_PATH,
    )
except ModuleNotFoundError:  # pragma: no cover
    from scripts.prepare_phase4_development_data import (
        ARTIFACT_COLUMNS,
        ARTIFACT_MANIFEST_RELATIVE_PATH,
        ARTIFACT_RELATIVE_PATH,
        EXPECTED_ARTIFACT_ROWS,
        PARTITION_COLUMN,
        SOURCE_RELATIVE_PATH,
    )


SCHEMA_VERSION = 1
EXPERIMENT_ID = "P4-R0"
MODEL_NAME = "all-MiniLM-L6-v2"
MODEL_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
DEVICE = "cpu"
DEVELOPMENT_SEED = 20260810
EMBEDDING_BATCH_SIZE = 256
TRAIN_PER_CLASS_CAP = 30_000
EXPECTED_CAPPED_FIT_ROWS = 56_675
EXPECTED_PARTITION_ROWS = {
    "fit": 99_200,
    "calibration": 21_909,
    "validation": 19_672,
}
OUTPUT_RELATIVE_PATH = Path("evaluation/research/phase4_r0_minilm_reproducibility.json")
PHASE2B_ARTIFACT = Path("evaluation/research/phase2b_classifier_experiments.json")
EMBEDDING_DIMENSION = 384
LOGISTIC_REGRESSION_SOLVER = "lbfgs"
LOGISTIC_REGRESSION_MAX_ITER = 2_000
LOGISTIC_REGRESSION_CLASS_WEIGHT = "balanced"
CALIBRATION_METHOD = "sigmoid"
MIN_AVAILABLE_MEMORY_BYTES = 7 * 1024**3


class ResearchError(RuntimeError):
    """Raised when P4-R0's locked research contract is not satisfied."""


class EmbeddingEncoder(Protocol):
    def encode(
        self,
        sentences: list[str],
        *,
        batch_size: int,
        convert_to_numpy: bool,
        normalize_embeddings: bool,
        show_progress_bar: bool,
    ) -> np.ndarray[Any, Any]: ...


@dataclass(frozen=True)
class P4R0Config:
    model_name: str = MODEL_NAME
    model_revision: str = MODEL_REVISION
    device: str = DEVICE
    batch_size: int = EMBEDDING_BATCH_SIZE
    normalize_embeddings: bool = True
    logistic_regression_c: float = 1.0
    logistic_regression_solver: str = LOGISTIC_REGRESSION_SOLVER
    logistic_regression_max_iter: int = LOGISTIC_REGRESSION_MAX_ITER
    logistic_regression_class_weight: str = LOGISTIC_REGRESSION_CLASS_WEIGHT
    calibration_method: str = CALIBRATION_METHOD
    train_per_class_cap: int = TRAIN_PER_CLASS_CAP
    seed: int = DEVELOPMENT_SEED


def validate_fixed_config(config: P4R0Config) -> None:
    if type(config) is not P4R0Config or config != P4R0Config():
        raise ResearchError(
            "P4-R0 configuration is immutable and must use locked defaults"
        )


def _phase2_dependencies() -> tuple[Any, ...]:
    try:
        from research_phase2b_classifier import (
            REGRESSION_CASES,
            acceptance_gates,
            confidence_metrics,
            fraud_metrics,
            length_metrics,
            metric_summary,
            normalize_text,
            split_development_rows,
        )
        from train_department_baseline import (
            INPUT_COLUMNS,
            LABEL_COLUMN,
            LABELS,
            TEXT_COLUMN,
            BaselineConfig,
            _partition_for,
            balance_training_rows,
        )
    except ModuleNotFoundError:  # pragma: no cover
        from scripts.research_phase2b_classifier import (
            REGRESSION_CASES,
            acceptance_gates,
            confidence_metrics,
            fraud_metrics,
            length_metrics,
            metric_summary,
            normalize_text,
            split_development_rows,
        )
        from scripts.train_department_baseline import (
            INPUT_COLUMNS,
            LABEL_COLUMN,
            LABELS,
            TEXT_COLUMN,
            BaselineConfig,
            _partition_for,
            balance_training_rows,
        )
    return (
        REGRESSION_CASES,
        acceptance_gates,
        confidence_metrics,
        fraud_metrics,
        length_metrics,
        metric_summary,
        normalize_text,
        split_development_rows,
        INPUT_COLUMNS,
        LABEL_COLUMN,
        TEXT_COLUMN,
        BaselineConfig,
        LABELS,
        _partition_for,
        balance_training_rows,
    )


def read_development_manifest(manifest_path: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifact = manifest.get("artifact", {})
    partitions = manifest.get("partitions", {})
    source = manifest.get("source_manifest_provenance", {})
    protection = manifest.get("protection", {})
    if (
        manifest.get("schema_version") != 1
        or manifest.get("status") != "completed"
        or artifact.get("file_name") != ARTIFACT_RELATIVE_PATH.name
        or artifact.get("rows") != EXPECTED_ARTIFACT_ROWS
        or not isinstance(artifact.get("sha256"), str)
        or len(artifact["sha256"]) != 64
        or {
            name: partitions.get(name, {}).get("rows")
            for name in EXPECTED_PARTITION_ROWS
        }
        != EXPECTED_PARTITION_ROWS
        or source.get("combined_checksum_verified_during_authorized_extraction")
        is not True
        or protection.get("original_validation_rows_excluded") is not True
        or protection.get("held_out_test_rows_excluded") is not True
        or protection.get("protected_rows_published") is not False
        or protection.get("manifest_aggregate_only") is not True
    ):
        raise ResearchError("development-only manifest does not satisfy the P4-R0 lock")
    return manifest


def verify_development_artifact(artifact_path: Path, manifest: dict[str, Any]) -> None:
    if _artifact_sha256(artifact_path) != manifest["artifact"]["sha256"]:
        raise ResearchError(
            "development-only artifact checksum does not match manifest"
        )


def load_development_artifact(
    artifact_path: Path, manifest: dict[str, Any], dependencies: tuple[Any, ...]
) -> tuple[dict[str, list[tuple[str, str]]], dict[str, Any]]:
    (
        _,
        _,
        _,
        _,
        _,
        _,
        _,
        _,
        input_columns,
        label_column,
        text_column,
        _,
        labels,
        _,
        _,
    ) = dependencies
    expected_columns = (PARTITION_COLUMN, *input_columns)
    if tuple(ARTIFACT_COLUMNS) != expected_columns:
        raise ResearchError("development artifact schema contract is inconsistent")
    try:
        import pandas as pd
    except ModuleNotFoundError as error:  # pragma: no cover
        raise ResearchError(
            "pandas is required to read the development-only artifact"
        ) from error
    header = pd.read_csv(artifact_path, nrows=0).columns.tolist()
    if tuple(header) != expected_columns:
        raise ResearchError(
            "development artifact schema differs from the locked contract"
        )
    development = {name: [] for name in EXPECTED_PARTITION_ROWS}
    reader = pd.read_csv(
        artifact_path,
        usecols=list(expected_columns),
        dtype={
            PARTITION_COLUMN: "string",
            text_column: "string",
            label_column: "string",
        },
        chunksize=100_000,
        keep_default_na=True,
    )
    for chunk in reader:
        if chunk.isna().any().any():
            raise ResearchError("development artifact contains a null value")
        for partition, text, label in zip(
            chunk[PARTITION_COLUMN].astype(str),
            chunk[text_column].astype(str),
            chunk[label_column].astype(str),
            strict=True,
        ):
            if partition not in development or not text.strip() or label not in labels:
                raise ResearchError("development artifact contains an invalid row")
            development[partition].append((text, label))
    counts = {name: len(rows) for name, rows in development.items()}
    if counts != EXPECTED_PARTITION_ROWS:
        raise ResearchError(
            "development artifact partition counts do not match the lock"
        )
    if sum(counts.values()) != manifest["artifact"]["rows"]:
        raise ResearchError("development artifact row total does not match manifest")
    metadata = {
        "development_artifact_rows": sum(counts.values()),
        "development_artifact_sha256": manifest["artifact"]["sha256"],
        "development_partitions": {name: {"rows": counts[name]} for name in counts},
        "protected_rows_materialized": False,
        "original_validation_rows_excluded": True,
        "held_out_test_rows_excluded": True,
        "source_provenance": manifest["source_manifest_provenance"],
    }
    return development, metadata


def validate_p4_r0_paths(
    input_path: Path,
    manifest_path: Path,
    output_path: Path,
    workspace_root: Path | None = None,
) -> None:
    root = (workspace_root or Path.cwd()).resolve()
    combined_source = (root / SOURCE_RELATIVE_PATH).resolve()
    if input_path.expanduser().resolve(strict=False) == combined_source:
        raise ResearchError("P4-R0 must not open or hash the combined source")
    expected_artifact = (root / ARTIFACT_RELATIVE_PATH).resolve()
    expected_manifest = (root / ARTIFACT_MANIFEST_RELATIVE_PATH).resolve()
    expected_output = (root / OUTPUT_RELATIVE_PATH).resolve()
    actual = tuple(
        path.expanduser().resolve(strict=False)
        for path in (input_path, manifest_path, output_path)
    )
    if actual != (expected_artifact, expected_manifest, expected_output):
        raise ResearchError(
            "P4-R0 requires canonical development artifact, manifest, and output paths"
        )


def available_memory_bytes() -> int:
    try:
        from ctypes import Structure, byref, c_ulong, c_ulonglong, sizeof, windll
    except ImportError as error:  # pragma: no cover
        raise ResearchError(
            "unable to query available memory on this platform"
        ) from error

    class MemoryStatus(Structure):
        _fields_ = [
            ("length", c_ulong),
            ("memory_load", c_ulong),
            ("total_physical", c_ulonglong),
            ("available_physical", c_ulonglong),
            ("total_page_file", c_ulonglong),
            ("available_page_file", c_ulonglong),
            ("total_virtual", c_ulonglong),
            ("available_virtual", c_ulonglong),
            ("available_extended_virtual", c_ulonglong),
        ]

    status = MemoryStatus()
    status.length = sizeof(MemoryStatus)
    if not windll.kernel32.GlobalMemoryStatusEx(byref(status)):
        raise ResearchError("unable to query available physical memory")
    return int(status.available_physical)


def conservative_memory_plan() -> dict[str, int]:
    fit_embedding_bytes = EXPECTED_CAPPED_FIT_ROWS * EMBEDDING_DIMENSION * 4
    plan = {
        "fit_embedding_and_sklearn_copy": fit_embedding_bytes * 2,
        "encoder_and_tokenization_batch": int(1.5 * 1024**3),
        "streamed_source_and_development_text": int(1.25 * 1024**3),
        "python_runtime_and_calibration": int(0.5 * 1024**3),
        "safety_headroom": int(2.5 * 1024**3),
    }
    estimated_peak = sum(plan.values())
    plan["estimated_peak_memory_bytes"] = estimated_peak
    plan["required_available_memory"] = MIN_AVAILABLE_MEMORY_BYTES
    if estimated_peak > MIN_AVAILABLE_MEMORY_BYTES:
        raise ResearchError(
            "locked memory policy is lower than its conservative estimate"
        )
    return plan


def require_memory_budget(
    available_bytes: int | None = None,
    required_bytes: int = MIN_AVAILABLE_MEMORY_BYTES,
    stage: str = "before loading",
) -> int:
    available = available_memory_bytes() if available_bytes is None else available_bytes
    if available < required_bytes:
        raise ResearchError(
            f"P4-R0 memory guard failed {stage}: requires at least "
            f"{required_bytes / 1024**3:.2f} GiB available RAM; found "
            f"{available / 1024**3:.2f} GiB"
        )
    return available


def cached_snapshot_path(cache_root: Path | None = None) -> Path:
    root = cache_root
    if root is None:
        root = Path(
            os.environ.get("HF_HUB_CACHE")
            or os.environ.get("HUGGINGFACE_HUB_CACHE")
            or Path.home() / ".cache" / "huggingface" / "hub"
        )
    snapshot = (
        root
        / "models--sentence-transformers--all-MiniLM-L6-v2"
        / "snapshots"
        / MODEL_REVISION
    )
    if not snapshot.is_dir():
        raise ResearchError(
            "locked MiniLM snapshot is not available in the local cache"
        )
    return snapshot


def snapshot_sha256(snapshot: Path) -> str:
    digest = hashlib.sha256()
    files = sorted(path for path in snapshot.rglob("*") if path.is_file())
    if not files:
        raise ResearchError("locked MiniLM snapshot contains no files")
    for path in files:
        digest.update(path.relative_to(snapshot).as_posix().encode("utf-8"))
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


DEFAULT_P4_R0_CONFIG = P4R0Config()


def load_encoder(
    config: P4R0Config = DEFAULT_P4_R0_CONFIG,
    factory: Callable[..., EmbeddingEncoder] | None = None,
    snapshot: Path | None = None,
) -> tuple[EmbeddingEncoder, dict[str, Any]]:
    validate_fixed_config(config)
    local_snapshot = snapshot or cached_snapshot_path()
    if local_snapshot.name != MODEL_REVISION:
        raise ResearchError(
            "resolved MiniLM snapshot does not match the locked revision"
        )
    if factory is None:
        try:
            import sentence_transformers
            import transformers
            from sentence_transformers import SentenceTransformer
        except ModuleNotFoundError as error:
            raise ResearchError(
                "sentence-transformers and transformers must be installed before P4-R0"
            ) from error
        factory = SentenceTransformer
        metadata = {
            "sentence_transformers_version": sentence_transformers.__version__,
            "transformers_version": transformers.__version__,
        }
    else:
        metadata = {
            "sentence_transformers_version": "mocked",
            "transformers_version": "mocked",
        }
    encoder = factory(
        MODEL_NAME,
        device=DEVICE,
        revision=MODEL_REVISION,
        local_files_only=True,
    )
    return encoder, {
        **metadata,
        "requested_revision": MODEL_REVISION,
        "resolved_revision": MODEL_REVISION,
        "snapshot_sha256": snapshot_sha256(local_snapshot),
    }


def encode_texts(
    encoder: EmbeddingEncoder,
    texts: list[str],
    config: P4R0Config,
) -> np.ndarray[Any, Any]:
    validate_fixed_config(config)
    matrix = np.asarray(
        encoder.encode(
            texts,
            batch_size=config.batch_size,
            convert_to_numpy=True,
            normalize_embeddings=config.normalize_embeddings,
            show_progress_bar=False,
        ),
        dtype=np.float32,
    )
    if matrix.ndim != 2 or matrix.shape[0] != len(texts):
        raise ResearchError("encoder returned an invalid embedding matrix")
    if not np.isfinite(matrix).all():
        raise ResearchError("encoder returned non-finite embedding values")
    return matrix


def train_classifier(
    fit_embeddings: np.ndarray[Any, Any],
    fit_labels: list[str],
    config: P4R0Config,
) -> LogisticRegression:
    validate_fixed_config(config)
    classifier = LogisticRegression(
        C=config.logistic_regression_c,
        class_weight=config.logistic_regression_class_weight,
        max_iter=config.logistic_regression_max_iter,
        random_state=config.seed,
        solver=config.logistic_regression_solver,
    )
    classifier.fit(fit_embeddings, fit_labels)
    return classifier


def fit_sampling_parameters(config: P4R0Config) -> dict[str, int]:
    validate_fixed_config(config)
    return {
        "train_per_class_cap": config.train_per_class_cap,
        "seed": config.seed,
    }


def calibrate_classifier(
    classifier: LogisticRegression,
    calibration_embeddings: np.ndarray[Any, Any],
    calibration_labels: list[str],
    config: P4R0Config = DEFAULT_P4_R0_CONFIG,
) -> CalibratedClassifierCV:
    validate_fixed_config(config)
    calibrated = CalibratedClassifierCV(
        FrozenEstimator(classifier), method=config.calibration_method
    )
    calibrated.fit(calibration_embeddings, calibration_labels)
    return calibrated


def validate_locked_contract(
    partition_metadata: dict[str, Any], manifest: dict[str, Any]
) -> None:
    if manifest.get("artifact", {}).get("rows") != EXPECTED_ARTIFACT_ROWS:
        raise ResearchError(
            "development artifact row count does not match the locked contract"
        )
    partitions = partition_metadata.get("development_partitions", {})
    for partition, expected_rows in EXPECTED_PARTITION_ROWS.items():
        if partitions.get(partition, {}).get("rows") != expected_rows:
            raise ResearchError(f"locked {partition} row count does not match")
    if partition_metadata.get("original_validation_rows_excluded") is not True:
        raise ResearchError("original validation protection contract does not match")
    if partition_metadata.get("held_out_test_rows_excluded") is not True:
        raise ResearchError("held-out test protection contract does not match")


def validate_capped_fit_rows(fit_rows: list[tuple[str, str]]) -> None:
    if len(fit_rows) != EXPECTED_CAPPED_FIT_ROWS:
        raise ResearchError("locked capped fit row count does not match")


def validate_phase2b_baseline_path(
    path: Path, workspace_root: Path | None = None
) -> None:
    root = (workspace_root or Path.cwd()).resolve()
    expected = (root / PHASE2B_ARTIFACT).resolve()
    if path.expanduser().resolve(strict=False) != expected:
        raise ResearchError("P4-R0 requires the canonical Phase 2B baseline artifact")


def load_phase2b_baseline(path: Path = PHASE2B_ARTIFACT) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        payload.get("status") != "completed"
        or payload.get("held_out_test_evaluated") is not False
        or payload.get("original_validation_evaluated") is not False
    ):
        raise ResearchError(
            "Phase 2B baseline artifact does not satisfy protection contract"
        )
    for candidate in payload.get("candidates", []):
        if candidate.get("candidate", {}).get("candidate_id") == "mnb_0":
            return candidate
    raise ResearchError("Phase 2B MNB baseline is unavailable")


def synthetic_safety_summary(
    encoder: EmbeddingEncoder,
    classifier: Any,
    config: P4R0Config,
    regression_cases: tuple[tuple[str, str, str], ...],
    normalize: Callable[[str], str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    texts = [normalize(case[1]) for case in regression_cases]
    embeddings = encode_texts(encoder, texts, config)
    probabilities = classifier.predict_proba(embeddings)
    predictions = classifier.classes_[np.argmax(probabilities, axis=1)]
    details = [
        {
            "case_id": case[0],
            "expected_department": case[2],
            "predicted_department": str(predictions[index]),
            "raw_max_probability": float(np.max(probabilities[index])),
            "safe_at_0_60": bool(
                predictions[index] == case[2] or np.max(probabilities[index]) < 0.60
            ),
            "candidate_id": EXPERIMENT_ID,
        }
        for index, case in enumerate(regression_cases)
    ]
    stable_case_ids = {"account_access", "card_payment", "fraud", "loan"}
    summary = {
        "case_count": len(details),
        "safe_case_count": sum(bool(row["safe_at_0_60"]) for row in details),
        "unsafe_case_count": sum(not bool(row["safe_at_0_60"]) for row in details),
        "stable_case_count": sum(row["case_id"] in stable_case_ids for row in details),
        "stable_case_failures": sum(
            row["case_id"] in stable_case_ids
            and row["predicted_department"] != row["expected_department"]
            for row in details
        ),
    }
    del embeddings, probabilities, predictions
    return details, summary


def short_text_summary(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    wanted = {(0, 100): "0_100", (101, 300): "101_300"}
    summary = {
        wanted[(row["minimum_characters"], row["maximum_characters"])]: row
        for row in rows
        if (row["minimum_characters"], row["maximum_characters"]) in wanted
    }
    if set(summary) != set(wanted.values()):
        raise ResearchError("required short-text buckets are unavailable")
    return summary


def privacy_metadata() -> dict[str, bool]:
    return {
        "contains_narratives": False,
        "contains_complaint_ids": False,
        "contains_embeddings": False,
        "contains_row_level_predictions": False,
        "aggregate_only": True,
    }


FORBIDDEN_AGGREGATE_OUTPUT_KEYS = {
    "case_id",
    "expected_department",
    "predicted_department",
    "raw_max_probability",
    "probability",
    "probabilities",
    "prediction",
    "predictions",
    "narrative",
    "narratives",
    "complaint_id",
    "complaint_ids",
    "embedding",
    "embeddings",
    "row_id",
    "row_ids",
}


def assert_aggregate_only_payload(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in FORBIDDEN_AGGREGATE_OUTPUT_KEYS:
                raise ResearchError(f"aggregate output contains prohibited key: {key}")
            assert_aggregate_only_payload(child)
    elif isinstance(value, list):
        for child in value:
            assert_aggregate_only_payload(child)


def publish_aggregate_result(output_path: Path, result: dict[str, Any]) -> None:
    assert_aggregate_only_payload(result)
    atomic_write_json(output_path, result)


def evaluate_phase2b_gates(
    candidate: dict[str, Any],
    baseline: dict[str, Any],
    gate_function: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    return gate_function(candidate, baseline)


def _artifact_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_p4_r0(
    input_path: Path,
    manifest_path: Path,
    output_path: Path,
    phase2b_artifact: Path = PHASE2B_ARTIFACT,
    config: P4R0Config = DEFAULT_P4_R0_CONFIG,
) -> dict[str, Any]:
    validate_fixed_config(config)
    validate_p4_r0_paths(input_path, manifest_path, output_path)
    validate_phase2b_baseline_path(phase2b_artifact)
    if output_path.exists():
        raise FileExistsError("refusing to overwrite an existing P4-R0 artifact")
    available_memory = require_memory_budget(stage="before reading manifest")
    manifest = read_development_manifest(manifest_path)
    verify_development_artifact(input_path, manifest)
    (
        regression_cases,
        acceptance_gates,
        confidence_metrics,
        fraud_metrics,
        length_metrics,
        metric_summary,
        normalize_text,
        split_development_rows,
        input_columns,
        label_column,
        text_column,
        BaselineConfig,
        labels,
        partition_for,
        balance_training_rows,
    ) = _phase2_dependencies()
    dependencies = (
        regression_cases,
        acceptance_gates,
        confidence_metrics,
        fraud_metrics,
        length_metrics,
        metric_summary,
        normalize_text,
        split_development_rows,
        input_columns,
        label_column,
        text_column,
        BaselineConfig,
        labels,
        partition_for,
        balance_training_rows,
    )
    require_memory_budget(stage="before loading development-only artifact")
    development, partition_metadata = load_development_artifact(
        input_path, manifest, dependencies
    )
    validate_locked_contract(partition_metadata, manifest)
    baseline = load_phase2b_baseline(phase2b_artifact)
    fit_rows = balance_training_rows(
        development["fit"],
        BaselineConfig(
            input_path=input_path,
            input_manifest_path=manifest_path,
            metrics_path=output_path.with_suffix(".unused.json"),
            model_path=output_path.with_suffix(".unused.joblib"),
            **fit_sampling_parameters(config),
        ),
    )
    validate_capped_fit_rows(fit_rows)
    partition_metadata["fit_after_fraud_cap"] = {"rows": len(fit_rows)}
    determinism = configure_determinism(config.seed)
    require_memory_budget(stage="before loading local MiniLM")
    encoder, encoder_metadata = load_encoder(config)
    fit_text = [text for text, _ in fit_rows]
    fit_labels = [label for _, label in fit_rows]
    require_memory_budget(stage="before fit embedding allocation")
    fit_embeddings = encode_texts(encoder, fit_text, config)
    embedding_dimension = int(fit_embeddings.shape[1])
    classifier = train_classifier(fit_embeddings, fit_labels, config)
    del fit_embeddings, fit_text, fit_labels, fit_rows, development["fit"]

    calibration_text = [text for text, _ in development["calibration"]]
    calibration_labels = [label for _, label in development["calibration"]]
    require_memory_budget(stage="before calibration embedding allocation")
    calibration_embeddings = encode_texts(encoder, calibration_text, config)
    calibrated = calibrate_classifier(
        classifier, calibration_embeddings, calibration_labels, config
    )
    del (
        calibration_embeddings,
        calibration_text,
        calibration_labels,
        development["calibration"],
    )

    validation_text = [text for text, _ in development["validation"]]
    validation_labels = [label for _, label in development["validation"]]
    require_memory_budget(stage="before validation embedding allocation")
    validation_embeddings = encode_texts(encoder, validation_text, config)
    predictions = classifier.predict(validation_embeddings)
    raw_probabilities = classifier.predict_proba(validation_embeddings)
    calibrated_probabilities = calibrated.predict_proba(validation_embeddings)
    length_rows = length_metrics(validation_text, validation_labels, predictions)
    synthetic_details, synthetic_summary = synthetic_safety_summary(
        encoder, classifier, config, tuple(regression_cases), normalize_text
    )
    candidate = {
        "validation_metrics": metric_summary(validation_labels, predictions),
        "text_length_metrics": length_rows,
        "fraud_metrics": fraud_metrics(validation_labels, predictions),
        "raw_confidence": confidence_metrics(
            validation_labels, raw_probabilities, classifier.classes_
        ),
        "calibrated_confidence": confidence_metrics(
            validation_labels, calibrated_probabilities, calibrated.classes_
        ),
        "synthetic_regression": synthetic_details,
        "training_rows": EXPECTED_CAPPED_FIT_ROWS,
        "calibration_rows": EXPECTED_PARTITION_ROWS["calibration"],
        "validation_rows": EXPECTED_PARTITION_ROWS["validation"],
        "boundary_overlap": {"status": "not_applicable_dense_embeddings_only"},
    }
    candidate["gate_results"] = evaluate_phase2b_gates(
        candidate, baseline, acceptance_gates
    )
    output_candidate = dict(candidate)
    del output_candidate["synthetic_regression"]
    result = {
        "schema_version": SCHEMA_VERSION,
        "status": "completed",
        "experiment_id": EXPERIMENT_ID,
        "research_only": True,
        "held_out_test_evaluated": False,
        "original_validation_evaluated": False,
        "finalist": False,
        "source": {
            "development_artifact_file": input_path.name,
            "development_artifact_sha256": manifest["artifact"]["sha256"],
            "rows": int(manifest["artifact"]["rows"]),
            "combined_source_provenance": manifest["source_manifest_provenance"],
            "language": "existing English source narratives; no translation step applied",
        },
        "locked_partitions": partition_metadata,
        "configuration": {
            **asdict(config),
            "embedding_dimension": embedding_dimension,
            **encoder_metadata,
        },
        "memory_strategy": {
            "conservative_peak_memory_bytes": MIN_AVAILABLE_MEMORY_BYTES,
            "conservative_peak_memory_plan": conservative_memory_plan(),
            "minimum_available_memory_bytes": MIN_AVAILABLE_MEMORY_BYTES,
            "available_memory_bytes_before_loading": available_memory,
            "embedding_partitions_processed_sequentially": True,
            "embeddings_persisted": False,
        },
        "phase2b_baseline": {
            "file": phase2b_artifact.name,
            "sha256": _artifact_sha256(phase2b_artifact),
            "candidate_id": "mnb_0",
        },
        **output_candidate,
        "synthetic_safety": synthetic_summary,
        "short_text_summary": short_text_summary(length_rows),
        "privacy": privacy_metadata(),
        "limitations": [
            "This is a development-only reproducibility experiment.",
            "Original validation and held-out test partitions were not encoded or predicted.",
            "No threshold, routing, mapping, Firebase, or production model change is authorized.",
        ],
        "environment": {
            "python": platform.python_version(),
            "scikit_learn": sklearn.__version__,
            "determinism": determinism,
        },
    }
    del validation_embeddings, predictions, raw_probabilities, calibrated_probabilities
    del synthetic_details
    publish_aggregate_result(output_path, result)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=OUTPUT_RELATIVE_PATH)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = run_p4_r0(args.input, args.manifest, args.output)
    except (ResearchError, FileExistsError, KeyError, ValueError) as error:
        print(f"P4-R0 failed: {error}")
        return 1
    print(
        json.dumps(
            {
                "status": result["status"],
                "macro_f1": result["validation_metrics"]["macro_f1"],
                "gates_passed": result["gate_results"]["passed"],
                "held_out_test_evaluated": result["held_out_test_evaluated"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
