"""Read-only validation for the Stage 1B blind human-review worksheet."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

try:
    from scripts.prepare_stage1b_review_worksheet import (
        EXPECTED_DRAFT_SHA256,
        SHUFFLE_SEED,
        WORKSHEET_COLUMNS,
        build_reference,
        build_worksheet_rows,
        load_sources,
        sha256_file,
    )
except ModuleNotFoundError:
    from prepare_stage1b_review_worksheet import (
        EXPECTED_DRAFT_SHA256,
        SHUFFLE_SEED,
        WORKSHEET_COLUMNS,
        build_reference,
        build_worksheet_rows,
        load_sources,
        sha256_file,
    )

HUMAN_ENTRY_COLUMNS = (
    "reviewer_decision",
    "reviewer_department",
    "revised_text",
    "reviewer_note",
)
PROHIBITED_COLUMNS = {
    "expected_department",
    "original_department",
    "proposed_department",
    "difficulty",
    "prediction",
    "predicted_department",
    "confidence",
    "approval_recommendation",
}


def load_csv_canonical(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError("worksheet must be UTF-8 without BOM")
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("worksheet is not valid UTF-8") from exc
    if b"\r" in raw or not raw.endswith(b"\n"):
        raise ValueError("worksheet must use LF line endings and end with LF")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames or []
        rows = list(reader)
    return columns, rows


def validate_worksheet(
    worksheet_path: Path,
    reference_path: Path,
    draft_path: Path,
    queue_path: Path,
) -> list[str]:
    errors: list[str] = []
    if sha256_file(draft_path) != EXPECTED_DRAFT_SHA256:
        errors.append("draft benchmark SHA-256 changed")
        return errors
    try:
        records, entries, _queue = load_sources(draft_path, queue_path)
        expected_rows = build_worksheet_rows(records, entries)
        expected_reference = build_reference(records, entries)
        columns, rows = load_csv_canonical(worksheet_path)
        reference = json.loads(reference_path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return [str(exc)]
    if columns != list(WORKSHEET_COLUMNS):
        errors.append("worksheet columns are not in canonical order")
    if set(columns) & PROHIBITED_COLUMNS:
        errors.append("worksheet exposes prohibited answer or model metadata")
    if len(rows) != 73:
        errors.append(f"worksheet must contain 73 rows, found {len(rows)}")
    ids = [row.get("record_id", "") for row in rows]
    queued_ids = {entry["example_id"] for entry in entries}
    if len(set(ids)) != 73:
        errors.append("worksheet record IDs are not unique")
    if set(ids) != queued_ids:
        errors.append("worksheet IDs do not exactly match the committed review queue")
    expected_serialized = [
        {key: str(value) for key, value in row.items()} for row in expected_rows
    ]
    if rows != expected_serialized:
        errors.append("worksheet rows do not reproduce from the fixed seed and sources")
    for position, row in enumerate(rows, start=1):
        if row.get("review_order") != str(position):
            errors.append(f"review_order is invalid at row {position}")
        if any(row.get(column) for column in HUMAN_ENTRY_COLUMNS):
            errors.append(f"human-entry fields are not empty at row {position}")
    if reference != expected_reference:
        errors.append("sealed reference does not reproduce from committed sources")
    required_reference_flags = {
        "status": "internal_reference_only",
        "do_not_consult_during_blind_review": True,
        "not_human_review_results": True,
        "not_approval_evidence": True,
        "contains_predictions": False,
        "contains_confidence": False,
        "source_draft_sha256": EXPECTED_DRAFT_SHA256,
    }
    for key, value in required_reference_flags.items():
        if reference.get(key) != value:
            errors.append(f"sealed reference flag {key!r} is invalid")
    if reference.get("deterministic_shuffle", {}).get("seed") != SHUFFLE_SEED:
        errors.append("sealed reference shuffle seed is invalid")
    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worksheet", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--draft", type=Path, required=True)
    parser.add_argument("--queue", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    errors = validate_worksheet(args.worksheet, args.reference, args.draft, args.queue)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(f"Stage 1B worksheet validation passed: rows=73 seed={SHUFFLE_SEED}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
