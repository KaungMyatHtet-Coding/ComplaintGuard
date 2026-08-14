"""Tests for Stage 1B agreement analysis using only synthetic temporary files."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from scripts.analyze_stage1b_review_agreement import (
    LABELS,
    AnalysisError,
    analyze_records,
    build_outputs,
    cohen_kappa,
    deterministic_queue,
)


def synthetic_rows(
    originals: list[str], reviewers: list[str]
) -> tuple[list[dict[str, str]], dict[str, dict], dict[str, dict]]:
    completed = []
    reference = {}
    draft = {}
    for index, (original, reviewer) in enumerate(zip(originals, reviewers), start=1):
        record_id = f"SYN-{index:04d}"
        completed.append(
            {
                "review_order": str(index),
                "record_id": record_id,
                "complaint_text": f"Synthetic complaint {index}",
                "review_reasons": "ambiguity_review|controlled_variation",
                "word_count": "3",
                "reviewer_decision": "approve",
                "reviewer_department": reviewer,
                "revised_text": "",
                "reviewer_note": "",
            }
        )
        reference[record_id] = {
            "review_order": index,
            "record_id": record_id,
            "original_department": original,
            "original_difficulty": "hard",
            "original_review_reasons": ["ambiguity_notes", "controlled_variation"],
            "source_queue_position": index,
        }
        draft[record_id] = {
            "example_id": record_id,
            "text": f"Synthetic complaint {index}",
            "expected_department": original,
            "variation_tags": ["typo"],
        }
    return completed, reference, draft


def test_perfect_agreement() -> None:
    rows, reference, draft = synthetic_rows(list(LABELS), list(LABELS))
    metrics, disagreements = analyze_records(rows, reference, draft)
    assert metrics["agreement_count"] == 6
    assert metrics["exact_agreement_percentage"] == 100.0
    assert metrics["cohens_kappa"] == pytest.approx(1.0)
    assert disagreements == []


def test_partial_disagreement_and_confusion_orientation() -> None:
    originals = ["transfer_payment", "account_support", "card_atm"]
    reviewers = ["transfer_payment", "general_support", "fraud_security"]
    rows, reference, draft = synthetic_rows(originals, reviewers)
    metrics, disagreements = analyze_records(rows, reference, draft)
    matrix = metrics["confusion_matrix"]
    assert metrics["agreement_count"] == 1
    assert len(disagreements) == 2
    assert matrix["orientation"].startswith("rows=original_department")
    assert (
        matrix["values"][LABELS.index("account_support")][
            LABELS.index("general_support")
        ]
        == 1
    )
    assert (
        matrix["values"][LABELS.index("general_support")][
            LABELS.index("account_support")
        ]
        == 0
    )


def test_zero_agreement() -> None:
    originals = list(LABELS)
    reviewers = list(LABELS[1:]) + [LABELS[0]]
    rows, reference, draft = synthetic_rows(originals, reviewers)
    metrics, _ = analyze_records(rows, reference, draft)
    assert metrics["agreement_count"] == 0
    assert metrics["exact_agreement_percentage"] == 0.0
    assert metrics["cohens_kappa"] == pytest.approx(-0.2)


def test_cohen_kappa_known_matrix() -> None:
    matrix = {row: {column: 0 for column in LABELS} for row in LABELS}
    matrix["transfer_payment"]["transfer_payment"] = 20
    matrix["transfer_payment"]["account_support"] = 5
    matrix["account_support"]["transfer_payment"] = 10
    matrix["account_support"]["account_support"] = 15
    assert cohen_kappa(matrix, 50) == pytest.approx(0.4)


def test_deterministic_disagreement_ordering_is_label_independent() -> None:
    items = [
        {
            "record_id": record_id,
            "complaint_text": "Synthetic text",
            "original_department": "card_atm",
            "reviewer_department": "fraud_security",
            "original_difficulty": "hard",
            "review_reasons": ["ambiguity_review"],
            "controlled_variation_flags": [],
        }
        for record_id in ["SYN-0003", "SYN-0001", "SYN-0002"]
    ]
    first = deterministic_queue(items)
    relabeled = [
        {
            **item,
            "original_department": "loan_credit",
            "reviewer_department": "general_support",
        }
        for item in reversed(items)
    ]
    second = deterministic_queue(relabeled)
    assert [item["record_id"] for item in first] == [
        item["record_id"] for item in second
    ]
    assert [item["adjudication_order"] for item in first] == [1, 2, 3]


def fixture_files(tmp_path: Path) -> tuple[dict[str, Path], dict[str, str]]:
    originals = [LABELS[index % len(LABELS)] for index in range(73)]
    completed, reference_by_id, draft_by_id = synthetic_rows(originals, originals)
    completed_path = tmp_path / "completed.csv"
    pristine_path = tmp_path / "pristine.csv"
    fields = list(completed[0])
    for path, rows in ((completed_path, completed), (pristine_path, completed)):
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    reference_records = list(reference_by_id.values())
    reference = {
        "status": "internal_reference_only",
        "do_not_consult_during_blind_review": True,
        "not_human_review_results": True,
        "not_approval_evidence": True,
        "contains_predictions": False,
        "contains_confidence": False,
        "deterministic_shuffle": {"seed": 20260814},
        "source_draft_sha256": "",
        "record_count": 73,
        "records": reference_records,
    }
    draft_path = tmp_path / "draft.jsonl"
    draft_path.write_text(
        "".join(json.dumps(record) + "\n" for record in draft_by_id.values()),
        encoding="utf-8",
        newline="\n",
    )
    draft_hash = hashlib.sha256(draft_path.read_bytes()).hexdigest()
    reference["source_draft_sha256"] = draft_hash
    reference_path = tmp_path / "reference.json"
    reference_path.write_text(json.dumps(reference), encoding="utf-8")
    paths = {
        "completed_review": completed_path,
        "pristine_worksheet": pristine_path,
        "sealed_reference": reference_path,
        "draft_benchmark": draft_path,
    }
    hashes = {
        name: hashlib.sha256(path.read_bytes()).hexdigest()
        for name, path in paths.items()
    }
    return paths, hashes


def run_fixture(paths: dict[str, Path], hashes: dict[str, str]) -> None:
    build_outputs(
        completed_path=paths["completed_review"],
        pristine_path=paths["pristine_worksheet"],
        reference_path=paths["sealed_reference"],
        draft_path=paths["draft_benchmark"],
        expected_hashes={
            "completed_review": hashes["completed_review"],
            "pristine_worksheet": hashes["pristine_worksheet"],
            "draft_benchmark": hashes["draft_benchmark"],
        },
        git_commit="a" * 40,
        unsealed_at="2026-08-14T20:41:42+06:30",
    )


@pytest.mark.parametrize("case", ["missing", "extra", "duplicate"])
def test_record_membership_and_duplicate_errors(tmp_path: Path, case: str) -> None:
    paths, hashes = fixture_files(tmp_path)
    reference = json.loads(paths["sealed_reference"].read_text(encoding="utf-8"))
    if case == "missing":
        reference["records"].pop()
        reference["record_count"] = 72
    elif case == "extra":
        extra = {**reference["records"][0], "record_id": "SYN-9999"}
        reference["records"].append(extra)
        reference["record_count"] = 74
    else:
        reference["records"][1]["record_id"] = reference["records"][0]["record_id"]
    paths["sealed_reference"].write_text(json.dumps(reference), encoding="utf-8")
    with pytest.raises(AnalysisError):
        run_fixture(paths, hashes)


def test_invalid_label(tmp_path: Path) -> None:
    paths, hashes = fixture_files(tmp_path)
    rows = list(
        csv.DictReader(paths["completed_review"].open(encoding="utf-8", newline=""))
    )
    rows[0]["reviewer_department"] = "invalid"
    with paths["completed_review"].open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    hashes["completed_review"] = hashlib.sha256(
        paths["completed_review"].read_bytes()
    ).hexdigest()
    with pytest.raises(AnalysisError, match="invalid reviewer label"):
        run_fixture(paths, hashes)


def test_mismatched_input_hash_and_reference_metadata(tmp_path: Path) -> None:
    paths, hashes = fixture_files(tmp_path)
    bad_hashes = {**hashes, "completed_review": "0" * 64}
    with pytest.raises(AnalysisError, match="protected input hash differs"):
        run_fixture(paths, bad_hashes)
    reference = json.loads(paths["sealed_reference"].read_text(encoding="utf-8"))
    reference["source_draft_sha256"] = "0" * 64
    paths["sealed_reference"].write_text(json.dumps(reference), encoding="utf-8")
    with pytest.raises(AnalysisError, match="source draft SHA-256"):
        run_fixture(paths, hashes)


def test_input_files_remain_unchanged(tmp_path: Path) -> None:
    paths, hashes = fixture_files(tmp_path)
    before = {name: path.read_bytes() for name, path in paths.items()}
    run_fixture(paths, hashes)
    assert {name: path.read_bytes() for name, path in paths.items()} == before


@pytest.mark.parametrize("field", ["prediction", "confidence"])
def test_prediction_or_confidence_data_is_rejected(tmp_path: Path, field: str) -> None:
    paths, hashes = fixture_files(tmp_path)
    reference = json.loads(paths["sealed_reference"].read_text(encoding="utf-8"))
    reference["records"][0][field] = 0.9
    paths["sealed_reference"].write_text(json.dumps(reference), encoding="utf-8")
    with pytest.raises(AnalysisError):
        run_fixture(paths, hashes)
