"""Derive the unfrozen Stage 1B reviewed candidate from human evidence."""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import os
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from scripts.run_stage1b_adjudication_app import HUMAN_FIELDS, validate_entry
    from scripts.validate_short_english_benchmark import LABELS, load_jsonl
except ModuleNotFoundError:  # Direct execution from the repository root.
    from run_stage1b_adjudication_app import HUMAN_FIELDS, validate_entry
    from validate_short_english_benchmark import LABELS, load_jsonl

EXPECTED_HASHES = {
    "source_draft": "f9ae2ab171c51b630a081c770e6db48bc06d0924f3823da4827643c2562553f7",
    "completed_review": "b3975a3604a82ae594e851673a9092054cc74f3294ca70c34ca9195541416cc3",
    "completed_adjudication": "2ebfc8696767aca54c56334cf8d432b5368c40be7faf5d201912ae0967bfd90b",
}
SPOT_CHECK_SEED = "stage1b-post-adjudication-spot-check-v1"
SOURCE_RELATIVE = Path(
    "evaluation/model_hunting/short_english_benchmark_draft_v1.jsonl"
)
REVIEW_RELATIVE = Path(
    "evaluation/model_hunting/short_english_benchmark_stage1b_completed_review.csv"
)
ADJUDICATION_RELATIVE = Path(
    "evaluation/model_hunting/short_english_benchmark_stage1b_completed_adjudication.json"
)
REPORT_RELATIVE = Path(
    "evaluation/model_hunting/short_english_benchmark_stage1b_application_report.json"
)
CANDIDATE_RELATIVE = Path(
    "evaluation/model_hunting/short_english_benchmark_reviewed_candidate_v1.jsonl"
)


class ApplicationError(ValueError):
    """Raised when evidence cannot be applied safely."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ApplicationError(f"{path} must contain a JSON object")
    return value


def _load_review(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _unique(
    records: list[dict[str, Any]], field: str, source: str
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        record_id = record.get(field)
        if not isinstance(record_id, str) or not record_id:
            raise ApplicationError(f"{source} contains a missing record ID")
        if record_id in result:
            raise ApplicationError(f"{source} contains duplicate record ID {record_id}")
        result[record_id] = record
    return result


def validate_output_path(source: Path, output: Path, expected_directory: Path) -> None:
    source = source.absolute()
    output = output.absolute()
    expected_directory = expected_directory.resolve(strict=True)
    if output.parent.resolve(strict=True) != expected_directory:
        raise ApplicationError("candidate output is outside the authorized directory")
    if output.is_symlink():
        raise ApplicationError("candidate output must not be a symlink")
    if source.resolve(strict=True) == output.resolve(strict=False):
        raise ApplicationError("candidate output aliases the source draft")
    if output.exists() and os.path.samefile(source, output):
        raise ApplicationError("candidate output is a hardlink to the source draft")


def validate_and_plan(
    source_records: list[dict[str, Any]],
    review_rows: list[dict[str, str]],
    adjudication: dict[str, Any],
) -> dict[str, Any]:
    source_by_id = _unique(source_records, "example_id", "source draft")
    review_by_id = _unique(review_rows, "record_id", "completed review")
    entries = adjudication.get("entries")
    if not isinstance(entries, list):
        raise ApplicationError("completed adjudication entries are invalid")
    adjudication_by_id = _unique(entries, "record_id", "completed adjudication")
    if len(source_records) != 180 or len(review_rows) != 73 or len(entries) != 10:
        raise ApplicationError("source or evidence record count is invalid")
    if not set(adjudication_by_id) < set(review_by_id):
        raise ApplicationError(
            "adjudication IDs must be a strict subset of reviewed IDs"
        )

    plan: dict[str, str] = {}
    classifications: Counter[str] = Counter()
    agreements: list[str] = []
    for record_id, row in review_by_id.items():
        source = source_by_id.get(record_id)
        if source is None:
            raise ApplicationError(f"review contains unknown record ID {record_id}")
        if row.get("complaint_text") != source["text"]:
            raise ApplicationError(f"review complaint text differs for {record_id}")
        if row.get("reviewer_decision") != "approve":
            raise ApplicationError(f"review decision is not approve for {record_id}")
        reviewer = row.get("reviewer_department")
        if reviewer not in LABELS:
            raise ApplicationError(f"review department is invalid for {record_id}")
        original = source["expected_department"]
        if original == reviewer:
            if record_id in adjudication_by_id:
                raise ApplicationError(f"agreement record was adjudicated: {record_id}")
            classifications["agreement"] += 1
            agreements.append(record_id)
            plan[record_id] = original
            continue
        entry = adjudication_by_id.get(record_id)
        if entry is None:
            raise ApplicationError(f"disagreement lacks adjudication: {record_id}")
        immutable = {
            "complaint_text": source["text"],
            "original_department": original,
            "reviewer_department": reviewer,
            "original_difficulty": source["difficulty"],
            "controlled_variation_flags": source["variation_tags"],
        }
        for field, expected in immutable.items():
            if entry.get(field) != expected:
                raise ApplicationError(f"adjudication {field} differs for {record_id}")
        errors = validate_entry(
            {field: entry.get(field, "") for field in HUMAN_FIELDS}, entry
        )
        if errors:
            raise ApplicationError(
                f"invalid adjudication for {record_id}: {'; '.join(errors)}"
            )
        decision = entry["adjudication_decision"]
        category = {
            "keep_original": "adjudicated_keep_original",
            "use_reviewer": "adjudicated_use_reviewer",
            "revise_and_relabel": "adjudicated_revise_and_relabel",
            "remove_from_benchmark": "adjudicated_remove",
            "needs_second_review": "unresolved",
        }[decision]
        classifications[category] += 1
        if category in {"adjudicated_remove", "unresolved"}:
            raise ApplicationError(
                f"unresolved or removal decision blocks application: {record_id}"
            )
        if entry.get("revised_text"):
            raise ApplicationError(
                f"text revision is not authorized in this application: {record_id}"
            )
        plan[record_id] = entry["final_department"]

    if set(adjudication_by_id) != {
        record_id
        for record_id, row in review_by_id.items()
        if source_by_id[record_id]["expected_department"] != row["reviewer_department"]
    }:
        raise ApplicationError(
            "adjudication membership does not equal review disagreements"
        )
    expected = Counter(
        {
            "agreement": 63,
            "adjudicated_keep_original": 9,
            "adjudicated_use_reviewer": 1,
            "adjudicated_revise_and_relabel": 0,
            "adjudicated_remove": 0,
            "unresolved": 0,
        }
    )
    if classifications != expected:
        raise ApplicationError(f"application distribution is {dict(classifications)}")
    return {
        "labels": plan,
        "reviewed_ids": list(review_by_id),
        "agreement_ids": agreements,
        "classifications": dict(expected),
    }


def derive_candidate(
    source_records: list[dict[str, Any]], plan: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    candidate = copy.deepcopy(source_records)
    changes: list[dict[str, str]] = []
    labels = plan["labels"]
    for record in candidate:
        record_id = record["example_id"]
        final = labels.get(record_id, record["expected_department"])
        if final != record["expected_department"]:
            changes.append(
                {
                    "record_id": record_id,
                    "before_department": record["expected_department"],
                    "after_department": final,
                }
            )
            record["expected_department"] = final
    if changes != [
        {
            "record_id": "SEB-0176",
            "before_department": "account_support",
            "after_department": "fraud_security",
        }
    ]:
        raise ApplicationError(f"unexpected candidate changes: {changes}")
    return candidate, changes


def select_spot_checks(
    source_by_id: dict[str, dict[str, Any]],
    review_by_id: dict[str, dict[str, str]],
    agreement_ids: list[str],
    changed_ids: list[str],
    size: int = 12,
) -> list[str]:
    def score(record_id: str) -> str:
        return hashlib.sha256(f"{SPOT_CHECK_SEED}:{record_id}".encode()).hexdigest()

    ordered = sorted(agreement_ids, key=score)
    selected = list(changed_ids)
    represented = {source_by_id[value]["expected_department"] for value in selected}
    for label in LABELS:
        if label in represented:
            continue
        choices = [
            value
            for value in ordered
            if source_by_id[value]["expected_department"] == label
            and source_by_id[value]["difficulty"] == "hard"
            and "ambiguity_review" in review_by_id[value]["review_reasons"]
        ]
        if not choices:
            choices = [
                value
                for value in ordered
                if source_by_id[value]["expected_department"] == label
            ]
        if choices:
            selected.append(choices[0])
            represented.add(label)
    controlled = [value for value in ordered if source_by_id[value]["variation_tags"]]
    for value in controlled + ordered:
        if len(selected) == size:
            break
        if value not in selected:
            selected.append(value)
    if len(selected) != size:
        raise ApplicationError("could not build the requested spot-check plan")
    return selected


def _jsonl_bytes(records: list[dict[str, Any]]) -> bytes:
    lines = [
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for value in records
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def apply(
    source_path: Path,
    review_path: Path,
    adjudication_path: Path,
    candidate_path: Path,
    report_path: Path,
    git_commit: str,
    timestamp: str,
) -> dict[str, Any]:
    for name, path in (
        ("source_draft", source_path),
        ("completed_review", review_path),
        ("completed_adjudication", adjudication_path),
    ):
        actual = sha256_file(path)
        if actual != EXPECTED_HASHES[name]:
            raise ApplicationError(f"{name} SHA-256 is {actual}")
    validate_output_path(source_path, candidate_path, source_path.parent)
    validate_output_path(source_path, report_path, source_path.parent)
    source_records = load_jsonl(source_path)
    review_rows = _load_review(review_path)
    adjudication = _load_json(adjudication_path)
    plan = validate_and_plan(source_records, review_rows, adjudication)
    candidate, changes = derive_candidate(source_records, plan)
    candidate_bytes = _jsonl_bytes(candidate)
    candidate_hash = hashlib.sha256(candidate_bytes).hexdigest()
    source_by_id = {record["example_id"]: record for record in source_records}
    review_by_id = {record["record_id"]: record for record in review_rows}
    spot_ids = select_spot_checks(
        source_by_id,
        review_by_id,
        plan["agreement_ids"],
        [change["record_id"] for change in changes],
    )
    report = {
        "status": "reviewed_candidate_unapproved_unfrozen",
        "git_commit": git_commit,
        "application_timestamp": timestamp,
        "inputs": {
            "source_draft": {
                "path": SOURCE_RELATIVE.as_posix(),
                "sha256": EXPECTED_HASHES["source_draft"],
            },
            "completed_review": {
                "path": REVIEW_RELATIVE.as_posix(),
                "sha256": EXPECTED_HASHES["completed_review"],
            },
            "completed_adjudication": {
                "path": ADJUDICATION_RELATIVE.as_posix(),
                "sha256": EXPECTED_HASHES["completed_adjudication"],
            },
        },
        "counts": {
            "source_records": len(source_records),
            "candidate_records": len(candidate),
            "reviewed_queue": 73,
            "non_queued": 107,
            **plan["classifications"],
            "text_changes": 0,
            "added": 0,
            "removed": 0,
            "reordered": 0,
        },
        "changes": changes,
        "candidate": {
            "path": CANDIDATE_RELATIVE.as_posix(),
            "sha256": candidate_hash,
            "label_distribution": {
                label: Counter(record["expected_department"] for record in candidate)[
                    label
                ]
                for label in LABELS
            },
            "approved": False,
            "benchmark_version": "",
            "freeze_status": "unfrozen",
        },
        "review_coverage": {
            "record_level_schema_handling": "Existing draft fields are preserved; the schema cannot distinguish 73 reviewed records from 107 non-queued records without ad hoc fields.",
            "limitation": "Only the 73 Stage 1B queued records received delayed blind review; the other 107 records were not individually reviewed in Stage 1B.",
        },
        "leakage_limitation": "Prior exact checks are carried forward because complaint text did not change; full-corpus near-duplicate and raw-source checks remain incomplete.",
        "spot_check_plan": {
            "status": "pending",
            "size": len(spot_ids),
            "record_ids": spot_ids,
            "method": f"Include changed records, then one hard ambiguity agreement per unrepresented department where available, then controlled-variation agreements and deterministic SHA-256 order using seed {SPOT_CHECK_SEED}.",
        },
        "safeguards": {
            "candidate_remains_unapproved": True,
            "candidate_remains_unfrozen": True,
            "no_model_predictions_consulted": True,
            "no_candidate_model_work_occurred": True,
            "authored_rationale_preserved_as_source_metadata": True,
        },
    }
    report_bytes = (
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    atomic_write(candidate_path, candidate_bytes)
    atomic_write(report_path, report_bytes)
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate_output", type=Path)
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    candidate = args.candidate_output.absolute()
    expected = (root / CANDIDATE_RELATIVE).absolute()
    if candidate != expected:
        raise SystemExit(f"candidate output must be {expected}")
    timestamp = datetime.now().astimezone().isoformat()
    report = apply(
        root / SOURCE_RELATIVE,
        root / REVIEW_RELATIVE,
        root / ADJUDICATION_RELATIVE,
        candidate,
        root / REPORT_RELATIVE,
        "9986353321bcb33e200fc0e6b2f7f7e0e82213da",
        timestamp,
    )
    print(
        f"Reviewed candidate created: records={report['counts']['candidate_records']} changes={len(report['changes'])} sha256={report['candidate']['sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
