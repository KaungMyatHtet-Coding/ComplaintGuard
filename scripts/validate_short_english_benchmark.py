"""Validate and review the draft short-English benchmark without rewriting it."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "draft-review-v1"
LABELS = (
    "transfer_payment",
    "account_support",
    "card_atm",
    "fraud_security",
    "loan_credit",
    "general_support",
)
REQUIRED_FIELDS = frozenset(
    {
        "example_id",
        "text",
        "expected_department",
        "word_count",
        "character_count",
        "difficulty",
        "ambiguity_notes",
        "source_type",
        "author",
        "reviewer",
        "split",
        "duplicate_group",
        "approved",
        "benchmark_version",
        "ground_truth_rationale",
        "variation_tags",
        "review_status",
    }
)
DIFFICULTY_COUNTS = {"easy": 60, "medium": 72, "hard": 48}
PER_LABEL_DIFFICULTY = {"easy": 10, "medium": 12, "hard": 8}
VARIATION_COUNTS = {"typo": 18, "abbreviation": 18, "informal": 27}
ALLOWED_VARIATION_TAGS = frozenset({"typo", "abbreviation", "informal"})
ID_PATTERN = re.compile(r"^SEB-(\d{4})$")
EMAIL_PATTERN = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
PHONE_PATTERN = re.compile(r"(?<!\w)(?:\+?\d[\s().-]*){7,}(?!\w)")
LONG_NUMBER_PATTERN = re.compile(r"(?<!\w)\d(?:[\s-]?\d){5,}(?!\w)")
SECRET_PATTERN = re.compile(
    r"(?i)\b(?:password|passcode|pin|security code|cvv|cvc|api key|access token|"
    r"auth token|private key|account number|card number|loan number|nrc)\b"
)
ABSOLUTE_PATH_PATTERN = re.compile(r"(?:[A-Za-z]:\\Users\\|/home/)[^\s]+")
CANDIDATE_TERM_PATTERN = re.compile(
    r"(?i)\b(?:tf-idf|naive bayes|transformer|embedding|character n-gram|"
    r"candidate model|classifier prediction)\b"
)
WORD_PATTERN = re.compile(r"\S+")
PUNCTUATION_PATTERN = re.compile(r"[^\w\s]", re.UNICODE)
TEXT_FILE_SUFFIXES = {
    ".md",
    ".txt",
    ".json",
    ".jsonl",
    ".csv",
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".mjs",
}


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    message: str
    example_ids: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "example_ids": list(self.example_ids),
        }


def normalize_text(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def duplicate_normalize(text: str) -> str:
    normalized = normalize_text(text)
    return " ".join(PUNCTUATION_PATTERN.sub(" ", normalized).split())


def word_count(text: str) -> int:
    return len(WORD_PATTERN.findall(normalize_text(text)))


def character_count(text: str) -> int:
    return len(normalize_text(text))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError("UTF-8 BOM is not allowed")
    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("dataset is not valid UTF-8") from exc
    if b"\r" in raw or (raw and not raw.endswith(b"\n")):
        raise ValueError("dataset must use LF line endings and end with LF")
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(decoded.splitlines(), start=1):
        if not line:
            raise ValueError(f"blank line at {line_number}")
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON at line {line_number}") from exc
        if not isinstance(value, dict):
            raise TypeError(f"line {line_number} is not a JSON object")
        canonical = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        if line != canonical:
            raise ValueError(f"line {line_number} is not canonical JSON")
        records.append(value)
    return records


def _add(
    findings: list[Finding],
    severity: str,
    code: str,
    message: str,
    *example_ids: str,
) -> None:
    findings.append(Finding(severity, code, message, tuple(example_ids)))


def validate_records(records: list[dict[str, Any]]) -> list[Finding]:
    findings: list[Finding] = []
    if len(records) != 180:
        _add(findings, "error", "record_count", f"expected 180, found {len(records)}")
    ids: list[str] = []
    texts: dict[str, list[str]] = {}
    normalized_texts: dict[str, list[str]] = {}
    label_counts: Counter[str] = Counter()
    difficulty_counts: Counter[str] = Counter()
    label_difficulty: Counter[tuple[str, str]] = Counter()
    variation_counts: Counter[str] = Counter()
    controlled_ids: set[str] = set()
    duplicate_groups: dict[str, list[str]] = {}
    length_bands: Counter[str] = Counter()

    for position, record in enumerate(records, start=1):
        record_id = str(record.get("example_id", f"line-{position}"))
        fields = frozenset(record)
        if fields != REQUIRED_FIELDS:
            _add(
                findings,
                "error",
                "schema_fields",
                f"missing={sorted(REQUIRED_FIELDS - fields)}, unexpected={sorted(fields - REQUIRED_FIELDS)}",
                record_id,
            )
            continue
        match = ID_PATTERN.fullmatch(record_id)
        if match is None or int(match.group(1)) != position:
            _add(
                findings,
                "error",
                "canonical_id_order",
                "ID must match canonical line position",
                record_id,
            )
        ids.append(record_id)
        label = record["expected_department"]
        if label not in LABELS:
            _add(
                findings,
                "error",
                "invalid_label",
                f"unsupported label {label!r}",
                record_id,
            )
        else:
            label_counts[label] += 1
        difficulty = record["difficulty"]
        if difficulty not in DIFFICULTY_COUNTS:
            _add(
                findings,
                "error",
                "invalid_difficulty",
                f"invalid difficulty {difficulty!r}",
                record_id,
            )
        else:
            difficulty_counts[difficulty] += 1
            label_difficulty[(label, difficulty)] += 1
        text = record["text"]
        if not isinstance(text, str) or not text.strip():
            _add(
                findings,
                "error",
                "invalid_text",
                "text must be a non-empty string",
                record_id,
            )
            continue
        actual_words = word_count(text)
        actual_characters = character_count(text)
        if record["word_count"] != actual_words:
            _add(
                findings,
                "error",
                "word_count",
                f"stored={record['word_count']}, actual={actual_words}",
                record_id,
            )
        if record["character_count"] != actual_characters:
            _add(
                findings,
                "error",
                "character_count",
                f"stored={record['character_count']}, actual={actual_characters}",
                record_id,
            )
        if not 3 <= actual_words <= 20 or not 15 <= actual_characters <= 140:
            _add(
                findings,
                "error",
                "short_length",
                f"words={actual_words}, characters={actual_characters}",
                record_id,
            )
        length_bands[
            "3-6" if actual_words <= 6 else "7-13" if actual_words <= 13 else "14-20"
        ] += 1
        if not re.search(r"[A-Za-z]", text) or re.search(r"[^\x00-\x7f]", text):
            _add(
                findings,
                "error",
                "english_ascii",
                "text must be English ASCII",
                record_id,
            )
        exact = normalize_text(text)
        duplicate = duplicate_normalize(text)
        texts.setdefault(exact, []).append(record_id)
        normalized_texts.setdefault(duplicate, []).append(record_id)
        if (
            EMAIL_PATTERN.search(text)
            or PHONE_PATTERN.search(text)
            or LONG_NUMBER_PATTERN.search(text)
        ):
            _add(
                findings,
                "error",
                "sensitive_pattern",
                "email, phone, or long-number pattern detected",
                record_id,
            )
        if SECRET_PATTERN.search(text) or ABSOLUTE_PATH_PATTERN.search(text):
            _add(
                findings,
                "error",
                "prohibited_sensitive_term",
                "credential, identifier, or private-path term detected",
                record_id,
            )
        candidate_metadata = " ".join(
            (
                text,
                str(record["ground_truth_rationale"]),
                str(record["ambiguity_notes"]),
            )
        )
        if CANDIDATE_TERM_PATTERN.search(candidate_metadata):
            _add(
                findings,
                "error",
                "candidate_specific_content",
                "candidate architecture or prediction terminology detected",
                record_id,
            )
        tags = record["variation_tags"]
        if (
            not isinstance(tags, list)
            or tags != sorted(set(tags))
            or set(tags) - ALLOWED_VARIATION_TAGS
        ):
            _add(
                findings,
                "error",
                "variation_tags",
                "tags must be unique, sorted, and allowed",
                record_id,
            )
        else:
            for tag in tags:
                variation_counts[tag] += 1
            if tags:
                controlled_ids.add(record_id)
            if len(tags) > 2:
                _add(
                    findings,
                    "error",
                    "variation_limit",
                    "more than two deliberate deviations",
                    record_id,
                )
        if record["source_type"] != "synthetic_authored":
            _add(
                findings,
                "error",
                "source_type",
                "source_type must be synthetic_authored",
                record_id,
            )
        if record["split"] != "final":
            _add(
                findings,
                "error",
                "split",
                "draft intended-use split must be final",
                record_id,
            )
        if record["approved"] is not False or record["review_status"] != "pending":
            _add(
                findings,
                "error",
                "draft_status",
                "record must be unapproved and pending",
                record_id,
            )
        if record["benchmark_version"] != "":
            _add(
                findings,
                "error",
                "benchmark_version",
                "draft benchmark version must be empty",
                record_id,
            )
        if (
            record["author"] != "project_owner"
            or record["reviewer"] != "pending_delayed_blind_self_review"
        ):
            _add(
                findings,
                "error",
                "review_roles",
                "draft author/reviewer roles are invalid",
                record_id,
            )
        if (
            not isinstance(record["ground_truth_rationale"], str)
            or not record["ground_truth_rationale"].strip()
        ):
            _add(
                findings,
                "error",
                "rationale",
                "ground-truth rationale is required",
                record_id,
            )
        ambiguity = record["ambiguity_notes"]
        if not isinstance(ambiguity, str):
            _add(
                findings,
                "error",
                "ambiguity_type",
                "ambiguity_notes must be a string",
                record_id,
            )
        elif difficulty == "hard" and not ambiguity.strip():
            _add(
                findings,
                "warning",
                "hard_without_ambiguity_note",
                "hard example needs label-confirmation review",
                record_id,
            )
        group = record["duplicate_group"]
        if not isinstance(group, str):
            _add(
                findings,
                "error",
                "duplicate_group_type",
                "duplicate_group must be a string",
                record_id,
            )
        elif group:
            duplicate_groups.setdefault(group, []).append(record_id)

    if len(ids) != len(set(ids)):
        _add(findings, "error", "duplicate_id", "example IDs are not unique")
    if label_counts != Counter({label: 30 for label in LABELS}):
        _add(
            findings, "error", "label_balance", f"label counts are {dict(label_counts)}"
        )
    if difficulty_counts != Counter(DIFFICULTY_COUNTS):
        _add(
            findings,
            "error",
            "difficulty_balance",
            f"difficulty counts are {dict(difficulty_counts)}",
        )
    for label in LABELS:
        actual = {
            difficulty: label_difficulty[(label, difficulty)]
            for difficulty in DIFFICULTY_COUNTS
        }
        if actual != PER_LABEL_DIFFICULTY:
            _add(findings, "error", "label_difficulty_balance", f"{label}: {actual}")
    if length_bands != Counter({"3-6": 45, "7-13": 90, "14-20": 45}):
        _add(
            findings,
            "error",
            "length_distribution",
            f"length bands are {dict(length_bands)}",
        )
    if variation_counts != Counter(VARIATION_COUNTS):
        _add(
            findings,
            "error",
            "variation_distribution",
            f"variation counts are {dict(variation_counts)}",
        )
    if len(controlled_ids) > 45:
        _add(
            findings,
            "error",
            "controlled_variation_union",
            f"controlled variation appears in {len(controlled_ids)} records",
        )
    for value, value_ids in texts.items():
        if len(value_ids) > 1:
            _add(
                findings,
                "error",
                "exact_duplicate",
                f"exact duplicate: {value!r}",
                *value_ids,
            )
    for value, value_ids in normalized_texts.items():
        if len(value_ids) > 1:
            _add(
                findings,
                "error",
                "normalized_duplicate",
                f"normalized duplicate: {value!r}",
                *value_ids,
            )
    for group, group_ids in duplicate_groups.items():
        if len(group_ids) < 2:
            _add(
                findings,
                "error",
                "orphan_duplicate_group",
                f"group {group!r} has one member",
                *group_ids,
            )
    return findings


def near_duplicate_findings(records: list[dict[str, Any]]) -> list[Finding]:
    findings: list[Finding] = []
    prepared = [
        (
            record["example_id"],
            record["expected_department"],
            duplicate_normalize(record["text"]),
        )
        for record in records
    ]
    for index, (left_id, left_label, left_text) in enumerate(prepared):
        left_tokens = set(left_text.split())
        for right_id, right_label, right_text in prepared[index + 1 :]:
            right_tokens = set(right_text.split())
            union = left_tokens | right_tokens
            jaccard = len(left_tokens & right_tokens) / len(union) if union else 1.0
            ratio = SequenceMatcher(None, left_text, right_text, autojunk=False).ratio()
            if jaccard >= 0.72 or ratio >= 0.86:
                severity = "warning"
                code = (
                    "cross_label_near_duplicate"
                    if left_label != right_label
                    else "near_duplicate"
                )
                _add(
                    findings,
                    severity,
                    code,
                    f"token_jaccard={jaccard:.3f}, sequence_ratio={ratio:.3f}",
                    left_id,
                    right_id,
                )
    return findings


def _iter_repository_texts(
    repository_root: Path, excluded: set[Path]
) -> Iterable[tuple[str, str]]:
    for path in sorted(repository_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in TEXT_FILE_SUFFIXES:
            continue
        if any(
            part in {".git", ".venv", "node_modules", ".next"} for part in path.parts
        ):
            continue
        if path.resolve() in excluded or path.stat().st_size > 5_000_000:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        for line in content.splitlines():
            candidate = line.strip().strip("\"'` ,[](){}")
            if 3 <= len(candidate.split()) <= 40 and re.search(r"[A-Za-z]", candidate):
                yield path.relative_to(repository_root).as_posix(), candidate


def repository_leakage_findings(
    records: list[dict[str, Any]], repository_root: Path, excluded: set[Path]
) -> tuple[list[Finding], dict[str, Any]]:
    findings: list[Finding] = []
    targets = {
        normalize_text(record["text"]): record["example_id"] for record in records
    }
    normalized_targets = {
        duplicate_normalize(record["text"]): record["example_id"] for record in records
    }
    files_checked: set[str] = set()
    lines_checked = 0
    for source, text in _iter_repository_texts(repository_root, excluded):
        files_checked.add(source)
        lines_checked += 1
        exact = normalize_text(text)
        duplicate = duplicate_normalize(text)
        record_id = targets.get(exact)
        if record_id:
            _add(
                findings,
                "error",
                "repository_exact_overlap",
                f"overlap with {source}",
                record_id,
            )
        elif duplicate in normalized_targets:
            _add(
                findings,
                "error",
                "repository_normalized_overlap",
                f"normalized overlap with {source}",
                normalized_targets[duplicate],
            )
    return findings, {
        "method": "local repository text-line exact and normalized scan",
        "files_checked": len(files_checked),
        "candidate_lines_checked": lines_checked,
        "excluded_generated_paths": sorted(
            path.relative_to(repository_root.resolve()).as_posix() for path in excluded
        ),
    }


def corpus_leakage_findings(
    records: list[dict[str, Any]], corpus_path: Path | None
) -> tuple[list[Finding], dict[str, Any]]:
    if corpus_path is None or not corpus_path.is_file():
        return [], {
            "status": "not_checked",
            "reason": "mapped training corpus is unavailable",
            "rows_checked": 0,
        }
    targets = {
        normalize_text(record["text"]): record["example_id"] for record in records
    }
    findings: list[Finding] = []
    rows_checked = 0
    with corpus_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != ["Consumer complaint narrative", "department_label"]:
            raise ValueError("mapped corpus schema is unexpected")
        for row in reader:
            rows_checked += 1
            normalized = normalize_text(row["Consumer complaint narrative"])
            record_id = targets.get(normalized)
            if record_id:
                _add(
                    findings,
                    "error",
                    "mapped_corpus_exact_overlap",
                    "exact normalized overlap with mapped corpus",
                    record_id,
                )
    return findings, {
        "status": "checked",
        "method": "streamed NFKC/case-fold/whitespace exact comparison",
        "path": corpus_path.as_posix(),
        "rows_checked": rows_checked,
        "near_overlap_checked": False,
    }


def summarize(
    dataset_path: Path,
    records: list[dict[str, Any]],
    findings: list[Finding],
    leakage: dict[str, Any],
) -> dict[str, Any]:
    label_counts = Counter(record["expected_department"] for record in records)
    difficulty_counts = Counter(record["difficulty"] for record in records)
    variation_counts = Counter(
        tag for record in records for tag in record["variation_tags"]
    )
    source_counts = Counter(record["source_type"] for record in records)
    words = [record["word_count"] for record in records]
    characters = [record["character_count"] for record in records]
    length_bands = Counter(
        "3-6" if value <= 6 else "7-13" if value <= 13 else "14-20" for value in words
    )
    severity_counts = Counter(finding.severity for finding in findings)
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "draft_review_pending",
        "dataset_path": dataset_path.as_posix(),
        "draft_review_sha256": sha256_file(dataset_path),
        "hash_status": "draft review identity only; not a frozen benchmark hash",
        "record_count": len(records),
        "per_label_counts": {label: label_counts[label] for label in LABELS},
        "difficulty_distribution": dict(sorted(difficulty_counts.items())),
        "length_distribution": dict(sorted(length_bands.items())),
        "word_count": {"minimum": min(words), "maximum": max(words)},
        "character_count": {"minimum": min(characters), "maximum": max(characters)},
        "variation_distribution": dict(sorted(variation_counts.items())),
        "controlled_variation_record_count": sum(
            bool(record["variation_tags"]) for record in records
        ),
        "source_type_distribution": dict(sorted(source_counts.items())),
        "exact_duplicate_count": sum(f.code == "exact_duplicate" for f in findings),
        "normalized_duplicate_count": sum(
            f.code == "normalized_duplicate" for f in findings
        ),
        "near_duplicate_candidate_count": sum(
            f.code == "near_duplicate" for f in findings
        ),
        "cross_label_similarity_warning_count": sum(
            f.code == "cross_label_near_duplicate" for f in findings
        ),
        "privacy_error_count": sum(
            f.code in {"sensitive_pattern", "prohibited_sensitive_term"}
            for f in findings
        ),
        "leakage": leakage,
        "structural_validation": "pass" if severity_counts["error"] == 0 else "fail",
        "blocking_error_count": severity_counts["error"],
        "human_review_warning_count": severity_counts["warning"],
        "informational_finding_count": severity_counts["info"],
        "findings": [finding.as_dict() for finding in findings],
        "validator": {
            "path": "scripts/validate_short_english_benchmark.py",
            "version": SCHEMA_VERSION,
            "candidate_predictions_consulted": False,
        },
        "freeze_status": "unfrozen",
        "human_review_status": "pending",
    }


def build_review_queue(
    records: list[dict[str, Any]], findings: list[Finding], leakage: dict[str, Any]
) -> dict[str, Any]:
    by_id = {record["example_id"]: record for record in records}
    categories: dict[str, set[str]] = {
        "ambiguity_notes": {
            record["example_id"] for record in records if record["ambiguity_notes"]
        },
        "hard_label_confirmation": {
            record["example_id"] for record in records if record["difficulty"] == "hard"
        },
        "controlled_variation": {
            record["example_id"] for record in records if record["variation_tags"]
        },
        "unusual_length": {
            record["example_id"]
            for record in records
            if record["word_count"] in {3, 20} or record["character_count"] >= 130
        },
        "near_duplicate_candidates": set(),
        "cross_label_similarity": set(),
    }
    for finding in findings:
        if finding.code == "near_duplicate":
            categories["near_duplicate_candidates"].update(finding.example_ids)
        elif finding.code == "cross_label_near_duplicate":
            categories["cross_label_similarity"].update(finding.example_ids)
    entries = []
    all_ids = sorted(set().union(*categories.values()))
    for record_id in all_ids:
        record = by_id[record_id]
        entries.append(
            {
                "example_id": record_id,
                "expected_department": record["expected_department"],
                "difficulty": record["difficulty"],
                "variation_tags": record["variation_tags"],
                "ambiguity_notes": record["ambiguity_notes"],
                "review_categories": sorted(
                    name for name, values in categories.items() if record_id in values
                ),
                "review_status": "pending",
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "pending_delayed_blind_self_review",
        "independent_reviewer_available": False,
        "dataset_text_included": False,
        "queue_size": len(entries),
        "category_counts": {name: len(values) for name, values in categories.items()},
        "unresolved_leakage_limitations": [
            "Near-duplicate screening against the 3.8-million-row mapped corpus was not performed.",
            "Raw CFPB source data was not scanned.",
        ],
        "leakage_summary": leakage,
        "entries": entries,
    }


def write_new_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument(
        "--repository-root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--mapped-corpus", type=Path)
    parser.add_argument("--review-report", type=Path)
    parser.add_argument("--review-queue", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        records = load_jsonl(args.dataset)
        findings = validate_records(records)
        findings.extend(near_duplicate_findings(records))
        excluded = {args.dataset.resolve()}
        if args.review_report:
            excluded.add(args.review_report.resolve())
        if args.review_queue:
            excluded.add(args.review_queue.resolve())
        repository_findings, repository_scan = repository_leakage_findings(
            records, args.repository_root, excluded
        )
        findings.extend(repository_findings)
        corpus_findings, corpus_scan = corpus_leakage_findings(
            records, args.mapped_corpus
        )
        findings.extend(corpus_findings)
        leakage = {
            "sources_checked": [repository_scan, corpus_scan],
            "sources_not_checked": [
                "raw CFPB CSV/ZIP",
                "near-duplicate similarity against the full mapped corpus",
                "unavailable external or private data",
            ],
            "freezing_blocked_until_human_review": True,
        }
        report = summarize(args.dataset, records, findings, leakage)
        queue = build_review_queue(records, findings, leakage)
        if args.review_report:
            write_new_json(args.review_report, report)
        if args.review_queue:
            write_new_json(args.review_queue, queue)
    except (OSError, TypeError, ValueError, csv.Error, json.JSONDecodeError) as exc:
        print(f"Validation failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(
        f"Draft validation {report['structural_validation']}: records={len(records)} "
        f"errors={report['blocking_error_count']} warnings={report['human_review_warning_count']}"
    )
    return 0 if report["blocking_error_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
