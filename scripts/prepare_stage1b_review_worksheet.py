"""Prepare the deterministic Stage 1B blind-review files without reviewing data."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from pathlib import Path
from typing import Any

SHUFFLE_SEED = 20260814
EXPECTED_DRAFT_SHA256 = (
    "f9ae2ab171c51b630a081c770e6db48bc06d0924f3823da4827643c2562553f7"
)
WORKSHEET_COLUMNS = (
    "review_order",
    "record_id",
    "complaint_text",
    "review_reasons",
    "word_count",
    "reviewer_decision",
    "reviewer_department",
    "revised_text",
    "reviewer_note",
)
REASON_MAP = {
    "ambiguity_notes": "ambiguity_review",
    "hard_label_confirmation": "hard_label_confirmation",
    "controlled_variation": "controlled_variation",
    "unusual_length": "unusual_length",
    "near_duplicate_candidates": "near_duplicate_review",
    "cross_label_similarity": "cross_label_similarity_review",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_sources(
    draft_path: Path, queue_path: Path
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    if sha256_file(draft_path) != EXPECTED_DRAFT_SHA256:
        raise ValueError(
            "draft benchmark SHA-256 differs from the reviewed Stage 1A draft"
        )
    records: dict[str, dict[str, Any]] = {}
    with draft_path.open("r", encoding="utf-8", newline="") as handle:
        for line in handle:
            record = json.loads(line)
            record_id = record["example_id"]
            if record_id in records:
                raise ValueError("draft benchmark contains duplicate record IDs")
            records[record_id] = record
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    entries = queue.get("entries")
    if not isinstance(entries, list) or len(entries) != 73:
        raise ValueError("review queue must contain exactly 73 entries")
    queued_ids = [entry.get("example_id") for entry in entries]
    if len(set(queued_ids)) != 73 or any(
        record_id not in records for record_id in queued_ids
    ):
        raise ValueError("review queue IDs must be unique members of the draft")
    return records, entries, queue


def shuffled_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    shuffled = list(entries)
    random.Random(SHUFFLE_SEED).shuffle(shuffled)
    original = [entry["example_id"] for entry in entries]
    result = [entry["example_id"] for entry in shuffled]
    if result == original or result == sorted(result):
        raise ValueError("deterministic shuffle did not blind the source order")
    return shuffled


def neutral_reasons(entry: dict[str, Any]) -> str:
    categories = entry.get("review_categories")
    if not isinstance(categories, list) or not categories:
        raise ValueError("every queued record requires at least one review category")
    try:
        normalized = sorted({REASON_MAP[category] for category in categories})
    except KeyError as exc:
        raise ValueError(f"unsupported review category: {exc.args[0]}") from exc
    return "|".join(normalized)


def build_worksheet_rows(
    records: dict[str, dict[str, Any]], entries: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    rows = []
    for order, entry in enumerate(shuffled_entries(entries), start=1):
        record = records[entry["example_id"]]
        rows.append(
            {
                "review_order": order,
                "record_id": record["example_id"],
                "complaint_text": record["text"],
                "review_reasons": neutral_reasons(entry),
                "word_count": record["word_count"],
                "reviewer_decision": "",
                "reviewer_department": "",
                "revised_text": "",
                "reviewer_note": "",
            }
        )
    return rows


def build_reference(
    records: dict[str, dict[str, Any]], entries: list[dict[str, Any]]
) -> dict[str, Any]:
    source_positions = {
        entry["example_id"]: position for position, entry in enumerate(entries, start=1)
    }
    rows = []
    for order, entry in enumerate(shuffled_entries(entries), start=1):
        record = records[entry["example_id"]]
        rows.append(
            {
                "review_order": order,
                "record_id": record["example_id"],
                "original_department": record["expected_department"],
                "original_difficulty": record["difficulty"],
                "original_review_reasons": entry["review_categories"],
                "source_queue_position": source_positions[record["example_id"]],
            }
        )
    return {
        "status": "internal_reference_only",
        "do_not_consult_during_blind_review": True,
        "not_human_review_results": True,
        "not_approval_evidence": True,
        "contains_predictions": False,
        "contains_confidence": False,
        "deterministic_shuffle": {
            "algorithm": "Python random.Random(seed).shuffle",
            "seed": SHUFFLE_SEED,
            "input_order": "committed Stage 1A review queue entry order",
        },
        "source_draft_sha256": EXPECTED_DRAFT_SHA256,
        "record_count": len(rows),
        "records": rows,
    }


def write_outputs(
    worksheet_path: Path,
    reference_path: Path,
    worksheet_rows: list[dict[str, Any]],
    reference: dict[str, Any],
) -> None:
    worksheet_path.parent.mkdir(parents=True, exist_ok=True)
    with worksheet_path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=WORKSHEET_COLUMNS, lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(worksheet_rows)
    with reference_path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(reference, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", type=Path, required=True)
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--worksheet", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        records, entries, _queue = load_sources(args.draft, args.queue)
        rows = build_worksheet_rows(records, entries)
        reference = build_reference(records, entries)
        write_outputs(args.worksheet, args.reference, rows, reference)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"Worksheet preparation failed: {type(exc).__name__}: {exc}")
        return 1
    print(
        f"Prepared {len(rows)} blind review rows with deterministic seed {SHUFFLE_SEED}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
