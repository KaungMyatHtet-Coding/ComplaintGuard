"""Privacy-aware, chunked cleaning for the historical CFPB CSV snapshot."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import sqlite3
import unicodedata
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import islice
from pathlib import Path
from time import perf_counter
from typing import Final

import pandas as pd

CLEANED_COLUMNS: Final[tuple[str, ...]] = (
    "Complaint ID",
    "Date received",
    "Consumer complaint narrative",
    "Product",
    "Issue",
    "Sub-product",
    "Sub-issue",
)
REQUIRED_COLUMNS: Final[frozenset[str]] = frozenset(CLEANED_COLUMNS)
OPTIONAL_TEXT_COLUMNS: Final[tuple[str, ...]] = ("Sub-product", "Sub-issue")
LABEL_COLUMNS: Final[tuple[str, ...]] = ("Product", "Issue")
REJECTION_REASONS: Final[tuple[str, ...]] = (
    "invalid_complaint_id",
    "invalid_date_received",
    "missing_product",
    "missing_issue",
    "missing_or_unusable_narrative",
    "duplicate_identical",
)
TIMESTAMP_DATE_FORMAT: Final[str] = "%Y-%m-%dT%H:%M:%S.%fZ"
TIMESTAMP_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z")
PLAIN_DATE_FORMAT: Final[str] = "%Y-%m-%d"
PLAIN_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
SNAPSHOT_DATE_MIN: Final[pd.Timestamp] = pd.Timestamp("2011-12-01", tz="UTC")
SNAPSHOT_DATE_MAX: Final[pd.Timestamp] = pd.Timestamp("2026-07-20", tz="UTC")
DATE_DIAGNOSTIC_CATEGORIES: Final[tuple[str, ...]] = (
    "accepted_millisecond_utc_timestamp",
    "accepted_plain_iso_date",
    "null_date",
    "exact_empty_date",
    "whitespace_bearing_date",
    "invalid_date_shape",
    "impossible_calendar_date",
    "out_of_profile_range_date",
)
LEGACY_REPORT_SCHEMA_VERSION: Final[int] = 1
CURRENT_REPORT_SCHEMA_VERSION: Final[int] = 2
REQUIRED_DATE_FORMAT_COUNT_KEYS: Final[tuple[str, ...]] = (
    *DATE_DIAGNOSTIC_CATEGORIES,
    "total_accepted_dates",
    "total_classified_dates",
)
LEGACY_PAIR_IDENTITIES: Final[dict[str, dict[str, object]]] = {
    "ae691665a9bd4ee68eff41991f5e4075": {
        "csv_sha256": "02766ee4e84fc0ed61c847f302fa73b920aeb157b12f44edcd2b2a7244e744ad",
        "report_sha256": "948b258bf7abb33d8e6f9c96964e43052155c303f834728fdbc4d6e076151ec1",
        "retained_rows": 34114,
    },
    "a41f53c53c7841289a15d3c07bb192c4": {
        "csv_sha256": "f72ca43e869599995bb8f71b7e1859700bea852e1f910cedaa02002ff1c990bf",
        "report_sha256": "5b9ec74ad9590cfdf9c0049dac27a855ccc5c5f65d231f268f5ba4a6ceac52e1",
        "retained_rows": 2487,
    },
}
REDACTION_TOKENS: Final[tuple[str, ...]] = (
    "[REDACTED_EMAIL]",
    "[REDACTED_PHONE]",
    "[REDACTED_NUMBER]",
)

EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
URL_RE = re.compile(r"(?i)\b(?:https?://|www\.)\S+")
PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d().\- ]{5,}\d)(?!\w)")
LONG_NUMBER_RE = re.compile(r"(?<!\d)\d(?:[ -]?\d){8,}(?!\d)")
WHITESPACE_RE = re.compile(r"\s+")
MASKING_TOKEN_RE = re.compile(r"(?i)\bX{2,}\b")


class CleaningError(RuntimeError):
    """Base error for safe, non-row-level cleaning failures."""


class RequiredColumnsError(CleaningError):
    """Raised when the input does not have the approved source schema."""


class ConflictingDuplicateError(CleaningError):
    """Raised when one Complaint ID has different canonical content."""


class PairValidationError(CleaningError):
    """Raised when final CSV and report completion metadata do not match."""


class PublicationError(CleaningError):
    """Raised when a completed pair cannot be safely published or restored."""


class RecoveryRequiredError(CleaningError):
    """Raised when run-specific publication recovery artifacts already exist."""


@dataclass(frozen=True)
class CleaningConfig:
    """Configuration for one deterministic cleaning run."""

    input_path: Path
    output_path: Path
    report_path: Path
    chunk_size: int = 100_000
    max_rows: int | None = None
    max_chunks: int | None = None
    overwrite: bool = False

    def validate(self) -> None:
        if self.chunk_size <= 0:
            raise ValueError("chunk_size must be greater than zero")
        if self.max_rows is not None and self.max_rows <= 0:
            raise ValueError("max_rows must be greater than zero")
        if self.max_chunks is not None and self.max_chunks <= 0:
            raise ValueError("max_chunks must be greater than zero")
        if self.output_path.resolve() == self.input_path.resolve():
            raise ValueError("input and output paths must differ")
        if self.report_path.resolve() in {
            self.input_path.resolve(),
            self.output_path.resolve(),
        }:
            raise ValueError("report path must differ from input and output paths")


@dataclass(frozen=True)
class PreviousPair:
    """Validated metadata for a recoverable previous completed pair."""

    identity: tuple[object, ...]


def normalize_boundary(value: object) -> str | None:
    """Trim category boundaries without changing spelling, case, or internals."""
    if value is None or pd.isna(value):
        return None
    stripped = str(value).strip()
    return stripped or None


def normalize_and_redact_narrative(value: object) -> tuple[str | None, set[str]]:
    """Normalize one narrative and conservatively redact obvious direct PII."""
    if value is None or pd.isna(value):
        return None, set()

    text = unicodedata.normalize("NFKC", str(value))
    redactions: set[str] = set()

    text, count = URL_RE.subn(" ", text)
    if count:
        redactions.add("url")
    text, count = EMAIL_RE.subn("[REDACTED_EMAIL]", text)
    if count:
        redactions.add("email")
    text, count = LONG_NUMBER_RE.subn("[REDACTED_NUMBER]", text)
    if count:
        redactions.add("long_number")
    phone_count = 0

    def redact_phone(match: re.Match[str]) -> str:
        nonlocal phone_count
        if sum(character.isdigit() for character in match.group()) < 7:
            return match.group()
        phone_count += 1
        return "[REDACTED_PHONE]"

    text = PHONE_RE.sub(redact_phone, text)
    if phone_count:
        redactions.add("phone")

    text = WHITESPACE_RE.sub(" ", text).strip()
    if not text:
        return None, redactions

    meaningful = text
    for token in REDACTION_TOKENS:
        meaningful = meaningful.replace(token, " ")
    meaningful = MASKING_TOKEN_RE.sub(" ", meaningful)
    if not any(character.isalnum() for character in meaningful):
        return None, redactions
    return text, redactions


def classify_and_parse_dates(
    date_text: pd.Series,
) -> tuple[pd.Series, pd.Series, dict[str, int]]:
    """Strictly classify and parse the two date shapes observed in this snapshot."""
    dates = pd.Series(pd.NaT, index=date_text.index, dtype="datetime64[ns, UTC]")
    null_date = date_text.isna()
    exact_empty_date = date_text.notna() & date_text.eq("")
    whitespace_bearing_date = (
        date_text.notna() & ~exact_empty_date & date_text.ne(date_text.str.strip())
    )
    eligible_shape = ~(null_date | exact_empty_date | whitespace_bearing_date)

    timestamp_shape = eligible_shape & date_text.str.fullmatch(
        TIMESTAMP_DATE_RE,
        na=False,
    )
    plain_shape = (
        eligible_shape
        & ~timestamp_shape
        & date_text.str.fullmatch(PLAIN_DATE_RE, na=False)
    )
    invalid_date_shape = eligible_shape & ~(timestamp_shape | plain_shape)

    timestamp_hour = pd.to_numeric(
        date_text.where(timestamp_shape).str.slice(11, 13),
        errors="coerce",
    )
    timestamp_minute = pd.to_numeric(
        date_text.where(timestamp_shape).str.slice(14, 16),
        errors="coerce",
    )
    timestamp_second = pd.to_numeric(
        date_text.where(timestamp_shape).str.slice(17, 19),
        errors="coerce",
    )
    timestamp_clock_valid = timestamp_shape & (
        timestamp_hour.between(0, 23)
        & timestamp_minute.between(0, 59)
        & timestamp_second.between(0, 59)
    )
    timestamp_dates = pd.to_datetime(
        date_text.where(timestamp_clock_valid),
        format=TIMESTAMP_DATE_FORMAT,
        errors="coerce",
        exact=True,
        utc=True,
    )
    plain_dates = pd.to_datetime(
        date_text.where(plain_shape),
        format=PLAIN_DATE_FORMAT,
        errors="coerce",
        exact=True,
        utc=True,
    )
    parsed = timestamp_dates.where(timestamp_shape, plain_dates)
    shaped = timestamp_shape | plain_shape
    impossible_calendar_date = (
        (timestamp_shape & ~timestamp_clock_valid)
        | (timestamp_clock_valid & timestamp_dates.isna())
        | (plain_shape & plain_dates.isna())
    )
    calendar_valid = shaped & ~impossible_calendar_date
    parsed_calendar_date = parsed.dt.normalize()
    out_of_profile_range_date = calendar_valid & (
        (parsed_calendar_date < SNAPSHOT_DATE_MIN)
        | (parsed_calendar_date > SNAPSHOT_DATE_MAX)
    )
    accepted_timestamp = timestamp_shape & calendar_valid & ~out_of_profile_range_date
    accepted_plain = plain_shape & calendar_valid & ~out_of_profile_range_date
    valid_date = accepted_timestamp | accepted_plain
    dates.loc[valid_date] = parsed.loc[valid_date]

    diagnostics = {
        "accepted_millisecond_utc_timestamp": int(accepted_timestamp.sum()),
        "accepted_plain_iso_date": int(accepted_plain.sum()),
        "null_date": int(null_date.sum()),
        "exact_empty_date": int(exact_empty_date.sum()),
        "whitespace_bearing_date": int(whitespace_bearing_date.sum()),
        "invalid_date_shape": int(invalid_date_shape.sum()),
        "impossible_calendar_date": int(impossible_calendar_date.sum()),
        "out_of_profile_range_date": int(out_of_profile_range_date.sum()),
    }
    if sum(diagnostics.values()) != len(date_text):
        raise CleaningError("Aggregate date classification reconciliation failed")
    return dates, valid_date, diagnostics


def _canonical_digest(row: pd.Series) -> str:
    canonical = [
        None if pd.isna(row[column]) else str(row[column])
        for column in CLEANED_COLUMNS[1:]
    ]
    payload = json.dumps(canonical, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _temporary_path(final_path: Path, run_id: str) -> Path:
    return final_path.with_name(f".{final_path.name}.{run_id}.tmp")


def _input_metadata(input_path: Path, source_columns: list[str]) -> dict[str, object]:
    stat = input_path.stat()
    header_payload = json.dumps(
        source_columns, ensure_ascii=False, separators=(",", ":")
    )
    return {
        "file_name": input_path.name,
        "size_bytes": stat.st_size,
        "modified_at_utc": datetime.fromtimestamp(
            stat.st_mtime, timezone.utc
        ).isoformat(),
        "header_sha256": hashlib.sha256(header_payload.encode("utf-8")).hexdigest(),
    }


def stream_file_integrity(path: Path) -> dict[str, object]:
    """Return SHA-256 and byte size using bounded streaming reads."""
    digest = hashlib.sha256()
    size_bytes = 0
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
            size_bytes += len(block)
    return {"sha256": digest.hexdigest(), "size_bytes": size_bytes}


def _csv_retained_rows(path: Path) -> int:
    try:
        with path.open("r", encoding="utf-8", newline="") as source:
            reader = csv.reader(source, strict=True)
            header = next(reader)
            if header != list(CLEANED_COLUMNS):
                raise PairValidationError(
                    "Completed CSV schema does not match the approved schema"
                )
            return sum(1 for _ in reader)
    except StopIteration as error:
        raise PairValidationError("Completed CSV is missing its header") from error
    except (OSError, UnicodeError, csv.Error) as error:
        raise PairValidationError("Completed CSV cannot be validated") from error


def _read_report_mappings(
    report_path: Path,
) -> tuple[dict[str, object], dict[str, object], dict[str, object], dict[str, object]]:
    try:
        parsed = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PairValidationError("Completion report is missing or invalid") from error
    if not isinstance(parsed, dict):
        raise PairValidationError("Completion report must be a JSON object")
    completion = parsed.get("completion")
    counts = parsed.get("counts")
    schema = parsed.get("schema")
    if not isinstance(completion, dict):
        raise PairValidationError("Completion metadata must be a JSON object")
    if not isinstance(counts, dict):
        raise PairValidationError("Aggregate counts must be a JSON object")
    if not isinstance(schema, dict):
        raise PairValidationError("Schema metadata must be a JSON object")
    return parsed, completion, counts, schema


def _validate_version_2_date_counts(
    report: dict[str, object],
    counts: dict[str, object],
) -> None:
    date_counts = report.get("date_format_counts")
    if not isinstance(date_counts, dict):
        raise PairValidationError("Version-2 report has invalid date-format counts")
    if set(date_counts) != set(REQUIRED_DATE_FORMAT_COUNT_KEYS):
        raise PairValidationError("Version-2 report has incomplete date-format counts")
    values: dict[str, int] = {}
    for key in REQUIRED_DATE_FORMAT_COUNT_KEYS:
        value = date_counts.get(key)
        if type(value) is not int or value < 0:
            raise PairValidationError("Version-2 report has invalid date-format counts")
        values[key] = value
    category_total = sum(values[key] for key in DATE_DIAGNOSTIC_CATEGORIES)
    accepted_total = (
        values["accepted_millisecond_utc_timestamp"] + values["accepted_plain_iso_date"]
    )
    if (
        values["total_classified_dates"] != category_total
        or values["total_accepted_dates"] != accepted_total
        or type(counts.get("input_rows")) is not int
        or values["total_classified_dates"] != counts["input_rows"]
    ):
        raise PairValidationError(
            "Version-2 report has inconsistent date-format counts"
        )


def _is_approved_legacy_pair(
    report: dict[str, object],
    report_path: Path,
    csv_integrity: dict[str, object],
) -> bool:
    completion = report["completion"]
    if not isinstance(completion, dict):
        return False
    run_id = completion.get("run_id")
    identity = LEGACY_PAIR_IDENTITIES.get(run_id)
    if identity is None:
        return False
    report_integrity = stream_file_integrity(report_path)
    return (
        completion.get("csv_sha256") == identity["csv_sha256"]
        and completion.get("retained_row_count") == identity["retained_rows"]
        and csv_integrity["sha256"] == identity["csv_sha256"]
        and report_integrity["sha256"] == identity["report_sha256"]
    )


def _pair_identity(report: dict[str, object]) -> tuple[object, ...]:
    completion = report["completion"]
    counts = report["counts"]
    schema = report["schema"]
    if (
        not isinstance(completion, dict)
        or not isinstance(counts, dict)
        or not isinstance(schema, dict)
    ):
        raise PairValidationError("Completed-pair metadata has invalid structure")
    cleaned_columns = schema.get("cleaned_columns")
    return (
        report.get("run_id"),
        report.get("status"),
        completion.get("run_id"),
        completion.get("status"),
        completion.get("csv_file_name"),
        completion.get("csv_sha256"),
        completion.get("csv_size_bytes"),
        completion.get("retained_row_count"),
        counts.get("retained_rows"),
        tuple(cleaned_columns) if isinstance(cleaned_columns, list) else None,
    )


def validate_completed_pair(output_path: Path, report_path: Path) -> dict[str, object]:
    """Validate that a report-last completion marker matches its CSV."""
    if not output_path.is_file() or not report_path.is_file():
        raise PairValidationError("Completed CSV/report pair is incomplete")
    report, completion, counts, schema = _read_report_mappings(report_path)

    run_id = completion.get("run_id")
    retained_rows = completion.get("retained_row_count")
    cleaned_columns = schema.get("cleaned_columns")
    if (
        report.get("status") != "completed"
        or completion.get("status") != "completed"
        or not isinstance(run_id, str)
        or not run_id
        or report.get("run_id") != run_id
        or completion.get("csv_file_name") != output_path.name
        or type(retained_rows) is not int
        or counts.get("retained_rows") != retained_rows
        or cleaned_columns != list(CLEANED_COLUMNS)
    ):
        raise PairValidationError(
            "Completion metadata does not match the completed run"
        )

    integrity = stream_file_integrity(output_path)
    if (
        completion.get("csv_sha256") != integrity["sha256"]
        or completion.get("csv_size_bytes") != integrity["size_bytes"]
        or _csv_retained_rows(output_path) != retained_rows
    ):
        raise PairValidationError("Completed CSV integrity does not match its report")
    report_schema_version = report.get("report_schema_version")
    if (
        type(report_schema_version) is int
        and report_schema_version == CURRENT_REPORT_SCHEMA_VERSION
    ):
        _validate_version_2_date_counts(report, counts)
    elif (
        report_schema_version is None
        and _is_approved_legacy_pair(report, report_path, integrity)
    ) or (
        type(report_schema_version) is int
        and report_schema_version == LEGACY_REPORT_SCHEMA_VERSION
        and _is_approved_legacy_pair(report, report_path, integrity)
    ):
        pass
    else:
        raise PairValidationError("Unsupported or unrecognized report schema version")
    return report


def _backup_path(final_path: Path, run_id: str) -> Path:
    return final_path.with_name(f".{final_path.name}.{run_id}.backup")


def _publication_lock_path(output_path: Path) -> Path:
    return output_path.with_name(f".{output_path.name}.publish.lock")


def _publication_lock_paths(output_path: Path, report_path: Path) -> tuple[Path, ...]:
    paths = {
        _publication_lock_path(output_path),
        _publication_lock_path(report_path),
    }
    return tuple(sorted(paths, key=lambda path: os.path.normcase(str(path.resolve()))))


def _find_recovery_artifacts(output_path: Path, report_path: Path) -> list[Path]:
    patterns = (
        f".{output_path.name}.*.backup",
        f".{report_path.name}.*.backup",
    )
    return [
        path
        for parent, pattern in (
            (output_path.parent, patterns[0]),
            (report_path.parent, patterns[1]),
        )
        for path in parent.glob(pattern)
    ]


def _acquire_publication_locks(
    lock_paths: tuple[Path, ...],
    run_id: str,
) -> tuple[Path, ...]:
    acquired: list[Path] = []
    try:
        for lock_path in lock_paths:
            with lock_path.open("x", encoding="utf-8") as lock:
                lock.write(run_id)
            acquired.append(lock_path)
    except FileExistsError as error:
        for lock_path in reversed(acquired):
            _release_publication_lock(lock_path, run_id)
        raise RecoveryRequiredError(
            "A publication lock already exists; inspect local recovery state before retrying"
        ) from error
    except Exception:
        for lock_path in reversed(acquired):
            _release_publication_lock(lock_path, run_id)
        raise
    return tuple(acquired)


def _release_publication_lock(lock_path: Path, run_id: str) -> None:
    try:
        if lock_path.read_text(encoding="utf-8") == run_id:
            lock_path.unlink()
    except FileNotFoundError:
        pass


def _release_publication_locks(lock_paths: tuple[Path, ...], run_id: str) -> None:
    for lock_path in reversed(lock_paths):
        _release_publication_lock(lock_path, run_id)


def _classify_previous_state(
    output_path: Path,
    report_path: Path,
) -> PreviousPair | None:
    output_exists = output_path.exists()
    report_exists = report_path.exists()
    if not output_exists and not report_exists:
        return None
    if report_exists:
        try:
            report, completion, _, _ = _read_report_mappings(report_path)
        except PairValidationError as error:
            raise RecoveryRequiredError(
                "Existing completion state is malformed and requires owner recovery"
            ) from error
        if completion.get("csv_file_name") != output_path.name:
            raise RecoveryRequiredError(
                "Existing report is a foreign completion marker for another CSV"
            )
    if not output_exists or not report_exists:
        raise RecoveryRequiredError(
            "Existing CSV/report state is incomplete and requires owner recovery"
        )
    try:
        report = validate_completed_pair(output_path, report_path)
    except PairValidationError as error:
        raise RecoveryRequiredError(
            "Existing CSV/report pair is invalid and requires owner recovery"
        ) from error
    return PreviousPair(identity=_pair_identity(report))


def _remove_current_report(report_path: Path, run_id: str) -> None:
    if not report_path.is_file():
        return
    try:
        completion_run_id = json.loads(report_path.read_text(encoding="utf-8"))[
            "completion"
        ]["run_id"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return
    if completion_run_id == run_id:
        report_path.unlink()


def _remove_current_csv(
    output_path: Path,
    expected_integrity: dict[str, object],
) -> None:
    if (
        output_path.is_file()
        and stream_file_integrity(output_path) == expected_integrity
    ):
        output_path.unlink()


def _copy_previous_artifacts_for_recovery(
    output_path: Path,
    report_path: Path,
    output_backup: Path,
    report_backup: Path,
) -> None:
    if output_backup.exists():
        shutil.copy2(output_backup, output_path)
    if report_backup.exists():
        shutil.copy2(report_backup, report_path)


def _remove_backups_after_valid_pair(backups: tuple[Path, ...], state: str) -> None:
    for backup in sorted(
        backups, key=lambda path: os.path.normcase(str(path.resolve()))
    ):
        try:
            backup.unlink(missing_ok=True)
        except OSError as error:
            raise RecoveryRequiredError(
                f"{state} pair is valid but backup cleanup is incomplete"
            ) from error


def _restore_and_validate_previous_pair(
    *,
    output_path: Path,
    report_path: Path,
    output_backup: Path,
    report_backup: Path,
    previous_pair: PreviousPair,
) -> None:
    try:
        _copy_previous_artifacts_for_recovery(
            output_path,
            report_path,
            output_backup,
            report_backup,
        )
        restored = validate_completed_pair(output_path, report_path)
        if _pair_identity(restored) != previous_pair.identity:
            raise PairValidationError(
                "Restored pair does not match its recorded completion metadata"
            )
    except Exception as error:
        raise RecoveryRequiredError(
            "Previous pair restoration is incomplete; recovery evidence was preserved"
        ) from error
    _remove_backups_after_valid_pair(
        (output_backup, report_backup),
        "Restored previous",
    )


def _publish_completed_pair(
    *,
    temporary_output: Path,
    temporary_report: Path,
    output_path: Path,
    report_path: Path,
    run_id: str,
    overwrite: bool,
    expected_integrity: dict[str, object],
    previous_pair: PreviousPair | None,
) -> None:
    if previous_pair is not None and not overwrite:
        raise FileExistsError(
            "Refusing to overwrite an existing CSV or completion report"
        )

    output_backup = _backup_path(output_path, run_id)
    report_backup = _backup_path(report_path, run_id)
    current_output_published = False
    current_report_published = False
    try:
        # The old report is the completion marker, so remove it before replacing its CSV.
        if previous_pair is not None:
            os.replace(report_path, report_backup)
            os.replace(output_path, output_backup)

        os.replace(temporary_output, output_path)
        current_output_published = True
        os.replace(temporary_report, report_path)
        current_report_published = True
        validate_completed_pair(output_path, report_path)
    except BaseException as publication_error:
        try:
            if current_report_published:
                _remove_current_report(report_path, run_id)
            if current_output_published:
                _remove_current_csv(output_path, expected_integrity)
            if previous_pair is not None:
                _restore_and_validate_previous_pair(
                    output_path=output_path,
                    report_path=report_path,
                    output_backup=output_backup,
                    report_backup=report_backup,
                    previous_pair=previous_pair,
                )
        except RecoveryRequiredError:
            raise
        except Exception as recovery_error:
            raise RecoveryRequiredError(
                "Publication recovery is incomplete; recovery evidence was preserved"
            ) from recovery_error
        if isinstance(publication_error, Exception):
            raise PublicationError(
                "Publication failed; previous local artifacts were restored"
            ) from publication_error
        raise
    else:
        if previous_pair is not None:
            _remove_backups_after_valid_pair(
                (output_backup, report_backup),
                "New",
            )


def clean_cfpb(config: CleaningConfig) -> dict[str, object]:
    """Clean a CFPB CSV incrementally and publish a report-validated pair."""
    config.validate()
    if not config.input_path.is_file():
        raise FileNotFoundError(f"Input CSV not found: {config.input_path.name}")

    source_columns = pd.read_csv(config.input_path, nrows=0).columns.tolist()
    missing_columns = sorted(REQUIRED_COLUMNS.difference(source_columns))
    if missing_columns:
        raise RequiredColumnsError(
            "Input CSV is missing required columns: " + ", ".join(missing_columns)
        )

    run_id = uuid.uuid4().hex
    config.output_path.parent.mkdir(parents=True, exist_ok=True)
    config.report_path.parent.mkdir(parents=True, exist_ok=True)
    lock_paths = _publication_lock_paths(config.output_path, config.report_path)
    temporary_output = _temporary_path(config.output_path, run_id)
    temporary_report = _temporary_path(config.report_path, run_id)
    sqlite_path = config.output_path.with_name(
        f".{config.output_path.name}.{run_id}.sqlite.tmp"
    )
    created_paths = (temporary_output, temporary_report, sqlite_path)
    started_at = datetime.now(timezone.utc)
    timer = perf_counter()
    input_rows = 0
    retained_rows = 0
    chunks_processed = 0
    rejected: Counter[str] = Counter()
    redactions: Counter[str] = Counter()
    date_diagnostics: Counter[str] = Counter()
    optional_nulls: Counter[str] = Counter()
    distributions = {column: Counter() for column in LABEL_COLUMNS}
    connection: sqlite3.Connection | None = None
    acquired_locks = _acquire_publication_locks(lock_paths, run_id)

    try:
        recovery_artifacts = _find_recovery_artifacts(
            config.output_path,
            config.report_path,
        )
        if recovery_artifacts:
            raise RecoveryRequiredError(
                "Recoverable publication backups already exist; inspect local recovery state before retrying"
            )
        previous_pair = _classify_previous_state(
            config.output_path,
            config.report_path,
        )
        if previous_pair is not None and not config.overwrite:
            raise FileExistsError(
                "Refusing to overwrite an existing CSV or completion report"
            )
        connection = sqlite3.connect(sqlite_path)
        connection.execute(
            "CREATE TABLE seen_complaints (complaint_id TEXT PRIMARY KEY, canonical_digest TEXT NOT NULL)"
        )

        reader = pd.read_csv(
            config.input_path,
            usecols=list(CLEANED_COLUMNS),
            dtype={column: "string" for column in CLEANED_COLUMNS},
            chunksize=config.chunk_size,
            nrows=config.max_rows,
            keep_default_na=True,
            low_memory=False,
            on_bad_lines="error",
        )
        wrote_header = False
        chunks = (
            reader if config.max_chunks is None else islice(reader, config.max_chunks)
        )
        for chunk_number, chunk in enumerate(chunks, start=1):
            chunks_processed += 1
            input_rows += len(chunk)

            for column in (*LABEL_COLUMNS, *OPTIONAL_TEXT_COLUMNS):
                chunk[column] = (
                    chunk[column]
                    .map(normalize_boundary, na_action=None)
                    .astype("string")
                )

            ids = chunk["Complaint ID"].str.strip()
            valid_id = ids.str.fullmatch(r"[1-9]\d*", na=False)
            date_text = chunk["Date received"]
            dates, valid_date, chunk_date_diagnostics = classify_and_parse_dates(
                date_text
            )
            date_diagnostics.update(chunk_date_diagnostics)
            valid_product = chunk["Product"].notna()
            valid_issue = chunk["Issue"].notna()

            normalized_narratives: list[str | None] = []
            for narrative in chunk["Consumer complaint narrative"]:
                normalized, applied = normalize_and_redact_narrative(narrative)
                normalized_narratives.append(normalized)
                redactions.update(applied)
            chunk["Consumer complaint narrative"] = pd.array(
                normalized_narratives, dtype="string"
            )
            valid_narrative = chunk["Consumer complaint narrative"].notna()

            reason = pd.Series(pd.NA, index=chunk.index, dtype="string")
            reason.mask(~valid_id & reason.isna(), "invalid_complaint_id", inplace=True)
            reason.mask(
                ~valid_date & reason.isna(), "invalid_date_received", inplace=True
            )
            reason.mask(~valid_product & reason.isna(), "missing_product", inplace=True)
            reason.mask(~valid_issue & reason.isna(), "missing_issue", inplace=True)
            reason.mask(
                ~valid_narrative & reason.isna(),
                "missing_or_unusable_narrative",
                inplace=True,
            )
            rejected.update(reason.dropna().value_counts().astype(int).to_dict())

            candidates = chunk.loc[reason.isna(), list(CLEANED_COLUMNS)].copy()
            candidates["Complaint ID"] = ids.loc[candidates.index]
            candidates["Date received"] = dates.loc[candidates.index].dt.strftime(
                "%Y-%m-%d"
            )

            retained_indices: list[int] = []
            for index, row in candidates.iterrows():
                digest = _canonical_digest(row)
                cursor = connection.execute(
                    "INSERT OR IGNORE INTO seen_complaints VALUES (?, ?)",
                    (row["Complaint ID"], digest),
                )
                if cursor.rowcount == 1:
                    retained_indices.append(index)
                    continue
                existing = connection.execute(
                    "SELECT canonical_digest FROM seen_complaints WHERE complaint_id = ?",
                    (row["Complaint ID"],),
                ).fetchone()
                if existing is not None and existing[0] == digest:
                    rejected["duplicate_identical"] += 1
                    continue
                rejected["duplicate_conflicting"] += 1
                raise ConflictingDuplicateError(
                    "Conflicting canonical content found for a duplicate Complaint ID; "
                    "the run was aborted without publishing output"
                )
            connection.commit()

            retained = candidates.loc[retained_indices, list(CLEANED_COLUMNS)]
            retained_rows += len(retained)
            for column in OPTIONAL_TEXT_COLUMNS:
                optional_nulls[column] += int(retained[column].isna().sum())
            for column in LABEL_COLUMNS:
                distributions[column].update(retained[column].value_counts().to_dict())
            if not retained.empty or not wrote_header:
                retained.to_csv(
                    temporary_output,
                    mode="a",
                    index=False,
                    header=not wrote_header,
                    lineterminator="\n",
                )
                wrote_header = True

        rejected_total = sum(rejected[reason] for reason in REJECTION_REASONS)
        if input_rows != retained_rows + rejected_total:
            raise CleaningError("Aggregate row-count reconciliation failed")
        total_classified_dates = sum(
            date_diagnostics[category] for category in DATE_DIAGNOSTIC_CATEGORIES
        )
        total_accepted_dates = (
            date_diagnostics["accepted_millisecond_utc_timestamp"]
            + date_diagnostics["accepted_plain_iso_date"]
        )
        if total_classified_dates != input_rows:
            raise CleaningError("Aggregate date classification reconciliation failed")

        output_integrity = stream_file_integrity(temporary_output)
        finished_at = datetime.now(timezone.utc)
        report: dict[str, object] = {
            "generated_at_utc": finished_at.isoformat(),
            "generator": "scripts/clean_cfpb.py",
            "report_schema_version": CURRENT_REPORT_SCHEMA_VERSION,
            "run_id": run_id,
            "status": "completed",
            "completion": {
                "run_id": run_id,
                "status": "completed",
                "csv_file_name": config.output_path.name,
                "csv_sha256": output_integrity["sha256"],
                "csv_size_bytes": output_integrity["size_bytes"],
                "retained_row_count": retained_rows,
            },
            "configuration": {
                "input_file_name": config.input_path.name,
                "output_file_name": config.output_path.name,
                "chunk_size": config.chunk_size,
                "max_rows": config.max_rows,
                "max_chunks": config.max_chunks,
                "csv_only": True,
                "overwrite": config.overwrite,
            },
            "input_integrity": _input_metadata(config.input_path, source_columns),
            "schema": {
                "source_column_count": len(source_columns),
                "required_source_columns": list(CLEANED_COLUMNS),
                "cleaned_columns": list(CLEANED_COLUMNS),
                "complaint_id_role": "provenance and deduplication only; never an ML feature",
            },
            "counts": {
                "input_rows": input_rows,
                "retained_rows": retained_rows,
                "rejected_rows": rejected_total,
                "chunks_processed": chunks_processed,
                "reconciliation_valid": True,
            },
            "rejection_reasons": {
                reason: int(rejected[reason]) for reason in REJECTION_REASONS
            },
            "date_format_counts": {
                **{
                    category: int(date_diagnostics[category])
                    for category in DATE_DIAGNOSTIC_CATEGORIES
                },
                "total_accepted_dates": int(total_accepted_dates),
                "total_classified_dates": int(total_classified_dates),
            },
            "optional_category_null_counts": {
                column: int(optional_nulls[column]) for column in OPTIONAL_TEXT_COLUMNS
            },
            "redaction_counts": {
                reason: int(redactions[reason])
                for reason in ("email", "url", "phone", "long_number")
            },
            "label_distributions": {
                column: dict(sorted(distributions[column].items()))
                for column in LABEL_COLUMNS
            },
            "timing": {
                "started_at_utc": started_at.isoformat(),
                "finished_at_utc": finished_at.isoformat(),
                "elapsed_seconds": round(perf_counter() - timer, 3),
            },
            "privacy": {
                "classification": "PII-reduced, not anonymized",
                "row_level_values_in_report": False,
            },
        }
        temporary_report.write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
        if connection is not None:
            connection.close()
            connection = None
        _publish_completed_pair(
            temporary_output=temporary_output,
            temporary_report=temporary_report,
            output_path=config.output_path,
            report_path=config.report_path,
            run_id=run_id,
            overwrite=config.overwrite,
            expected_integrity=output_integrity,
            previous_pair=previous_pair,
        )
        return report
    except Exception:
        if connection is not None:
            connection.close()
        for path in created_paths:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        raise
    finally:
        sqlite_path.unlink(missing_ok=True)
        _release_publication_locks(acquired_locks, run_id)
