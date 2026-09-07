from __future__ import annotations
import csv, json, subprocess
from pathlib import Path
import pytest
from scripts.prepare_v2_dataset import CATEGORY_IDS, IntakeValidationError, annotation_agreement, group_and_partition, load_records, normalize_and_redact, prepare_intake, readiness_gates, validate_annotation, validate_record

ROOT = Path(__file__).parents[2]


def candidate(**changes: object) -> dict:
    row = {"recordId":"synthetic-1","complaintText":"Synthetic complaint about a pending intended transfer.","language":"en","proposedCategoryId":"transfers_payments_remittance","sourceType":"synthetic","sourceName":"owner synthetic fixture","sourceReference":"fixture-v1","collectionDate":"2026-09-07","licenseOrConsentStatus":"approved_synthetic_authorization","privacyReviewStatus":"passed","metadata":{"originLanguage":"en","translationMethod":"not_applicable","sourceRecordGroup":"synthetic-family-1"},"taxonomyVersion":"v2"}
    row.update(changes); return row


def test_schema_is_strict_and_taxonomy_is_frozen() -> None:
    assert len(set(CATEGORY_IDS)) == 8
    assert validate_record(candidate())["taxonomyVersion"] == "v2"
    with pytest.raises(IntakeValidationError, match="unknown_or_missing_fields"):
        validate_record({**candidate(), "unexpected": True})


@pytest.mark.parametrize(("changes","code"), [({"sourceReference":""},"missing_provenance"),({"licenseOrConsentStatus":"pending"},"license_or_consent_not_approved"),({"privacyReviewStatus":"failed"},"privacy_review_not_passed"),({"language":"mm"},"unsupported_language"),({"proposedCategoryId":"general_support"},"unsupported_category"),({"complaintText":"too short"},"complaint_text_too_short")])
def test_intake_rejections(changes: dict, code: str) -> None:
    with pytest.raises(IntakeValidationError, match=code): validate_record(candidate(**changes))


def test_privacy_redaction_and_aggregate_rejections_do_not_leak_text() -> None:
    private = "My name is Alice Smith; email alice@example.com; call +95 (9) 123-4567; NRC: 12/ABC(N)123456; transaction id: TXN-998877; address 12 Lake Road."
    redacted, markers = normalize_and_redact(private)
    assert "Alice" not in redacted and "example.com" not in redacted and "998877" not in redacted
    assert {"name","email","nrc_or_passport","transaction_id","address","phone_or_financial_number"} <= markers
    _, report = prepare_intake([candidate(complaintText=private), candidate(recordId="bad", complaintText="secret")])
    serialized = json.dumps(report)
    assert "secret" not in serialized and "Alice" not in serialized
    assert report["acceptedCount"] == report["rejectedCount"] == 1


def test_jsonl_and_csv_are_supported(tmp_path: Path) -> None:
    jsonl = tmp_path / "input.jsonl"; jsonl.write_text(json.dumps(candidate()) + "\n", encoding="utf-8")
    assert load_records(jsonl) == [candidate()]
    csv_path = tmp_path / "input.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=candidate().keys()); writer.writeheader(); row=candidate(); row["metadata"]=json.dumps(row["metadata"]); writer.writerow(row)
    assert load_records(csv_path) == [candidate()]


def test_duplicates_group_before_deterministic_partitioning() -> None:
    rows = [validate_record(candidate(recordId="a")), validate_record(candidate(recordId="b")), validate_record(candidate(recordId="c", complaintText="Synthetic complaint about the pending intended transfer."))]
    first, evidence = group_and_partition(rows, .80); second, _ = group_and_partition(rows, .80)
    assert evidence["exactDuplicatePairs"] == 1 and evidence["nearDuplicatePairs"] >= 1
    assert evidence["crossPartitionDuplicateGroups"] == 0
    assert {row["split"] for row in first} == {row["split"] for row in second}
    assert len({row["duplicateGroupId"] for row in first}) == 1


def test_annotation_disagreement_adjudication_and_equations() -> None:
    fixture = json.loads((ROOT / "data/mapping/v2_annotation_synthetic_fixture.json").read_text(encoding="utf-8"))
    for row in fixture: validate_annotation(row)
    metrics = annotation_agreement(fixture)
    assert metrics["rawAgreementPercentage"] == 50.0
    assert metrics["cohensKappa"] == pytest.approx(1 / 3)
    assert metrics["confusionCounts"]["mobile_internet_banking -> transfers_payments_remittance"] == 1
    assert metrics["perLanguageReviewedCount"] == {"mixed": 1, "my": 1}
    unresolved = {**fixture[1], "disagreementState":"disagreed_unresolved", "adjudicatedFinalCategory":None, "adjudicatorDecisionReason":None, "adjudicatedAt":None}
    validate_annotation(unresolved)
    assert annotation_agreement([unresolved])["unresolvedDisagreementCount"] == 1


def test_zero_review_data_is_not_available() -> None:
    result = annotation_agreement([])
    assert result["available"] is False and result["rawAgreementPercentage"] is None and result["cohensKappa"] is None


def test_readiness_requires_approved_thresholds_and_real_evidence() -> None:
    config = json.loads((ROOT / "data/mapping/v2_dataset_readiness_gates_proposed.json").read_text())
    _, manifest = prepare_intake([])
    result = readiness_gates(manifest, annotation_agreement([]), config)
    assert result["configurationApproved"] is False
    assert result["ready"] is False
    assert result["gates"]["minimumPerCategoryMet"] is False


def test_frozen_v1_evidence_hashes_are_unchanged() -> None:
    import hashlib
    expected = {
        "data/mapping/cfpb_department_mapping_v1.json":"5a09d54b5b5c81286dea24abf519dc479fe29fd4ba813f4375ecf154171475f7",
        "data/processed/cfpb_training_v1_manifest.json":"77452092015c71e0c029450cbfd8ca2160e926b972dade5ecb9f8f19cd998e64",
        "data/processed/cfpb_model_v1_metrics.json":"99fc40b8e791fe65ff7ed22e8e5a731ed650351ad577d27322e95f2bdd1550d8",
        "evaluation/day18/model_evaluation_v1.json":"f6b3a872396ba8a8db874bdb0ca00f839a4515c1c77e935ce13cd02d488dae06",
    }
    for relative, digest in expected.items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == digest


@pytest.mark.parametrize(("path","ignored"), [("data/v2/intake/raw.jsonl",True),("data/v2/prepared/corpus.jsonl",True),("data/v2/annotations/review.csv",True),("data/v2/exports/text.csv",True),("data/v2/reviewer-a/notes.json",True),("data/processed/myanmar_dataset_v2_manifest.json",False),("data/mapping/v2_dataset_intake_schema.json",False)])
def test_git_privacy_ignore_boundaries(path: str, ignored: bool) -> None:
    result = subprocess.run(["git","check-ignore","--no-index","--quiet",path], cwd=ROOT)
    assert (result.returncode == 0) is ignored
