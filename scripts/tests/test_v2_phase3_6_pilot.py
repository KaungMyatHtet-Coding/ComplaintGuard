from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from pathlib import Path

from scripts.prepare_v2_dataset import (
    annotation_agreement,
    load_annotations,
    load_records,
    path_is_git_ignored,
    validate_pilot,
)

ROOT = Path(__file__).parents[2]
INTAKE_HEADERS = {"recordId", "complaintText", "language", "proposedCategoryId", "sourceType", "sourceName", "sourceReference", "collectionDate", "licenseOrConsentStatus", "privacyReviewStatus", "metadata", "taxonomyVersion"}


def test_intake_templates_are_synthetic_and_match_contract() -> None:
    for name in ("pilot_intake_template.jsonl", "pilot_intake_template.csv"):
        path = ROOT / "data/v2/intake" / name
        rows = load_records(path)
        assert len(rows) == 1
        assert set(rows[0]) == INTAKE_HEADERS
        assert rows[0]["sourceType"] == "synthetic"
        assert "SYNTHETIC EXAMPLE ONLY" in rows[0]["complaintText"]
        assert path_is_git_ignored(path)


def test_annotation_template_headers_and_ignored_paths() -> None:
    expected = {
        "reviewer_a_template.csv": {"recordId", "language", "reviewerACategory", "reviewerAReviewedAt", "taxonomyVersion"},
        "reviewer_b_template.csv": {"recordId", "language", "reviewerBCategory", "reviewerBReviewedAt", "taxonomyVersion"},
        "adjudication_template.csv": {"recordId", "language", "reviewerACategory", "reviewerBCategory", "disagreementState", "adjudicatedFinalCategory", "adjudicatorDecisionReason", "reviewerAReviewedAt", "reviewerBReviewedAt", "adjudicatedAt", "taxonomyVersion"},
    }
    locations = {"reviewer_a_template.csv":"reviewer-a", "reviewer_b_template.csv":"reviewer-b", "adjudication_template.csv":"annotations"}
    for name, headers in expected.items():
        path = ROOT / "data/v2" / locations[name] / name
        with path.open(encoding="utf-8", newline="") as handle:
            assert set(next(csv.reader(handle))) == headers
        assert path_is_git_ignored(path)


def test_source_register_is_aggregate_only() -> None:
    schema = json.loads((ROOT / "data/mapping/v2_source_approval_register_schema.json").read_text(encoding="utf-8"))
    properties = schema["items"]["properties"]
    assert "complaintText" not in properties and "recordId" not in properties
    assert {"approvedAggregateRecordCount", "rejectionCount", "privacyReviewDecision"} <= set(properties)


def test_pilot_validation_is_aggregate_only_and_disagreement_blocks(capsys) -> None:
    record = load_records(ROOT / "data/v2/intake/pilot_intake_template.jsonl")[0]
    annotation = load_annotations(ROOT / "data/v2/annotations/adjudication_template.csv")[0]
    annotation.update(reviewerACategory="cards_atm_pos", reviewerBCategory="mobile_internet_banking", disagreementState="disagreed_unresolved", reviewerAReviewedAt="2026-09-07T01:00:00Z", reviewerBReviewedAt="2026-09-07T01:05:00Z")
    config = json.loads((ROOT / "data/mapping/v2_dataset_readiness_gates_proposed.json").read_text())
    _, report = validate_pilot([record], [annotation], config)
    serialized = json.dumps(report)
    assert record["complaintText"] not in serialized and record["recordId"] not in serialized
    assert report["readiness"]["ready"] is False
    assert report["annotations"]["agreement"]["unresolvedDisagreementCount"] == 1
    assert capsys.readouterr().out == ""


def test_zero_data_pilot_is_blocked() -> None:
    config = json.loads((ROOT / "data/mapping/v2_dataset_readiness_gates_proposed.json").read_text())
    _, report = validate_pilot([], [], config)
    assert report["readiness"]["ready"] is False
    assert report["annotations"]["agreement"] == annotation_agreement([])


def test_rejected_text_never_appears_in_output_or_logs(capsys) -> None:
    rejected = load_records(ROOT / "data/v2/intake/pilot_intake_template.jsonl")[0]
    rejected["complaintText"] = "PRIVATE-REJECTED-TEXT"
    rejected["privacyReviewStatus"] = "failed"
    config = json.loads((ROOT / "data/mapping/v2_dataset_readiness_gates_proposed.json").read_text())
    _, report = validate_pilot([rejected], [], config)
    assert "PRIVATE-REJECTED-TEXT" not in json.dumps(report)
    captured = capsys.readouterr()
    assert "PRIVATE-REJECTED-TEXT" not in captured.out
    assert "PRIVATE-REJECTED-TEXT" not in captured.err


def test_v1_hashes_and_v2_disabled_are_unchanged() -> None:
    expected = {
        "data/mapping/cfpb_department_mapping_v1.json":"5a09d54b5b5c81286dea24abf519dc479fe29fd4ba813f4375ecf154171475f7",
        "data/processed/cfpb_training_v1_manifest.json":"77452092015c71e0c029450cbfd8ca2160e926b972dade5ecb9f8f19cd998e64",
        "data/processed/cfpb_model_v1_metrics.json":"99fc40b8e791fe65ff7ed22e8e5a731ed650351ad577d27322e95f2bdd1550d8",
        "evaluation/day18/model_evaluation_v1.json":"f6b3a872396ba8a8db874bdb0ca00f839a4515c1c77e935ce13cd02d488dae06",
    }
    for relative, digest in expected.items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == digest
    taxonomy = json.loads((ROOT / "data/mapping/myanmar_banking_taxonomy_v2.json").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "data/processed/myanmar_dataset_v2_manifest.json").read_text())
    assert taxonomy["automatic_routing_enabled"] is False
    assert manifest["automatic_routing_enabled"] is False


def test_trackable_phase36_files_do_not_contain_customer_claims() -> None:
    tracked = [ROOT / "data/mapping/v2_source_approval_register_schema.json", ROOT / "docs/v2_phase3_6_pilot_collection_guide.md"]
    prohibited = ("real customer record", "actual customer complaint")
    for path in tracked:
        text = path.read_text(encoding="utf-8").casefold()
        assert not any(value in text for value in prohibited)
