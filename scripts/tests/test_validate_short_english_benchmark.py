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
    sha256_file,
    validate_records,
    validate_reviewed_candidate_evidence,
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


def evidence_records() -> list[dict]:
    values = [
        record("SEB-0001", "Account access remains unavailable"),
        record("SEB-0002", "Unknown activity appeared on account"),
        record("SEB-0003", "Transfer remains pending today"),
        record("SEB-0004", "Loan payment was marked late"),
    ]
    labels = ["account_support", "fraud_security", "transfer_payment", "loan_credit"]
    for item, label in zip(values, labels, strict=True):
        item["expected_department"] = label
    return values


def adjudication_entry(
    source: dict,
    *,
    decision: str = "use_reviewer",
    reviewer: str = "fraud_security",
    final: str = "fraud_security",
    revised: str = "",
) -> dict:
    return {
        "record_id": source["example_id"],
        "complaint_text": source["text"],
        "original_department": source["expected_department"],
        "reviewer_department": reviewer,
        "original_difficulty": source["difficulty"],
        "controlled_variation_flags": source["variation_tags"],
        "adjudication_decision": decision,
        "final_department": final,
        "revised_text": revised,
        "adjudication_note": "Synthetic human adjudication note",
    }


def write_evidence_fixture(
    tmp_path: Path,
    source: list[dict],
    entries: list[dict],
) -> tuple[Path, Path]:
    source_path = tmp_path / "source.jsonl"
    adjudication_path = tmp_path / "adjudication.json"
    write_jsonl(source_path, source)
    adjudication_path.write_text(
        json.dumps({"entries": entries}), encoding="utf-8", newline="\n"
    )
    return source_path, adjudication_path


def validate_fixture(
    tmp_path: Path,
    source: list[dict],
    candidate: list[dict],
    entries: list[dict],
):
    source_path, adjudication_path = write_evidence_fixture(tmp_path, source, entries)
    return validate_reviewed_candidate_evidence(
        candidate,
        source_path=source_path,
        adjudication_path=adjudication_path,
        expected_source_sha256=sha256_file(source_path),
        expected_adjudication_sha256=sha256_file(adjudication_path),
        expected_source_count=len(source),
    )


def authorized_candidate(source: list[dict]) -> tuple[list[dict], list[dict]]:
    candidate = json.loads(json.dumps(source))
    candidate[0]["expected_department"] = "fraud_security"
    entries = [
        adjudication_entry(source[0]),
        adjudication_entry(
            source[1],
            decision="keep_original",
            reviewer="account_support",
            final="fraud_security",
        ),
    ]
    return candidate, entries


def test_real_shape_authorized_one_label_change_passes(tmp_path: Path) -> None:
    source = evidence_records()
    candidate, entries = authorized_candidate(source)
    result = validate_fixture(tmp_path, source, candidate, entries)
    assert result.authorized_changes == (
        {
            "record_id": "SEB-0001",
            "before_department": "account_support",
            "after_department": "fraud_security",
        },
    )
    assert result.expected_label_counts["fraud_security"] == 2
    assert result.leakage_carry_forward_allowed is True


def test_missing_authorized_change_fails(tmp_path: Path) -> None:
    source = evidence_records()
    _, entries = authorized_candidate(source)
    with pytest.raises(ValueError, match="missing changes"):
        validate_fixture(tmp_path, source, source, entries)


@pytest.mark.parametrize(
    "mutation",
    [
        "unauthorized",
        "count_preserving_swap",
        "wrong_changed_record",
        "excessive",
        "arbitrary",
    ],
)
def test_unauthorized_label_changes_fail(tmp_path: Path, mutation: str) -> None:
    source = evidence_records()
    candidate, entries = authorized_candidate(source)
    if mutation == "unauthorized":
        candidate[2]["expected_department"] = "general_support"
    elif mutation == "count_preserving_swap":
        candidate[2]["expected_department"], candidate[3]["expected_department"] = (
            candidate[3]["expected_department"],
            candidate[2]["expected_department"],
        )
    elif mutation == "wrong_changed_record":
        candidate[0]["expected_department"] = source[0]["expected_department"]
        candidate[2]["expected_department"] = "fraud_security"
    elif mutation == "excessive":
        for item in candidate:
            item["expected_department"] = "fraud_security"
    else:
        candidate[3]["expected_department"] = "card_atm"
    with pytest.raises(ValueError, match="unauthorized or missing changes"):
        validate_fixture(tmp_path, source, candidate, entries)


@pytest.mark.parametrize(
    "mutation,match",
    [
        ("missing", "record count"),
        ("extra", "record count"),
        ("duplicate", "duplicate record ID"),
        ("reordered", "ordering differs"),
    ],
)
def test_candidate_membership_and_order_fail(
    tmp_path: Path, mutation: str, match: str
) -> None:
    source = evidence_records()
    candidate, entries = authorized_candidate(source)
    if mutation == "missing":
        candidate.pop()
    elif mutation == "extra":
        candidate.append(record("SEB-0005", "Extra synthetic complaint"))
    elif mutation == "duplicate":
        candidate[-1]["example_id"] = candidate[-2]["example_id"]
    else:
        candidate[1], candidate[2] = candidate[2], candidate[1]
    with pytest.raises(ValueError, match=match):
        validate_fixture(tmp_path, source, candidate, entries)


@pytest.mark.parametrize(
    "field,value",
    [
        ("text", "Unauthorized complaint text change"),
        ("ground_truth_rationale", "Unauthorized metadata change"),
        ("approved", True),
        ("review_status", "approved"),
        ("benchmark_version", "1.0.0"),
    ],
)
def test_unauthorized_text_metadata_and_final_state_fail(
    tmp_path: Path, field: str, value: object
) -> None:
    source = evidence_records()
    candidate, entries = authorized_candidate(source)
    candidate[2][field] = value
    with pytest.raises(ValueError, match="unauthorized or missing changes"):
        validate_fixture(tmp_path, source, candidate, entries)


def test_revised_text_requires_fresh_leakage_screening(tmp_path: Path) -> None:
    source = evidence_records()
    candidate = json.loads(json.dumps(source))
    revised = "Account access remains unavailable after closure"
    candidate[0]["text"] = revised
    candidate[0]["word_count"] = len(normalize_text(revised).split())
    candidate[0]["character_count"] = len(normalize_text(revised))
    entries = [
        adjudication_entry(
            source[0],
            decision="revise_and_relabel",
            final="fraud_security",
            revised=revised,
        )
    ]
    candidate[0]["expected_department"] = "fraud_security"
    with pytest.raises(ValueError, match="fresh leakage screening"):
        validate_fixture(tmp_path, source, candidate, entries)


def test_candidate_boolean_cannot_bypass_evidence_validation() -> None:
    with pytest.raises(TypeError, match="reviewed_candidate"):
        validate_records([], reviewed_candidate=True)  # type: ignore[call-arg]


@pytest.mark.parametrize(
    "defect,match",
    [
        ("keep_change", "keep_original contract"),
        ("wrong_reviewer_final", "use_reviewer contract"),
        ("unresolved", "unresolved adjudication"),
        ("unknown", "unknown record"),
        ("duplicate", "duplicate record ID"),
    ],
)
def test_invalid_adjudication_relationships_fail(
    tmp_path: Path, defect: str, match: str
) -> None:
    source = evidence_records()
    candidate, entries = authorized_candidate(source)
    if defect == "keep_change":
        entries[0].update(adjudication_decision="keep_original")
    elif defect == "wrong_reviewer_final":
        entries[0]["final_department"] = "loan_credit"
    elif defect == "unresolved":
        entries[0].update(
            adjudication_decision="needs_second_review", final_department="unresolved"
        )
    elif defect == "unknown":
        entries[0]["record_id"] = "SEB-9999"
    else:
        entries.append(json.loads(json.dumps(entries[0])))
    with pytest.raises(ValueError, match=match):
        validate_fixture(tmp_path, source, candidate, entries)


def test_missing_adjudication_relationship_fails(tmp_path: Path) -> None:
    source = evidence_records()
    candidate, _ = authorized_candidate(source)
    with pytest.raises(ValueError, match="unauthorized or missing changes"):
        validate_fixture(tmp_path, source, candidate, [])


@pytest.mark.parametrize("which", ["source", "adjudication"])
def test_protected_hash_mismatch_fails(tmp_path: Path, which: str) -> None:
    source = evidence_records()
    candidate, entries = authorized_candidate(source)
    source_path, adjudication_path = write_evidence_fixture(tmp_path, source, entries)
    expected_source = sha256_file(source_path)
    expected_adjudication = sha256_file(adjudication_path)
    if which == "source":
        expected_source = "0" * 64
    else:
        expected_adjudication = "0" * 64
    with pytest.raises(ValueError, match="SHA-256"):
        validate_reviewed_candidate_evidence(
            candidate,
            source_path=source_path,
            adjudication_path=adjudication_path,
            expected_source_sha256=expected_source,
            expected_adjudication_sha256=expected_adjudication,
            expected_source_count=len(source),
        )


def test_original_draft_and_final_state_protections_remain() -> None:
    item = record("SEB-0001")
    original_codes = {finding.code for finding in validate_records([item])}
    assert "label_balance" in original_codes
    item["approved"] = True
    item["review_status"] = "approved"
    item["benchmark_version"] = "1.0.0"
    protected_codes = {finding.code for finding in validate_records([item])}
    assert {"draft_status", "benchmark_version"} <= protected_codes
