from __future__ import annotations

import hashlib
import inspect
import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import research_phase4_r0_minilm as p4
from prepare_phase4_development_data import (
    ARTIFACT_MANIFEST_RELATIVE_PATH,
    ARTIFACT_RELATIVE_PATH,
    EXPECTED_ARTIFACT_ROWS,
    EXPECTED_PARTITION_ROWS,
    PARTITION_COLUMN,
    SOURCE_RELATIVE_PATH,
)
from research_phase2b_classifier import LABELS, acceptance_gates
from research_phase4_r0_minilm import (
    CALIBRATION_METHOD,
    DEVICE,
    LOGISTIC_REGRESSION_CLASS_WEIGHT,
    LOGISTIC_REGRESSION_MAX_ITER,
    LOGISTIC_REGRESSION_SOLVER,
    MIN_AVAILABLE_MEMORY_BYTES,
    MODEL_NAME,
    MODEL_REVISION,
    OUTPUT_RELATIVE_PATH,
    P4R0Config,
    ResearchError,
    assert_aggregate_only_payload,
    atomic_write_json,
    calibrate_classifier,
    conservative_memory_plan,
    encode_texts,
    evaluate_phase2b_gates,
    fit_sampling_parameters,
    load_development_artifact,
    load_encoder,
    privacy_metadata,
    publish_aggregate_result,
    read_development_manifest,
    require_memory_budget,
    short_text_summary,
    synthetic_safety_summary,
    train_classifier,
    validate_capped_fit_rows,
    validate_fixed_config,
    validate_locked_contract,
    validate_p4_r0_paths,
    verify_development_artifact,
)


class FakeEncoder:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def encode(self, texts: list[str], **kwargs: object) -> np.ndarray:
        self.calls.append({"texts": texts, **kwargs})
        return np.array(
            [[float(index), 1.0] for index, _ in enumerate(texts)], dtype=np.float32
        )


def development_manifest(artifact_sha256: str = "a" * 64) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "completed",
        "artifact": {
            "file_name": ARTIFACT_RELATIVE_PATH.name,
            "rows": EXPECTED_ARTIFACT_ROWS,
            "sha256": artifact_sha256,
        },
        "partitions": {
            name: {"rows": rows} for name, rows in EXPECTED_PARTITION_ROWS.items()
        },
        "source_manifest_provenance": {
            "combined_checksum_verified_during_authorized_extraction": True
        },
        "protection": {
            "original_validation_rows_excluded": True,
            "held_out_test_rows_excluded": True,
            "protected_rows_published": False,
            "manifest_aggregate_only": True,
        },
    }


def test_locked_configuration_includes_every_runtime_setting() -> None:
    config = P4R0Config()
    assert (
        config.model_name,
        config.model_revision,
        config.device,
        config.batch_size,
    ) == (MODEL_NAME, MODEL_REVISION, DEVICE, 256)
    assert config.normalize_embeddings is True
    assert (
        config.logistic_regression_c,
        config.logistic_regression_solver,
        config.logistic_regression_max_iter,
        config.logistic_regression_class_weight,
        config.calibration_method,
    ) == (
        1.0,
        LOGISTIC_REGRESSION_SOLVER,
        LOGISTIC_REGRESSION_MAX_ITER,
        LOGISTIC_REGRESSION_CLASS_WEIGHT,
        CALIBRATION_METHOD,
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("model_name", "other"),
        ("model_revision", "main"),
        ("device", "cuda"),
        ("batch_size", 64),
        ("normalize_embeddings", False),
        ("logistic_regression_c", 0.5),
        ("logistic_regression_solver", "liblinear"),
        ("logistic_regression_max_iter", 10),
        ("logistic_regression_class_weight", None),
        ("calibration_method", "isotonic"),
        ("train_per_class_cap", 1),
        ("seed", 1),
    ],
)
def test_every_configuration_override_is_rejected_before_work(
    field: str, value: object
) -> None:
    with pytest.raises(ResearchError, match="immutable"):
        validate_fixed_config(replace(P4R0Config(), **{field: value}))


def test_local_encoder_forwards_revision_and_disables_network(tmp_path: Path) -> None:
    snapshot = tmp_path / MODEL_REVISION
    snapshot.mkdir()
    (snapshot / "config.json").write_text("{}", encoding="utf-8")
    calls: list[dict[str, object]] = []

    def factory(*args: object, **kwargs: object) -> FakeEncoder:
        calls.append({"args": args, "kwargs": kwargs})
        return FakeEncoder()

    _, metadata = load_encoder(factory=factory, snapshot=snapshot)
    assert calls[0]["args"] == (MODEL_NAME,)
    assert calls[0]["kwargs"] == {
        "device": DEVICE,
        "revision": MODEL_REVISION,
        "local_files_only": True,
    }
    assert metadata["resolved_revision"] == MODEL_REVISION


def test_wrong_snapshot_is_rejected(tmp_path: Path) -> None:
    wrong = tmp_path / "main"
    wrong.mkdir()
    with pytest.raises(ResearchError, match="locked revision"):
        load_encoder(factory=lambda **_: FakeEncoder(), snapshot=wrong)


def test_p4_paths_require_development_artifact_and_reject_combined_source(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    artifact = workspace / ARTIFACT_RELATIVE_PATH
    manifest = workspace / ARTIFACT_MANIFEST_RELATIVE_PATH
    output = workspace / OUTPUT_RELATIVE_PATH
    validate_p4_r0_paths(artifact, manifest, output, workspace)
    with pytest.raises(ResearchError, match="combined source"):
        validate_p4_r0_paths(
            workspace / SOURCE_RELATIVE_PATH, manifest, output, workspace
        )
    with pytest.raises(ResearchError, match="canonical"):
        validate_p4_r0_paths(workspace / "other.csv", manifest, output, workspace)


def test_combined_source_rejection_happens_before_memory_or_loader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = Path.cwd()
    invoked: list[str] = []
    monkeypatch.setattr(
        p4,
        "require_memory_budget",
        lambda *args, **kwargs: invoked.append("memory") or 0,
    )
    monkeypatch.setattr(
        p4,
        "_phase2_dependencies",
        lambda: (_ for _ in ()).throw(AssertionError("work invoked")),
    )
    with pytest.raises(ResearchError, match="combined source"):
        p4.run_p4_r0(
            workspace / SOURCE_RELATIVE_PATH,
            workspace / ARTIFACT_MANIFEST_RELATIVE_PATH,
            workspace / OUTPUT_RELATIVE_PATH,
        )
    assert invoked == []


def test_development_manifest_and_checksum_are_verified_before_parsing(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / ARTIFACT_RELATIVE_PATH.name
    artifact.write_text("development-only", encoding="utf-8")
    checksum = hashlib.sha256(artifact.read_bytes()).hexdigest()
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(development_manifest(checksum)), encoding="utf-8"
    )
    manifest = read_development_manifest(manifest_path)
    verify_development_artifact(artifact, manifest)
    artifact.write_text("tampered", encoding="utf-8")
    with pytest.raises(ResearchError, match="checksum"):
        verify_development_artifact(artifact, manifest)


def test_development_artifact_count_rejection_uses_synthetic_file(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "development.csv"
    artifact.write_text(
        f"{PARTITION_COLUMN},Consumer complaint narrative,department_label\nfit,example,account_support\n",
        encoding="utf-8",
    )
    dependencies = (
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        ("Consumer complaint narrative", "department_label"),
        "department_label",
        "Consumer complaint narrative",
        None,
        LABELS,
        None,
        None,
    )
    with pytest.raises(ResearchError, match="partition counts"):
        load_development_artifact(artifact, development_manifest(), dependencies)


def test_no_overwrite_is_checked_before_memory_or_loader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "existing.json"
    output.write_text("{}", encoding="utf-8")
    invoked: list[str] = []
    monkeypatch.setattr(p4, "validate_p4_r0_paths", lambda *args: None)
    monkeypatch.setattr(p4, "validate_phase2b_baseline_path", lambda *args: None)
    monkeypatch.setattr(
        p4,
        "require_memory_budget",
        lambda *args, **kwargs: invoked.append("memory") or 0,
    )
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        p4.run_p4_r0(tmp_path / "artifact.csv", tmp_path / "manifest.json", output)
    assert invoked == []


def test_locked_contract_and_memory_policy_are_enforced() -> None:
    metadata = {
        "development_partitions": {
            name: {"rows": rows} for name, rows in EXPECTED_PARTITION_ROWS.items()
        },
        "original_validation_rows_excluded": True,
        "held_out_test_rows_excluded": True,
    }
    validate_locked_contract(metadata, development_manifest())
    with pytest.raises(ResearchError, match="capped fit"):
        validate_capped_fit_rows([])
    plan = conservative_memory_plan()
    assert plan["estimated_peak_memory_bytes"] == 6_348_121_088
    assert (
        require_memory_budget(available_bytes=MIN_AVAILABLE_MEMORY_BYTES)
        == MIN_AVAILABLE_MEMORY_BYTES
    )
    with pytest.raises(ResearchError, match="available RAM"):
        require_memory_budget(available_bytes=MIN_AVAILABLE_MEMORY_BYTES - 1)
    source = inspect.getsource(p4.run_p4_r0)
    assert (
        "verify_development_artifact" in source
        and "before loading development-only artifact" in source
    )


def test_encoding_classifier_and_calibration_use_only_mock_data() -> None:
    encoder = FakeEncoder()
    matrix = encode_texts(encoder, ["one", "two"], P4R0Config())
    assert matrix.shape == (2, 2)
    assert encoder.calls[0]["normalize_embeddings"] is True
    assert fit_sampling_parameters(P4R0Config()) == {
        "train_per_class_cap": 30_000,
        "seed": 20260810,
    }
    classifier = train_classifier(
        np.array([[0.0, 0.0], [0.1, 0.0], [1.0, 1.0], [1.1, 1.0]]),
        ["account_support", "account_support", "transfer_payment", "transfer_payment"],
        P4R0Config(),
    )
    calibrated = calibrate_classifier(
        classifier,
        np.array([[0.0, 0.1]] * 5 + [[1.0, 1.1]] * 5),
        ["account_support"] * 5 + ["transfer_payment"] * 5,
        P4R0Config(),
    )
    assert classifier.class_weight == "balanced" and calibrated.method == "sigmoid"


def test_synthetic_output_and_phase2b_gates_remain_aggregate_only() -> None:
    class FakeClassifier:
        classes_ = np.asarray(["account_support", "transfer_payment"])

        def predict_proba(self, embeddings: np.ndarray) -> np.ndarray:
            return np.tile(np.asarray([[0.3, 0.7]]), (len(embeddings), 1))

    _, summary = synthetic_safety_summary(
        FakeEncoder(),
        FakeClassifier(),
        P4R0Config(),
        (("case", "synthetic", "transfer_payment"),),
        lambda value: value,
    )
    assert_aggregate_only_payload({"synthetic_safety": summary})
    with pytest.raises(ResearchError, match="prohibited"):
        assert_aggregate_only_payload({"prediction": "transfer_payment"})
    per_class = {label: {"f1": 0.75, "recall": 0.75} for label in LABELS}
    per_class["transfer_payment"] = {"f1": 0.75, "recall": 0.50}
    candidate = {
        "validation_metrics": {
            "macro_f1": 0.71,
            "weighted_f1": 0.81,
            "per_class": per_class,
            "transfer_as_account": 100,
            "account_as_transfer": 20,
        },
        "text_length_metrics": [
            {"minimum_characters": 0, "maximum_characters": 100, "macro_f1": 0.53},
            {"minimum_characters": 101, "maximum_characters": 300, "macro_f1": 0.70},
        ],
        "fraud_metrics": {"false_positive_rate": 0.09, "false_negative_rate": 0.14},
        "calibrated_confidence": {
            "ece": 0.02,
            "multiclass_brier": 0.10,
            "wrong_high_confidence": {"0.6": 0, "0.7": 0, "0.8": 0, "0.9": 0},
        },
        "synthetic_regression": [
            {
                "case_id": key,
                "expected_department": label,
                "predicted_department": label,
                "safe_at_0_60": True,
            }
            for key, label in (
                ("account_access", "account_support"),
                ("card_payment", "card_atm"),
                ("fraud", "fraud_security"),
                ("loan", "loan_credit"),
            )
        ],
    }
    baseline = json.loads(json.dumps(candidate))
    baseline["validation_metrics"]["per_class"]["transfer_payment"]["recall"] = 0.40
    baseline["text_length_metrics"][0]["macro_f1"] = 0.50
    assert (
        evaluate_phase2b_gates(candidate, baseline, acceptance_gates)["passed"] is True
    )


def test_atomic_aggregate_publication_leaves_no_partial_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "artifact.json"
    monkeypatch.setattr(
        p4,
        "atomic_write_json",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("failure")),
    )
    with pytest.raises(OSError, match="failure"):
        publish_aggregate_result(output, {"privacy": privacy_metadata()})
    assert not output.exists()
    atomic_write_json(output, {"privacy": privacy_metadata()})
    with pytest.raises(FileExistsError):
        atomic_write_json(output, {"privacy": privacy_metadata()})


def test_short_text_contract_is_preserved() -> None:
    assert set(
        short_text_summary(
            [
                {"minimum_characters": 0, "maximum_characters": 100},
                {"minimum_characters": 101, "maximum_characters": 300},
            ]
        )
    ) == {"0_100", "101_300"}
