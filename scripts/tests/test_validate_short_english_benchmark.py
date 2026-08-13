"""Focused tests for the read-only short-English benchmark validator."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.validate_short_english_benchmark import (
    REQUIRED_FIELDS,
    duplicate_normalize,
    load_jsonl,
    near_duplicate_findings,
    normalize_text,
    validate_records,
)


def record(identifier: str, text: str = "Transfer is still pending") -> dict:
    normalized = normalize_text(text)
    return {
        "ambiguity_notes": "",
        "approved": False,
        "author": "project_owner",
        "benchmark_version": "",
        "character_count": len(normalized),
        "difficulty": "easy",
        "duplicate_group": "",
        "example_id": identifier,
        "expected_department": "transfer_payment",
        "ground_truth_rationale": "The complaint concerns a transfer movement failure.",
        "review_status": "pending",
        "reviewer": "pending_delayed_blind_self_review",
        "source_type": "synthetic_authored",
        "split": "final",
        "text": text,
        "variation_tags": [],
        "word_count": len(normalized.split()),
    }


def write_jsonl(path: Path, records: list[dict], *, canonical: bool = True) -> None:
    lines = [
        json.dumps(
            item,
            ensure_ascii=False,
            sort_keys=canonical,
            separators=(",", ":") if canonical else None,
        )
        for item in records
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def test_load_jsonl_requires_canonical_utf8_lf(tmp_path: Path) -> None:
    path = tmp_path / "draft.jsonl"
    write_jsonl(path, [record("SEB-0001")])
    assert load_jsonl(path)[0]["example_id"] == "SEB-0001"
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    with pytest.raises(ValueError, match="LF line endings"):
        load_jsonl(path)


def test_schema_is_exact_and_draft_fields_are_required() -> None:
    item = record("SEB-0001")
    assert frozenset(item) == REQUIRED_FIELDS
    del item["approved"]
    findings = validate_records([item])
    assert any(finding.code == "schema_fields" for finding in findings)


def test_counts_lengths_privacy_and_status_are_checked() -> None:
    item = record("SEB-0001", "Password 123456 belongs here")
    item["approved"] = True
    item["word_count"] = 99
    findings = validate_records([item])
    codes = {finding.code for finding in findings}
    assert {
        "record_count",
        "word_count",
        "sensitive_pattern",
        "prohibited_sensitive_term",
        "draft_status",
    } <= codes


def test_candidate_specific_content_is_rejected() -> None:
    item = record("SEB-0001", "Transformer prediction shaped this complaint")
    findings = validate_records([item])
    assert any(finding.code == "candidate_specific_content" for finding in findings)


def test_exact_and_normalized_duplicates_are_blocking() -> None:
    first = record("SEB-0001", "Transfer is still pending")
    second = record("SEB-0002", "Transfer is still pending!")
    findings = validate_records([first, second])
    assert any(finding.code == "normalized_duplicate" for finding in findings)
    assert duplicate_normalize(first["text"]) == duplicate_normalize(second["text"])


def test_near_duplicate_candidates_are_deterministic() -> None:
    first = record(
        "SEB-0001", "My transfer remains pending after several business days"
    )
    second = record("SEB-0002", "My transfer remains pending after many business days")
    second["expected_department"] = "account_support"
    findings = near_duplicate_findings([first, second])
    assert [finding.code for finding in findings] == ["cross_label_near_duplicate"]
    assert findings[0].example_ids == ("SEB-0001", "SEB-0002")


def test_validation_does_not_rewrite_input(tmp_path: Path) -> None:
    path = tmp_path / "draft.jsonl"
    write_jsonl(path, [record("SEB-0001")])
    before = path.read_bytes()
    records = load_jsonl(path)
    validate_records(records)
    near_duplicate_findings(records)
    assert path.read_bytes() == before
