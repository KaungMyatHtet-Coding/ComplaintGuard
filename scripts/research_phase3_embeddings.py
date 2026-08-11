"""Phase 3 development-only dense embedding research with all-MiniLM-L6-v2."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import random
import re
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

import joblib
import numpy as np
import sklearn
from sklearn.calibration import CalibratedClassifierCV
from sklearn.frozen import FrozenEstimator
from sklearn.linear_model import LogisticRegression

SCHEMA_VERSION = 2
MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_BATCH_SIZE = 256
TRAIN_PER_CLASS_CAP = 30_000
DEVELOPMENT_SEED = 20260810
PROTECTED_PATH_PATTERN = re.compile(
    r"(?:^|[^a-z0-9])(?:held[\W_]*out|original[\W_]*validation)(?:[^a-z0-9]|$)",
    re.IGNORECASE,
)


class ResearchError(RuntimeError):
    """Raised when the Phase 3 embedding integrity contract is not satisfied."""


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
class EmbeddingConfig:
    model_name: str = MODEL_NAME
    model_revision: str | None = None
    batch_size: int = EMBEDDING_BATCH_SIZE
    normalize_embeddings: bool = True
    logistic_regression_c: float = 1.0
    train_per_class_cap: int = TRAIN_PER_CLASS_CAP


def _phase2_dependencies() -> tuple[Any, ...]:
    """Import development-only dependencies lazily so lightweight tests stay offline."""
    try:
        from research_phase2b_classifier import (
            EXPECTED_DATASET_SHA256,
            _load_development,
            confidence_metrics,
            length_metrics,
            metric_summary,
        )
        from train_department_baseline import BaselineConfig, balance_training_rows
    except ModuleNotFoundError:  # pragma: no cover - package import path
        from scripts.research_phase2b_classifier import (
            EXPECTED_DATASET_SHA256,
            _load_development,
            confidence_metrics,
            length_metrics,
            metric_summary,
        )
        from scripts.train_department_baseline import (
            BaselineConfig,
            balance_training_rows,
        )
    return (
        EXPECTED_DATASET_SHA256,
        _load_development,
        confidence_metrics,
        length_metrics,
        metric_summary,
        BaselineConfig,
        balance_training_rows,
    )


def validate_research_paths(
    input_path: Path, manifest_path: Path, output_path: Path
) -> None:
    """Reject protected evaluation sources before any file is opened."""
    resolved = [
        path.expanduser().resolve(strict=False)
        for path in (input_path, manifest_path, output_path)
    ]
    if len(set(resolved)) != len(resolved):
        raise ResearchError("input, manifest, and output paths must be distinct")
    for role, path in zip(("input", "manifest", "output"), resolved, strict=True):
        if PROTECTED_PATH_PATTERN.search(path.as_posix()):
            raise ResearchError(
                f"{role} path refers to a protected evaluation partition"
            )


def configure_determinism(seed: int = DEVELOPMENT_SEED) -> dict[str, Any]:
    random.seed(seed)
    np.random.seed(seed)
    metadata: dict[str, Any] = {
        "python_random_seed": seed,
        "numpy_random_seed": seed,
        "torch_seed": None,
        "torch_deterministic_algorithms": None,
    }
    try:
        import torch
    except ModuleNotFoundError:
        return metadata
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)
    metadata.update(
        torch_seed=seed,
        torch_deterministic_algorithms=True,
        torch_version=torch.__version__,
    )
    return metadata


def _hash_model_snapshot(snapshot_path: Path) -> str | None:
    """Hash regular files in a resolved local model snapshot, when available."""
    if not snapshot_path.is_dir():
        return None
    digest = hashlib.sha256()
    files = sorted(path for path in snapshot_path.rglob("*") if path.is_file())
    if not files:
        return None
    for path in files:
        digest.update(path.relative_to(snapshot_path).as_posix().encode("utf-8"))
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _encoder_provenance(encoder: Any, requested_revision: str | None) -> dict[str, Any]:
    first_module = next(iter(getattr(encoder, "_modules", {}).values()), None)
    auto_model = getattr(first_module, "auto_model", None)
    name_or_path = getattr(getattr(auto_model, "config", None), "_name_or_path", None)
    snapshot = Path(name_or_path).resolve(strict=False) if name_or_path else None
    resolved_revision = None
    if snapshot is not None and snapshot.parent.name == "snapshots":
        resolved_revision = snapshot.name
    return {
        "requested_revision": requested_revision,
        "resolved_revision": resolved_revision,
        "snapshot_sha256": _hash_model_snapshot(snapshot) if snapshot else None,
    }


DEFAULT_EMBEDDING_CONFIG = EmbeddingConfig()


def load_encoder(
    config: EmbeddingConfig = DEFAULT_EMBEDDING_CONFIG,
) -> tuple[EmbeddingEncoder, dict[str, Any]]:
    try:
        import sentence_transformers
        from sentence_transformers import SentenceTransformer
    except ModuleNotFoundError as error:
        raise ResearchError(
            "sentence-transformers is required; install requirements-data.txt first"
        ) from error
    try:
        import transformers
    except (
        ModuleNotFoundError
    ):  # pragma: no cover - sentence-transformers normally supplies it
        transformers = None
    encoder = SentenceTransformer(
        config.model_name,
        device="cpu",
        revision=config.model_revision,
    )
    return encoder, {
        "sentence_transformers_version": sentence_transformers.__version__,
        "transformers_version": getattr(transformers, "__version__", None),
        **_encoder_provenance(encoder, config.model_revision),
    }


def atomic_write_json(output_path: Path, result: dict[str, Any]) -> None:
    """Atomically publish JSON without replacing an existing destination."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            json.dump(result, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary_path, output_path)
    except FileExistsError as error:
        raise FileExistsError(
            "refusing to overwrite an existing Phase 3 artifact"
        ) from error
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def encode_texts(
    encoder: EmbeddingEncoder,
    texts: list[str],
    config: EmbeddingConfig,
) -> np.ndarray[Any, Any]:
    embeddings = encoder.encode(
        texts,
        batch_size=config.batch_size,
        convert_to_numpy=True,
        normalize_embeddings=config.normalize_embeddings,
        show_progress_bar=False,
    )
    matrix = np.asarray(embeddings, dtype=np.float32)
    if matrix.ndim != 2 or matrix.shape[0] != len(texts):
        raise ResearchError("encoder returned an invalid embedding matrix")
    if not np.isfinite(matrix).all():
        raise ResearchError("encoder returned non-finite embedding values")
    return matrix


def short_text_summary(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    wanted = {(0, 100): "0_100", (101, 300): "101_300"}
    summary: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = (row["minimum_characters"], row["maximum_characters"])
        if key in wanted:
            summary[wanted[key]] = row
    if set(summary) != set(wanted.values()):
        raise ResearchError("required short-text buckets are unavailable")
    return summary


def train_embedding_classifier(
    fit_embeddings: np.ndarray[Any, Any],
    fit_labels: list[str],
    config: EmbeddingConfig,
) -> LogisticRegression:
    classifier = LogisticRegression(
        C=config.logistic_regression_c,
        class_weight="balanced",
        max_iter=2_000,
        random_state=DEVELOPMENT_SEED,
        solver="lbfgs",
    )
    classifier.fit(fit_embeddings, fit_labels)
    return classifier


def run_research(
    input_path: Path,
    manifest_path: Path,
    output_path: Path,
    config: EmbeddingConfig = DEFAULT_EMBEDDING_CONFIG,
) -> dict[str, Any]:
    validate_research_paths(input_path, manifest_path, output_path)
    if output_path.exists():
        raise FileExistsError("refusing to overwrite an existing Phase 3 artifact")
    (
        expected_dataset_sha256,
        load_development,
        confidence_metrics,
        length_metrics,
        metric_summary,
        BaselineConfig,
        balance_training_rows,
    ) = _phase2_dependencies()
    development, partition_metadata, manifest = load_development(
        input_path, manifest_path
    )
    fit_rows = balance_training_rows(
        development["fit"],
        BaselineConfig(
            input_path=input_path,
            input_manifest_path=manifest_path,
            metrics_path=output_path.with_suffix(".unused.json"),
            model_path=output_path.with_suffix(".unused.joblib"),
            train_per_class_cap=config.train_per_class_cap,
            seed=DEVELOPMENT_SEED,
        ),
    )
    if len(fit_rows) != 56_675:
        raise ResearchError("Phase 2B capped fit rows did not reconstruct exactly")
    fit_text = [text for text, _ in fit_rows]
    fit_labels = [label for _, label in fit_rows]
    calibration_text = [text for text, _ in development["calibration"]]
    calibration_labels = [label for _, label in development["calibration"]]
    validation_text = [text for text, _ in development["validation"]]
    validation_labels = [label for _, label in development["validation"]]
    determinism = configure_determinism()
    encoder, encoder_metadata = load_encoder(config)
    fit_embeddings = encode_texts(encoder, fit_text, config)
    calibration_embeddings = encode_texts(encoder, calibration_text, config)
    validation_embeddings = encode_texts(encoder, validation_text, config)
    classifier = train_embedding_classifier(fit_embeddings, fit_labels, config)
    predictions = classifier.predict(validation_embeddings)
    raw_probabilities = classifier.predict_proba(validation_embeddings)
    calibrated = CalibratedClassifierCV(FrozenEstimator(classifier), method="sigmoid")
    calibrated.fit(calibration_embeddings, calibration_labels)
    calibrated_probabilities = calibrated.predict_proba(validation_embeddings)
    metric_rows = length_metrics(validation_text, validation_labels, predictions)
    result = {
        "schema_version": SCHEMA_VERSION,
        "status": "completed",
        "research_only": True,
        "held_out_test_evaluated": False,
        "original_validation_evaluated": False,
        "source": {
            "dataset_file": input_path.name,
            "dataset_sha256": expected_dataset_sha256,
            "rows": int(manifest["output"]["rows"]),
            "language": "existing English source narratives; no translation step applied",
        },
        "locked_partitions": partition_metadata,
        "embedding_config": {
            **asdict(config),
            "device": "cpu",
            "embedding_dimension": int(fit_embeddings.shape[1]),
            **encoder_metadata,
        },
        "validation_metrics": metric_summary(validation_labels, predictions),
        "text_length_metrics": metric_rows,
        "short_text_summary": short_text_summary(metric_rows),
        "raw_confidence": confidence_metrics(
            validation_labels, raw_probabilities, classifier.classes_
        ),
        "calibrated_confidence": confidence_metrics(
            validation_labels, calibrated_probabilities, calibrated.classes_
        ),
        "privacy": {
            "contains_narratives": False,
            "contains_complaint_ids": False,
            "contains_row_level_predictions": False,
            "aggregate_only": True,
        },
        "limitations": [
            "The sentence encoder is pretrained but was not fine-tuned on this corpus.",
            "Original validation and held-out test partitions were not vectorized or predicted.",
            "The source development narratives are English; this experiment does not claim Myanmar routing quality.",
        ],
        "environment": {
            "python": platform.python_version(),
            "scikit_learn": sklearn.__version__,
            "joblib": joblib.__version__,
            "determinism": determinism,
        },
    }
    atomic_write_json(output_path, result)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model-name", default=MODEL_NAME)
    parser.add_argument("--model-revision")
    parser.add_argument("--batch-size", type=int, default=EMBEDDING_BATCH_SIZE)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = EmbeddingConfig(
        model_name=args.model_name,
        model_revision=args.model_revision,
        batch_size=args.batch_size,
    )
    try:
        result = run_research(args.input, args.manifest, args.output, config)
    except (ResearchError, FileExistsError, KeyError, ValueError) as error:
        print(f"research failed: {error}")
        return 1
    summary = result["short_text_summary"]
    print(
        json.dumps(
            {
                "status": result["status"],
                "macro_f1": result["validation_metrics"]["macro_f1"],
                "short_0_100_macro_f1": summary["0_100"]["macro_f1"],
                "short_101_300_macro_f1": summary["101_300"]["macro_f1"],
                "held_out_test_evaluated": result["held_out_test_evaluated"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
