"""Create the locked Phase 4 development-only artifact from the authorized source."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import random
import tempfile
from collections import Counter
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

try:
    from research_phase2b_classifier import (
        DEVELOPMENT_SEED,
        EXPECTED_DATASET_SHA256,
        LOCKED_RESERVOIR_SEED,
        split_development_rows,
    )
    from train_department_baseline import (
        LABEL_COLUMN,
        LABELS,
        TEXT_COLUMN,
        normalize_text,
    )
except ModuleNotFoundError:  # pragma: no cover
    from scripts.research_phase2b_classifier import (
        DEVELOPMENT_SEED,
        EXPECTED_DATASET_SHA256,
        LOCKED_RESERVOIR_SEED,
        split_development_rows,
    )
    from scripts.train_department_baseline import (
        LABEL_COLUMN,
        LABELS,
        TEXT_COLUMN,
        normalize_text,
    )


SCHEMA_VERSION = 1
METHOD_VERSION = "phase4-development-extraction-v1"
SOURCE_RELATIVE_PATH = Path("data/interim/cfpb/cfpb_training_v1.csv")
SOURCE_MANIFEST_RELATIVE_PATH = Path("data/processed/cfpb_training_v1_manifest.json")
ARTIFACT_RELATIVE_PATH = Path("data/interim/cfpb/phase4_development_v1.csv")
ARTIFACT_MANIFEST_RELATIVE_PATH = Path(
    "data/processed/phase4_development_v1_manifest.json"
)
PARTITION_COLUMN = "development_partition"
ARTIFACT_COLUMNS = (PARTITION_COLUMN, TEXT_COLUMN, LABEL_COLUMN)
LOCKED_RESERVOIR_ROWS = 200_000
ORIGINAL_TRAIN_RATIO = 0.70
ORIGINAL_VALIDATION_RATIO = 0.15
EXPECTED_PARTITION_ROWS = {
    "fit": 99_200,
    "calibration": 21_909,
    "validation": 19_672,
}
EXPECTED_ARTIFACT_ROWS = sum(EXPECTED_PARTITION_ROWS.values())


class PreparationError(RuntimeError):
    """Raised when the authorized development-data extraction is unsafe."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_path(root: Path, relative_path: Path) -> Path:
    return (root / relative_path).resolve()


def validate_paths(
    source_path: Path,
    source_manifest_path: Path,
    artifact_path: Path,
    artifact_manifest_path: Path,
    workspace_root: Path | None = None,
) -> None:
    root = (workspace_root or Path.cwd()).resolve()
    expected = (
        _canonical_path(root, SOURCE_RELATIVE_PATH),
        _canonical_path(root, SOURCE_MANIFEST_RELATIVE_PATH),
        _canonical_path(root, ARTIFACT_RELATIVE_PATH),
        _canonical_path(root, ARTIFACT_MANIFEST_RELATIVE_PATH),
    )
    actual = tuple(
        path.expanduser().resolve(strict=False)
        for path in (
            source_path,
            source_manifest_path,
            artifact_path,
            artifact_manifest_path,
        )
    )
    if actual != expected:
        raise PreparationError(
            "Phase 4 extraction paths must use the canonical contract"
        )
    if artifact_path.exists() or artifact_manifest_path.exists():
        raise FileExistsError("refusing to overwrite a Phase 4 development artifact")


def read_source_manifest(path: Path) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    output = manifest.get("output", {})
    if (
        manifest.get("status") != "completed"
        or output.get("file_name") != SOURCE_RELATIVE_PATH.name
        or output.get("rows") != 3_822_576
        or output.get("sha256") != EXPECTED_DATASET_SHA256
    ):
        raise PreparationError(
            "source manifest does not match the locked Phase 2 provenance"
        )
    return manifest


def original_partition(normalized: str) -> str:
    digest = hashlib.sha256(f"{LOCKED_RESERVOIR_SEED}\0{normalized}".encode()).digest()
    fraction = int.from_bytes(digest[:8], "big") / 2**64
    if fraction < ORIGINAL_TRAIN_RATIO:
        return "train"
    if fraction < ORIGINAL_TRAIN_RATIO + ORIGINAL_VALIDATION_RATIO:
        return "validation"
    return "test"


def select_locked_original_train_rows(
    rows: Iterable[tuple[str, str]],
    *,
    reservoir_rows: int = LOCKED_RESERVOIR_ROWS,
    seed: int = LOCKED_RESERVOIR_SEED,
    normalizer: Callable[[str], str] = normalize_text,
) -> tuple[list[tuple[str, str]], int]:
    """Reproduce the reservoir while retaining only selected original-train rows."""
    if reservoir_rows <= 0 or seed != LOCKED_RESERVOIR_SEED:
        raise PreparationError("locked reservoir configuration differs from Phase 2")
    slots: list[tuple[str, str] | None] = [None] * reservoir_rows
    randomizer = random.Random(seed)
    processed = 0
    for text, label in rows:
        processed += 1
        if processed <= reservoir_rows:
            position = processed - 1
        else:
            position = randomizer.randrange(processed)
            if position >= reservoir_rows:
                continue
        if not isinstance(text, str) or not text.strip():
            raise PreparationError(
                "source contains an empty narrative in a selected row"
            )
        normalized = normalizer(text)
        if not normalized:
            raise PreparationError(
                "selected narrative is empty after locked normalization"
            )
        if original_partition(normalized) == "train":
            if label not in LABELS:
                raise PreparationError(
                    "selected original-train row has an invalid label"
                )
            slots[position] = (normalized, label)
        else:
            # Protected rows are transiently classified only to reproduce membership.
            # Their normalized text and labels are never retained or published.
            slots[position] = None
        del normalized
    return [row for row in slots if row is not None], processed


def _source_rows(source_path: Path) -> Iterable[tuple[str, str]]:
    with source_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != (TEXT_COLUMN, LABEL_COLUMN):
            raise PreparationError(
                "combined source schema differs from the Phase 2 lock"
            )
        for row in reader:
            yield row[TEXT_COLUMN], row[LABEL_COLUMN]


def split_locked_development_rows(
    original_train_rows: list[tuple[str, str]],
) -> dict[str, list[tuple[str, str]]]:
    development = split_development_rows(original_train_rows, seed=DEVELOPMENT_SEED)
    counts = {name: len(rows) for name, rows in development.items()}
    if counts != EXPECTED_PARTITION_ROWS:
        raise PreparationError(
            "locked Phase 2 development membership did not reconstruct"
        )
    return development


def _temporary_path(destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="wb",
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        return Path(handle.name)


def write_artifact_temp(
    destination: Path, development: dict[str, list[tuple[str, str]]]
) -> tuple[Path, dict[str, int]]:
    temporary_path = _temporary_path(destination)
    counts = Counter[str]()
    try:
        with temporary_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=ARTIFACT_COLUMNS, lineterminator="\n"
            )
            writer.writeheader()
            for partition in ("fit", "calibration", "validation"):
                for text, label in development[partition]:
                    writer.writerow(
                        {
                            PARTITION_COLUMN: partition,
                            TEXT_COLUMN: text,
                            LABEL_COLUMN: label,
                        }
                    )
                    counts[partition] += 1
            handle.flush()
            os.fsync(handle.fileno())
        if dict(counts) != EXPECTED_PARTITION_ROWS:
            raise PreparationError("development artifact counts differ from the lock")
        if sum(counts.values()) != EXPECTED_ARTIFACT_ROWS:
            raise PreparationError(
                "development artifact row total differs from the lock"
            )
        return temporary_path, dict(counts)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def build_manifest(
    source_manifest: dict[str, Any], artifact_sha256: str, counts: dict[str, int]
) -> dict[str, Any]:
    output = source_manifest["output"]
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "completed",
        "artifact": {
            "file_name": ARTIFACT_RELATIVE_PATH.name,
            "rows": EXPECTED_ARTIFACT_ROWS,
            "sha256": artifact_sha256,
        },
        "partitions": {
            name: {"rows": counts[name]} for name in EXPECTED_PARTITION_ROWS
        },
        "source_manifest_provenance": {
            "file_name": SOURCE_MANIFEST_RELATIVE_PATH.name,
            "combined_dataset_file": output["file_name"],
            "combined_dataset_sha256": output["sha256"],
            "combined_dataset_rows": output["rows"],
            "combined_checksum_verified_during_authorized_extraction": True,
        },
        "extraction": {
            "method_version": METHOD_VERSION,
            "reservoir_rows": LOCKED_RESERVOIR_ROWS,
            "reservoir_seed": LOCKED_RESERVOIR_SEED,
            "original_split": "sha256(seed + NUL + normalized_text), 70/15/15",
            "development_seed": DEVELOPMENT_SEED,
            "development_split": "sha256(phase2a + NUL + seed + NUL + normalized_text), 70/15/15",
        },
        "protection": {
            "original_validation_rows_excluded": True,
            "held_out_test_rows_excluded": True,
            "protected_rows_published": False,
            "manifest_aggregate_only": True,
        },
    }


def write_manifest_temp(destination: Path, manifest: dict[str, Any]) -> Path:
    temporary_path = _temporary_path(destination)
    try:
        with temporary_path.open("w", encoding="utf-8", newline="") as handle:
            json.dump(manifest, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        return temporary_path
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def publish_transaction(
    artifact_temp: Path,
    artifact_path: Path,
    manifest_temp: Path,
    manifest_path: Path,
    publish: Callable[[Path, Path], None] = os.link,
) -> None:
    artifact_published = False
    try:
        publish(artifact_temp, artifact_path)
        artifact_published = True
        publish(manifest_temp, manifest_path)
    except Exception:
        if artifact_published:
            artifact_path.unlink(missing_ok=True)
        raise
    finally:
        artifact_temp.unlink(missing_ok=True)
        manifest_temp.unlink(missing_ok=True)


def prepare_development_data(
    source_path: Path = SOURCE_RELATIVE_PATH,
    source_manifest_path: Path = SOURCE_MANIFEST_RELATIVE_PATH,
    artifact_path: Path = ARTIFACT_RELATIVE_PATH,
    artifact_manifest_path: Path = ARTIFACT_MANIFEST_RELATIVE_PATH,
) -> dict[str, Any]:
    validate_paths(
        source_path, source_manifest_path, artifact_path, artifact_manifest_path
    )
    source_manifest = read_source_manifest(source_manifest_path)
    if sha256_file(source_path) != source_manifest["output"]["sha256"]:
        raise PreparationError("combined source checksum differs from trusted manifest")
    original_train_rows, processed = select_locked_original_train_rows(
        _source_rows(source_path)
    )
    if processed != source_manifest["output"]["rows"]:
        raise PreparationError(
            "combined source row count differs from trusted manifest"
        )
    if len(original_train_rows) != EXPECTED_ARTIFACT_ROWS:
        raise PreparationError("locked original-train membership did not reconstruct")
    development = split_locked_development_rows(original_train_rows)
    artifact_temp, counts = write_artifact_temp(artifact_path, development)
    try:
        artifact_sha256 = sha256_file(artifact_temp)
        manifest = build_manifest(source_manifest, artifact_sha256, counts)
        manifest_temp = write_manifest_temp(artifact_manifest_path, manifest)
        publish_transaction(
            artifact_temp, artifact_path, manifest_temp, artifact_manifest_path
        )
    except Exception:
        artifact_temp.unlink(missing_ok=True)
        raise
    return manifest


def main() -> int:
    try:
        manifest = prepare_development_data()
    except (PreparationError, FileExistsError, OSError, ValueError) as error:
        print(f"Phase 4 development-data preparation failed: {error}")
        return 1
    print(
        json.dumps({"status": manifest["status"], "rows": manifest["artifact"]["rows"]})
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
