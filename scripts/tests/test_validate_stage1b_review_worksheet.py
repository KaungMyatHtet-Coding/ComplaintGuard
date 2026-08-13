"""Tests for deterministic Stage 1B worksheet preparation and validation."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

import scripts.prepare_stage1b_review_worksheet as prepare
import scripts.validate_stage1b_review_worksheet as validator
from scripts.prepare_stage1b_review_worksheet import (
    EXPECTED_DRAFT_SHA256,
    SHUFFLE_SEED,
    WORKSHEET_COLUMNS,
    build_reference,
    build_worksheet_rows,
    neutral_reasons,
    shuffled_entries,
)
from scripts.validate_stage1b_review_worksheet import (
    PROHIBITED_COLUMNS,
    validate_worksheet,
)


def fixture_sources() -> tuple[dict[str, dict], list[dict]]:
    records = {
        f"SEB-{index:04d}": {
            "example_id": f"SEB-{index:04d}",
            "text": f"Synthetic complaint wording number {index}",
            "word_count": 5,
            "expected_department": "general_support",
            "difficulty": "hard",
        }
        for index in range(1, 74)
    }
    entries = [
        {
            "example_id": record_id,
            "review_categories": ["ambiguity_notes", "hard_label_confirmation"],
        }
        for record_id in records
    ]
    return records, entries


def test_shuffle_is_deterministic_and_not_source_order() -> None:
    _records, entries = fixture_sources()
    first = [entry["example_id"] for entry in shuffled_entries(entries)]
    second = [entry["example_id"] for entry in shuffled_entries(entries)]
    assert first == second
    assert first != [entry["example_id"] for entry in entries]
    assert SHUFFLE_SEED == 20260814


def test_worksheet_is_blind_and_human_fields_are_empty() -> None:
    records, entries = fixture_sources()
    rows = build_worksheet_rows(records, entries)
    assert len(rows) == 73
    assert set(rows[0]) == set(WORKSHEET_COLUMNS)
    assert not (set(rows[0]) & PROHIBITED_COLUMNS)
    for row in rows:
        assert row["reviewer_decision"] == ""
        assert row["reviewer_department"] == ""
        assert row["revised_text"] == ""
        assert row["reviewer_note"] == ""


def test_ambiguity_reason_is_neutralized() -> None:
    entry = {
        "review_categories": [
            "hard_label_confirmation",
            "ambiguity_notes",
            "controlled_variation",
        ]
    }
    assert neutral_reasons(entry) == (
        "ambiguity_review|controlled_variation|hard_label_confirmation"
    )


def test_reference_is_sealed_and_contains_no_model_results() -> None:
    records, entries = fixture_sources()
    reference = build_reference(records, entries)
    assert reference["status"] == "internal_reference_only"
    assert reference["do_not_consult_during_blind_review"] is True
    assert reference["not_human_review_results"] is True
    assert reference["not_approval_evidence"] is True
    assert reference["contains_predictions"] is False
    assert reference["contains_confidence"] is False


def write_fixture_files(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    records, entries = fixture_sources()
    draft = tmp_path / "draft.jsonl"
    draft.write_text(
        "\n".join(json.dumps(record, sort_keys=True) for record in records.values())
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    queue = tmp_path / "queue.json"
    queue.write_text(json.dumps({"entries": entries}), encoding="utf-8")
    worksheet = tmp_path / "worksheet.csv"
    rows = build_worksheet_rows(records, entries)
    with worksheet.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=WORKSHEET_COLUMNS, lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)
    reference = tmp_path / "reference.json"
    reference.write_text(
        json.dumps(build_reference(records, entries)), encoding="utf-8"
    )
    return draft, queue, worksheet, reference


def test_validator_rejects_changed_draft_before_reading_other_files(
    tmp_path: Path,
) -> None:
    draft, queue, worksheet, reference = write_fixture_files(tmp_path)
    assert hashlib.sha256(draft.read_bytes()).hexdigest() != EXPECTED_DRAFT_SHA256
    assert validate_worksheet(worksheet, reference, draft, queue) == [
        "draft benchmark SHA-256 changed"
    ]


def test_validator_accepts_reproducible_blank_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    draft, queue, worksheet, reference = write_fixture_files(tmp_path)
    monkeypatch.setattr(validator, "sha256_file", lambda _path: EXPECTED_DRAFT_SHA256)
    monkeypatch.setattr(prepare, "sha256_file", lambda _path: EXPECTED_DRAFT_SHA256)
    assert validate_worksheet(worksheet, reference, draft, queue) == []


def test_validator_detects_completed_human_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    draft, queue, worksheet, reference = write_fixture_files(tmp_path)
    rows = list(csv.DictReader(worksheet.open("r", encoding="utf-8", newline="")))
    rows[0]["reviewer_decision"] = "approve"
    with worksheet.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=WORKSHEET_COLUMNS, lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)
    monkeypatch.setattr(validator, "sha256_file", lambda _path: EXPECTED_DRAFT_SHA256)
    monkeypatch.setattr(prepare, "sha256_file", lambda _path: EXPECTED_DRAFT_SHA256)
    errors = validate_worksheet(worksheet, reference, draft, queue)
    assert "worksheet rows do not reproduce from the fixed seed and sources" in errors
    assert "human-entry fields are not empty at row 1" in errors
