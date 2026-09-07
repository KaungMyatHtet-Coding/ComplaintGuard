"""Local-only V2 intake, privacy preparation, grouping, and agreement evidence."""
from __future__ import annotations

import argparse, csv, hashlib, json, re, subprocess, unicodedata
from collections import Counter
from datetime import date, datetime
from difflib import SequenceMatcher
from pathlib import Path

CATEGORY_IDS = ("account_branch_services", "cards_atm_pos", "mobile_internet_banking", "transfers_payments_remittance", "loans_credit", "fraud_scam_unauthorized", "kyc_verification_restrictions", "general_complaints")
LANGUAGES = ("my", "en", "mixed")
SOURCE_TYPES = ("real_public", "translated", "synthetic")
LICENSE_STATUSES = ("approved_public_license", "approved_owner_consent", "approved_synthetic_authorization")
REQUIRED_FIELDS = frozenset(("recordId", "complaintText", "language", "proposedCategoryId", "sourceType", "sourceName", "sourceReference", "collectionDate", "licenseOrConsentStatus", "privacyReviewStatus", "metadata", "taxonomyVersion"))
SPLITS = (("train", 70), ("calibration", 10), ("validation", 10), ("held_out", 10))
PATTERNS = (
    (re.compile(r"(?i)\b(?:my name is|name\s*:)\s*[A-Z][A-Za-z' -]{2,60}\b"), "[REDACTED_NAME]", "name"),
    (re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"), "[REDACTED_EMAIL]", "email"),
    (re.compile(r"(?i)\b(?:NRC|passport)\s*(?:no\.?\s*)?[:#-]?\s*[A-Z0-9()/ -]{5,}\b"), "[REDACTED_IDENTITY_DOCUMENT]", "nrc_or_passport"),
    (re.compile(r"(?i)\b(?:transaction|txn|reference|ref)\s*(?:id|no\.?)?\s*[:#-]\s*[A-Z0-9-]{5,}\b"), "[REDACTED_TRANSACTION_ID]", "transaction_id"),
    (re.compile(r"(?i)\b\d{1,5}\s+[\w.' -]{2,40}\s+(?:street|st|road|rd|lane|ln|avenue|ave)\b"), "[REDACTED_ADDRESS]", "address"),
    (re.compile(r"(?<!\w)(?:\+?\d[\d(). -]{5,}\d)(?!\w)"), "[REDACTED_PHONE_OR_NUMBER]", "phone_or_financial_number"),
    (re.compile(r"(?<!\d)\d(?:[ -]?\d){7,}(?!\d)"), "[REDACTED_NUMBER]", "account_card_or_long_number"),
)


class IntakeValidationError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def normalize_and_redact(text: str) -> tuple[str, set[str]]:
    value, markers = unicodedata.normalize("NFKC", text), set()
    for pattern, replacement, marker in PATTERNS:
        value, count = pattern.subn(replacement, value)
        if count:
            markers.add(marker)
    return re.sub(r"\s+", " ", value).strip(), markers


def validate_record(record: dict, minimum_length: int = 20, maximum_length: int = 5000) -> dict:
    if set(record) != REQUIRED_FIELDS:
        raise IntakeValidationError("unknown_or_missing_fields")
    checks = ((record["language"] in LANGUAGES, "unsupported_language"), (record["proposedCategoryId"] in CATEGORY_IDS, "unsupported_category"), (record["sourceType"] in SOURCE_TYPES, "unsupported_source_type"), (record["licenseOrConsentStatus"] in LICENSE_STATUSES, "license_or_consent_not_approved"), (record["privacyReviewStatus"] == "passed", "privacy_review_not_passed"), (record["taxonomyVersion"] == "v2", "unsupported_taxonomy_version"))
    for passed, code in checks:
        if not passed:
            raise IntakeValidationError(code)
    if not all(str(record[key]).strip() for key in ("recordId", "sourceName", "sourceReference")):
        raise IntakeValidationError("missing_provenance")
    metadata = record["metadata"]
    if not isinstance(metadata, dict) or set(metadata) - {"originLanguage", "translationMethod", "sourceRecordGroup"}:
        raise IntakeValidationError("invalid_annotator_independent_metadata")
    try:
        date.fromisoformat(str(record["collectionDate"]))
    except ValueError as error:
        raise IntakeValidationError("invalid_collection_date") from error
    text, markers = normalize_and_redact(str(record["complaintText"]))
    if len(text) < minimum_length:
        raise IntakeValidationError("complaint_text_too_short")
    if len(text) > maximum_length:
        raise IntakeValidationError("complaint_text_too_long")
    return {**record, "complaintText": text, "privacyMarkersRedacted": sorted(markers)}


def load_records(path: Path) -> list[dict]:
    if path.suffix.casefold() == ".jsonl":
        return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    if path.suffix.casefold() == ".csv":
        rows = list(csv.DictReader(path.open(encoding="utf-8-sig", newline="")))
        for row in rows:
            row["metadata"] = json.loads(row.get("metadata") or "{}")
        return rows
    raise ValueError("input must be .jsonl or .csv")


def load_annotations(path: Path) -> list[dict]:
    if path.suffix.casefold() == ".jsonl":
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    elif path.suffix.casefold() == ".csv":
        rows = list(csv.DictReader(path.open(encoding="utf-8-sig", newline="")))
        nullable = {"reviewerACategory", "reviewerBCategory", "adjudicatedFinalCategory", "adjudicatorDecisionReason", "reviewerAReviewedAt", "reviewerBReviewedAt", "adjudicatedAt"}
        rows = [{key: (None if key in nullable and value == "" else value) for key, value in row.items()} for row in rows]
    else:
        raise ValueError("annotations must be .jsonl or .csv")
    return rows


def _fingerprint(text: str) -> str:
    return hashlib.sha256(text.casefold().encode()).hexdigest()


def _split(fingerprint: str) -> str:
    bucket, total = int(fingerprint[:8], 16) % 100, 0
    for name, weight in SPLITS:
        total += weight
        if bucket < total:
            return name
    raise AssertionError("partition weights must total 100")


def group_and_partition(records: list[dict], near_threshold: float = .90) -> tuple[list[dict], dict]:
    parent, fingerprints = list(range(len(records))), [_fingerprint(row["complaintText"]) for row in records]
    def root(i: int) -> int:
        while parent[i] != i:
            parent[i], i = parent[parent[i]], parent[i]
        return i
    def union(a: int, b: int) -> None:
        a, b = root(a), root(b)
        if a != b:
            parent[max(a, b)] = min(a, b)
    exact = near = 0
    for right in range(len(records)):
        for left in range(right):
            if fingerprints[left] == fingerprints[right]:
                exact += 1; union(left, right)
            elif SequenceMatcher(None, records[left]["complaintText"].casefold(), records[right]["complaintText"].casefold()).ratio() >= near_threshold:
                near += 1; union(left, right)
    groups: dict[int, list[int]] = {}
    for index in range(len(records)):
        groups.setdefault(root(index), []).append(index)
    prepared = [dict(row) for row in records]
    for members in groups.values():
        group_hash = min(fingerprints[index] for index in members)
        for index in members:
            prepared[index].update(duplicateGroupId=hashlib.sha256(("group-v2:" + group_hash).encode()).hexdigest(), split=_split(group_hash))
    evidence = {"exactDuplicatePairs": exact, "nearDuplicatePairs": near, "duplicateGroups": sum(len(group) > 1 for group in groups.values()), "crossPartitionDuplicateGroups": 0, "checkedBeforePartitioning": True, "nearDuplicateThreshold": near_threshold}
    return prepared, evidence


def prepare_intake(records: list[dict]) -> tuple[list[dict], dict]:
    accepted, reasons = [], Counter()
    for record in records:
        try:
            accepted.append(validate_record(record))
        except IntakeValidationError as error:
            reasons[error.code] += 1
    prepared, duplicates = group_and_partition(accepted)
    manifest = {"manifestSchemaVersion": 2, "datasetVersion": "dataset_v2_candidate", "taxonomyVersion": "v2", "automaticRoutingEnabled": False, "inputCount": len(records), "acceptedCount": len(prepared), "rejectedCount": sum(reasons.values()), "rejectionReasonCounts": dict(sorted(reasons.items())), "countsByLanguage": dict(sorted(Counter(row["language"] for row in prepared).items())), "countsByCategory": dict(sorted(Counter(row["proposedCategoryId"] for row in prepared).items())), "countsBySourceType": dict(sorted(Counter(row["sourceType"] for row in prepared).items())), "countsBySplit": dict(sorted(Counter(row["split"] for row in prepared).items())), "redactionMarkerCounts": dict(sorted(Counter(marker for row in prepared for marker in row["privacyMarkersRedacted"]).items())), "duplicates": duplicates, "complaintTextIncluded": False, "recordIdentifiersIncluded": False}
    return prepared, manifest


def annotation_agreement(rows: list[dict]) -> dict:
    reviewed = [row for row in rows if row.get("reviewerACategory") in CATEGORY_IDS and row.get("reviewerBCategory") in CATEGORY_IDS]
    unavailable = {"available": False, "rawAgreementPercentage": None, "cohensKappa": None, "confusionCounts": {}, "perCategoryReviewedCount": {}, "perLanguageReviewedCount": {}, "unresolvedDisagreementCount": 0}
    if not reviewed:
        return unavailable
    total, agreements = len(reviewed), sum(row["reviewerACategory"] == row["reviewerBCategory"] for row in reviewed)
    a, b = Counter(row["reviewerACategory"] for row in reviewed), Counter(row["reviewerBCategory"] for row in reviewed)
    observed = agreements / total
    expected = sum(a[c] * b[c] for c in CATEGORY_IDS) / total**2
    confusion = Counter(f'{row["reviewerACategory"]} -> {row["reviewerBCategory"]}' for row in reviewed)
    return {"available": True, "rawAgreementPercentage": observed * 100, "cohensKappa": None if expected == 1 else (observed - expected) / (1 - expected), "confusionCounts": dict(sorted(confusion.items())), "perCategoryReviewedCount": dict(sorted(Counter(row["reviewerACategory"] for row in reviewed).items())), "perLanguageReviewedCount": dict(sorted(Counter(row["language"] for row in reviewed).items())), "unresolvedDisagreementCount": sum(row.get("disagreementState") == "disagreed_unresolved" for row in reviewed)}


def readiness_gates(manifest: dict, agreement: dict, configuration: dict) -> dict:
    counts = manifest.get("countsByCategory", {})
    languages = manifest.get("countsByLanguage", {})
    gates = {
        "allProvenanceAndLicenseApproved": manifest.get("rejectionReasonCounts", {}).get("missing_provenance", 0) == 0 and manifest.get("rejectionReasonCounts", {}).get("license_or_consent_not_approved", 0) == 0,
        "allPrivacyReviewsPassed": manifest.get("rejectionReasonCounts", {}).get("privacy_review_not_passed", 0) == 0,
        "zeroUnresolvedDisagreements": agreement.get("available") is True and agreement.get("unresolvedDisagreementCount") == 0,
        "zeroCrossPartitionDuplicateGroups": manifest.get("duplicates", {}).get("crossPartitionDuplicateGroups") == 0,
        "minimumPerCategoryMet": all(counts.get(category, 0) >= configuration["proposed_minimum_per_category"] for category in CATEGORY_IDS),
        "minimumMyanmarCoverageMet": languages.get("my", 0) >= configuration["proposed_minimum_myanmar_records"],
        "minimumMixedCoverageMet": languages.get("mixed", 0) >= configuration["proposed_minimum_mixed_language_records"],
        "classBalanceDocumented": bool(counts),
        "deterministicPartitioning": manifest.get("duplicates", {}).get("checkedBeforePartitioning") is True,
        "lockedDatasetHashAndManifest": bool(manifest.get("lockedDatasetSha256")) and manifest.get("locked") is True,
    }
    approved = configuration.get("status") == "approved"
    return {"configurationApproved": approved, "gates": gates, "ready": approved and all(gates.values())}


def validate_annotation(row: dict) -> None:
    fields = {"recordId", "language", "reviewerACategory", "reviewerBCategory", "disagreementState", "adjudicatedFinalCategory", "adjudicatorDecisionReason", "reviewerAReviewedAt", "reviewerBReviewedAt", "adjudicatedAt", "taxonomyVersion"}
    if set(row) != fields or row["language"] not in LANGUAGES or row["taxonomyVersion"] != "v2":
        raise IntakeValidationError("invalid_annotation_contract")
    categories = (row["reviewerACategory"], row["reviewerBCategory"])
    if any(value is not None and value not in CATEGORY_IDS for value in categories):
        raise IntakeValidationError("invalid_annotation_category")
    state = row["disagreementState"]
    if state == "agreed" and (None in categories or categories[0] != categories[1]):
        raise IntakeValidationError("annotation_state_mismatch")
    if state == "disagreed_unresolved" and (None in categories or categories[0] == categories[1] or row["adjudicatedFinalCategory"] is not None):
        raise IntakeValidationError("annotation_state_mismatch")
    if state == "adjudicated" and (row["adjudicatedFinalCategory"] not in CATEGORY_IDS or not str(row["adjudicatorDecisionReason"] or "").strip() or not row["adjudicatedAt"]):
        raise IntakeValidationError("annotation_state_mismatch")
    for field in ("reviewerAReviewedAt", "reviewerBReviewedAt", "adjudicatedAt"):
        value = row[field]
        if value is not None:
            try:
                datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except ValueError as error:
                raise IntakeValidationError("invalid_annotation_timestamp") from error


def validate_pilot(records: list[dict], annotations: list[dict], configuration: dict) -> tuple[list[dict], dict]:
    prepared, manifest = prepare_intake(records)
    annotation_rejections = Counter()
    valid_annotations = []
    for annotation in annotations:
        try:
            validate_annotation(annotation)
            valid_annotations.append(annotation)
        except IntakeValidationError as error:
            annotation_rejections[error.code] += 1
    agreement = annotation_agreement(valid_annotations)
    readiness = readiness_gates(manifest, agreement, configuration)
    if annotation_rejections or agreement["unresolvedDisagreementCount"]:
        readiness["ready"] = False
    report = {
        "reportSchemaVersion": 1,
        "phase": "3.6-pilot-validation",
        "automaticRoutingEnabled": False,
        "dataset": manifest,
        "annotations": {
            "inputCount": len(annotations),
            "validCount": len(valid_annotations),
            "rejectedCount": sum(annotation_rejections.values()),
            "rejectionReasonCounts": dict(sorted(annotation_rejections.items())),
            "agreement": agreement,
        },
        "pilotProposal": {
            "status": "pending_human_approval",
            "acceptedRecordsPerCategory": 50,
            "totalAcceptedRecords": 400,
            "twoIndependentReviewersRequired": True,
        },
        "readiness": readiness,
        "complaintTextIncluded": False,
        "recordIdentifiersIncluded": False,
        "reviewerIdentifiersIncluded": False,
    }
    return prepared, report


def path_is_git_ignored(path: Path) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "--quiet", str(path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare only a user-provided local V2 JSONL/CSV file; no downloads.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--prepared-output", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--annotations", type=Path)
    parser.add_argument("--readiness-report", type=Path)
    parser.add_argument("--gates", type=Path, default=Path("data/mapping/v2_dataset_readiness_gates_proposed.json"))
    args = parser.parse_args()
    destinations = [args.prepared_output, args.manifest]
    if args.readiness_report:
        destinations.append(args.readiness_report)
    if any(path.exists() for path in destinations):
        raise FileExistsError("refusing to overwrite output")
    if not path_is_git_ignored(args.prepared_output):
        raise ValueError("prepared complaint text must be written inside a Git-ignored path")
    records = load_records(args.input)
    if args.annotations:
        if not args.readiness_report:
            raise ValueError("--readiness-report is required with --annotations")
        prepared, report = validate_pilot(records, load_annotations(args.annotations), json.loads(args.gates.read_text(encoding="utf-8")))
        manifest = report["dataset"]
        args.readiness_report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    else:
        prepared, manifest = prepare_intake(records)
    args.prepared_output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in prepared), encoding="utf-8")
    args.manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__": main()
