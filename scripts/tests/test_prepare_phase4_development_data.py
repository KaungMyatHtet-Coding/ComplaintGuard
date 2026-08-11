from __future__ import annotations

import json
import os
import random
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from prepare_phase4_development_data import (
    ARTIFACT_MANIFEST_RELATIVE_PATH,
    ARTIFACT_RELATIVE_PATH,
    EXPECTED_ARTIFACT_ROWS,
    EXPECTED_PARTITION_ROWS,
    LOCKED_RESERVOIR_SEED,
    SOURCE_MANIFEST_RELATIVE_PATH,
    SOURCE_RELATIVE_PATH,
    PreparationError,
    build_manifest,
    original_partition,
    publish_transaction,
    select_locked_original_train_rows,
    sha256_file,
    validate_paths,
    write_manifest_temp,
)
from train_department_baseline import normalize_text


def _legacy_reservoir(rows: list[tuple[str, str]], size: int) -> list[tuple[str, str]]:
    randomizer = random.Random(LOCKED_RESERVOIR_SEED)
    selected: list[tuple[str, str]] = []
    for processed, row in enumerate(rows, start=1):
        if len(selected) < size:
            selected.append(row)
        else:
            position = randomizer.randrange(processed)
            if position < size:
                selected[position] = row
    return selected


def test_selection_matches_phase2_membership_and_excludes_protected_rows(
    tmp_path: Path,
) -> None:
    rows = [
        (f"narrative {index}", "account_support" if index % 2 else "card_atm")
        for index in range(1, 12)
    ]
    selected, processed = select_locked_original_train_rows(rows, reservoir_rows=4)
    legacy = _legacy_reservoir(rows, 4)
    expected = [
        (normalize_text(text), label)
        for text, label in legacy
        if original_partition(normalize_text(text)) == "train"
    ]

    assert processed == len(rows)
    assert selected == expected
    assert all(original_partition(text) == "train" for text, _ in selected)


def test_selection_is_deterministic_and_does_not_retain_replaced_rows() -> None:
    rows = [(f"narrative {index}", "fraud_security") for index in range(20)]
    first, _ = select_locked_original_train_rows(rows, reservoir_rows=5)
    second, _ = select_locked_original_train_rows(rows, reservoir_rows=5)
    assert first == second
    assert all(normalize_text(text) == text for text, _ in first)


def test_canonical_paths_and_no_overwrite_are_rejected_before_source_read(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    source = root / SOURCE_RELATIVE_PATH
    source_manifest = root / SOURCE_MANIFEST_RELATIVE_PATH
    artifact = root / ARTIFACT_RELATIVE_PATH
    artifact_manifest = root / ARTIFACT_MANIFEST_RELATIVE_PATH
    validate_paths(source, source_manifest, artifact, artifact_manifest, root)
    with pytest.raises(PreparationError, match="canonical"):
        validate_paths(
            root / "other.csv", source_manifest, artifact, artifact_manifest, root
        )
    artifact.parent.mkdir(parents=True)
    artifact.write_text("existing", encoding="utf-8")
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        validate_paths(source, source_manifest, artifact, artifact_manifest, root)


def test_manifest_is_aggregate_only_and_records_only_permitted_counts(
    tmp_path: Path,
) -> None:
    source_manifest = {
        "output": {
            "file_name": SOURCE_RELATIVE_PATH.name,
            "rows": 3_822_576,
            "sha256": "b" * 64,
        }
    }
    manifest = build_manifest(source_manifest, "a" * 64, dict(EXPECTED_PARTITION_ROWS))
    encoded = json.dumps(manifest)
    assert manifest["artifact"]["rows"] == EXPECTED_ARTIFACT_ROWS
    assert set(manifest["partitions"]) == {"fit", "calibration", "validation"}
    for forbidden in (
        "narrative",
        "complaint_id",
        "row_id",
        "expected_department",
        "predicted_department",
        "probability",
        "embedding",
    ):
        assert forbidden not in encoded
    temporary = write_manifest_temp(tmp_path / "manifest.json", manifest)
    assert (
        json.loads(temporary.read_text(encoding="utf-8"))["protection"][
            "protected_rows_published"
        ]
        is False
    )
    temporary.unlink()


def test_artifact_checksum_is_deterministic_for_identical_bytes(tmp_path: Path) -> None:
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    payload = b"development_partition,Consumer complaint narrative,department_label\nfit,text,account_support\n"
    first.write_bytes(payload)
    second.write_bytes(payload)
    assert sha256_file(first) == sha256_file(second)


def test_transaction_rolls_back_new_artifact_when_manifest_publish_fails(
    tmp_path: Path,
) -> None:
    artifact_temp = tmp_path / "artifact.tmp"
    manifest_temp = tmp_path / "manifest.tmp"
    artifact_path = tmp_path / "artifact.csv"
    manifest_path = tmp_path / "manifest.json"
    artifact_temp.write_text("artifact", encoding="utf-8")
    manifest_temp.write_text("manifest", encoding="utf-8")

    def publish(source: Path, destination: Path) -> None:
        if destination == manifest_path:
            raise OSError("simulated manifest failure")
        os.link(source, destination)

    with pytest.raises(OSError, match="simulated"):
        publish_transaction(
            artifact_temp, artifact_path, manifest_temp, manifest_path, publish
        )
    assert not artifact_path.exists()
    assert not manifest_path.exists()
    assert not artifact_temp.exists()
    assert not manifest_temp.exists()


def test_transaction_publishes_artifact_then_manifest(tmp_path: Path) -> None:
    artifact_temp = tmp_path / "artifact.tmp"
    manifest_temp = tmp_path / "manifest.tmp"
    artifact_path = tmp_path / "artifact.csv"
    manifest_path = tmp_path / "manifest.json"
    artifact_temp.write_text("artifact", encoding="utf-8")
    manifest_temp.write_text("manifest", encoding="utf-8")
    publish_transaction(artifact_temp, artifact_path, manifest_temp, manifest_path)
    assert artifact_path.read_text(encoding="utf-8") == "artifact"
    assert manifest_path.read_text(encoding="utf-8") == "manifest"


def test_canonical_artifact_path_is_ignored_by_repository_policy() -> None:
    ignore_rules = (Path(__file__).resolve().parents[2] / ".gitignore").read_text(
        encoding="utf-8"
    )
    assert "data/interim/" in ignore_rules
    assert ARTIFACT_RELATIVE_PATH.as_posix().startswith("data/interim/")
