"""Tests for deterministic Stage 1B adjudication application."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path

import pytest

from scripts import apply_stage1b_benchmark_adjudication as app


def source_records() -> list[dict]:
    records = []
    for number in range(1, 181):
        record_id = f"SEB-{number:04d}"
        records.append(
            {
                "example_id": record_id,
                "text": f"Synthetic complaint text number {number}",
                "expected_department": "account_support"
                if number == 176
                else "transfer_payment",
                "difficulty": "hard" if number >= 133 else "easy",
                "variation_tags": ["informal"] if number % 7 == 0 else [],
            }
        )
    return records


def evidence(records: list[dict]) -> tuple[list[dict[str, str]], dict]:
    reviewed_ids = [f"SEB-{number:04d}" for number in range(1, 64)] + [
        "SEB-0088",
        "SEB-0136",
        "SEB-0151",
        "SEB-0158",
        "SEB-0160",
        "SEB-0163",
        "SEB-0167",
        "SEB-0176",
        "SEB-0178",
        "SEB-0179",
    ]
    by_id = {record["example_id"]: record for record in records}
    disagreement_ids = set(reviewed_ids[-10:])
    rows = []
    entries = []
    for order, record_id in enumerate(reviewed_ids, start=1):
        source = by_id[record_id]
        reviewer = source["expected_department"]
        if record_id in disagreement_ids:
            reviewer = (
                "fraud_security"
                if source["expected_department"] != "fraud_security"
                else "account_support"
            )
        rows.append(
            {
                "review_order": str(order),
                "record_id": record_id,
                "complaint_text": source["text"],
                "review_reasons": '["ambiguity_review"]',
                "reviewer_decision": "approve",
                "reviewer_department": reviewer,
            }
        )
        if record_id in disagreement_ids:
            use_reviewer = record_id == "SEB-0176"
            entries.append(
                {
                    "record_id": record_id,
                    "complaint_text": source["text"],
                    "original_department": source["expected_department"],
                    "reviewer_department": reviewer,
                    "original_difficulty": source["difficulty"],
                    "controlled_variation_flags": source["variation_tags"],
                    "adjudication_decision": "use_reviewer"
                    if use_reviewer
                    else "keep_original",
                    "final_department": reviewer
                    if use_reviewer
                    else source["expected_department"],
                    "revised_text": "",
                    "adjudication_note": "Synthetic human reason",
                }
            )
    return rows, {"entries": entries}


def write_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, Path, list[dict]]:
    records = source_records()
    rows, adjudication = evidence(records)
    source = tmp_path / "source.jsonl"
    review = tmp_path / "review.csv"
    completed = tmp_path / "adjudication.json"
    source.write_text(
        "\n".join(
            json.dumps(value, sort_keys=True, separators=(",", ":"))
            for value in records
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    import csv

    with review.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    completed.write_text(json.dumps(adjudication), encoding="utf-8")
    monkeypatch.setattr(
        app,
        "EXPECTED_HASHES",
        {
            "source_draft": app.sha256_file(source),
            "completed_review": app.sha256_file(review),
            "completed_adjudication": app.sha256_file(completed),
        },
    )
    return source, review, completed, records


def test_plan_and_candidate_apply_exactly_one_label() -> None:
    records = source_records()
    rows, adjudication = evidence(records)
    plan = app.validate_and_plan(records, rows, adjudication)
    assert plan["classifications"] == {
        "agreement": 63,
        "adjudicated_keep_original": 9,
        "adjudicated_use_reviewer": 1,
        "adjudicated_revise_and_relabel": 0,
        "adjudicated_remove": 0,
        "unresolved": 0,
    }
    candidate, changes = app.derive_candidate(records, plan)
    assert changes == [
        {
            "record_id": "SEB-0176",
            "before_department": "account_support",
            "after_department": "fraud_security",
        }
    ]
    assert (
        sum(left != right for left, right in zip(records, candidate, strict=True)) == 1
    )
    assert candidate[175]["text"] == records[175]["text"]


@pytest.mark.parametrize(
    "mutation,match",
    [
        ("missing_review", "record count"),
        ("extra_review", "record count"),
        ("duplicate_review", "duplicate record ID"),
        ("unresolved", "unresolved or removal decision"),
        ("revised", "invalid adjudication"),
        ("text_change", "complaint text differs"),
    ],
)
def test_inconsistent_evidence_is_rejected(mutation: str, match: str) -> None:
    records = source_records()
    rows, adjudication = evidence(records)
    if mutation == "missing_review":
        rows.pop()
    elif mutation == "extra_review":
        rows.append({**rows[0], "record_id": "SEB-0180"})
    elif mutation == "duplicate_review":
        rows[-1] = copy.deepcopy(rows[0])
    elif mutation == "unresolved":
        adjudication["entries"][0].update(
            adjudication_decision="needs_second_review", final_department="unresolved"
        )
    elif mutation == "revised":
        adjudication["entries"][0]["revised_text"] = "Changed synthetic complaint"
    elif mutation == "text_change":
        rows[0]["complaint_text"] = "Unauthorized change"
    with pytest.raises(app.ApplicationError, match=match):
        app.validate_and_plan(records, rows, adjudication)


def test_output_path_rejects_source_alias_outside_and_hardlink(tmp_path: Path) -> None:
    source = tmp_path / "source.jsonl"
    source.write_text("source", encoding="utf-8")
    with pytest.raises(app.ApplicationError, match="aliases"):
        app.validate_output_path(source, source, tmp_path)
    outside = tmp_path / "other"
    outside.mkdir()
    with pytest.raises(app.ApplicationError, match="outside"):
        app.validate_output_path(source, outside / "candidate.jsonl", tmp_path)
    hardlink = tmp_path / "hardlink.jsonl"
    os.link(source, hardlink)
    with pytest.raises(app.ApplicationError, match="hardlink"):
        app.validate_output_path(source, hardlink, tmp_path)


def test_output_path_rejects_symlink_when_supported(tmp_path: Path) -> None:
    source = tmp_path / "source.jsonl"
    source.write_text("source", encoding="utf-8")
    link = tmp_path / "candidate.jsonl"
    try:
        link.symlink_to(source)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")
    with pytest.raises(app.ApplicationError, match="symlink"):
        app.validate_output_path(source, link, tmp_path)


def test_apply_is_deterministic_atomic_and_preserves_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, review, completed, records = write_inputs(tmp_path, monkeypatch)
    candidate = tmp_path / "candidate.jsonl"
    report = tmp_path / "report.json"
    before = {path: path.read_bytes() for path in (source, review, completed)}
    first = app.apply(
        source,
        review,
        completed,
        candidate,
        report,
        "commit",
        "2026-08-14T00:00:00+06:30",
    )
    first_candidate = candidate.read_bytes()
    first_report = report.read_bytes()
    second = app.apply(
        source,
        review,
        completed,
        candidate,
        report,
        "commit",
        "2026-08-14T00:00:00+06:30",
    )
    assert candidate.read_bytes() == first_candidate
    assert report.read_bytes() == first_report
    assert first == second
    assert all(path.read_bytes() == value for path, value in before.items())
    loaded = app.load_jsonl(candidate)
    assert len(loaded) == 180 and loaded[175]["expected_department"] == "fraud_security"
    assert [record["example_id"] for record in loaded] == [
        record["example_id"] for record in records
    ]
    assert not list(tmp_path.glob(".*.tmp"))


def test_hash_mismatch_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, review, completed, _ = write_inputs(tmp_path, monkeypatch)
    monkeypatch.setitem(app.EXPECTED_HASHES, "source_draft", "0" * 64)
    with pytest.raises(app.ApplicationError, match="SHA-256"):
        app.apply(
            source,
            review,
            completed,
            tmp_path / "candidate.jsonl",
            tmp_path / "report.json",
            "commit",
            "timestamp",
        )


def test_spot_check_is_deterministic_and_includes_changed_record() -> None:
    records = source_records()
    rows, adjudication = evidence(records)
    plan = app.validate_and_plan(records, rows, adjudication)
    source_by_id = {record["example_id"]: record for record in records}
    review_by_id = {row["record_id"]: row for row in rows}
    first = app.select_spot_checks(
        source_by_id, review_by_id, plan["agreement_ids"], ["SEB-0176"]
    )
    second = app.select_spot_checks(
        source_by_id, review_by_id, plan["agreement_ids"], ["SEB-0176"]
    )
    assert first == second and len(first) == 12 and first[0] == "SEB-0176"
