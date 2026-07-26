from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pandas as pd
import pytest

from scripts.cfpb_cleaning import (
    CLEANED_COLUMNS,
    CleaningConfig,
    ConflictingDuplicateError,
    PairValidationError,
    PublicationError,
    RecoveryRequiredError,
    RequiredColumnsError,
    TIMESTAMP_DATE_RE,
    _acquire_publication_locks,
    _backup_path,
    _publication_lock_paths,
    _release_publication_locks,
    classify_and_parse_dates,
    clean_cfpb,
    normalize_and_redact_narrative,
    validate_completed_pair,
)


def row(
    complaint_id: str | None,
    narrative: str | None = "A useful complaint narrative",
    date_received: str | None = "2026-07-20T00:00:00.000Z",
    product: str | None = "Credit card",
    issue: str | None = "Billing dispute",
    sub_product: str | None = None,
    sub_issue: str | None = None,
) -> dict[str, str | None]:
    return {
        "Complaint ID": complaint_id,
        "Date received": date_received,
        "Consumer complaint narrative": narrative,
        "Product": product,
        "Issue": issue,
        "Sub-product": sub_product,
        "Sub-issue": sub_issue,
    }


def write_input(path: Path, rows: list[dict[str, str | None]]) -> None:
    pd.DataFrame(rows, columns=CLEANED_COLUMNS).to_csv(path, index=False)


def config(tmp_path: Path, input_path: Path, **overrides: object) -> CleaningConfig:
    values: dict[str, object] = {
        "input_path": input_path,
        "output_path": tmp_path / "complaints_cleaned.csv",
        "report_path": tmp_path / "cleaning_report.json",
        "chunk_size": 2,
    }
    values.update(overrides)
    return CleaningConfig(**values)  # type: ignore[arg-type]


def assert_no_publication_locks(root: Path) -> None:
    assert list(root.glob("*.publish.lock")) == []
    assert list(root.glob(".*.publish.lock")) == []


def assert_private_error(error: BaseException) -> None:
    message = str(error)
    assert "987654" not in message
    assert "Synthetic private narrative" not in message


def create_valid_pair(
    tmp_path: Path,
    *,
    output_name: str = "complaints_cleaned.csv",
    report_name: str = "cleaning_report.json",
) -> tuple[Path, CleaningConfig, dict[str, object]]:
    input_path = tmp_path / "input.csv"
    write_input(
        input_path,
        [row("987654", narrative="Synthetic private narrative")],
    )
    cleaning_config = config(
        tmp_path,
        input_path,
        output_path=tmp_path / output_name,
        report_path=tmp_path / report_name,
    )
    report = clean_cfpb(cleaning_config)
    return input_path, cleaning_config, report


def test_normalization_redacts_obvious_pii_and_preserves_masking_tokens() -> None:
    narrative = (
        "  Contact me@example.com or +1 (212) 555-1212. "
        "Account 1234 5678 9012 at https://example.com/a  XXXX  "
    )

    cleaned, applied = normalize_and_redact_narrative(narrative)

    assert cleaned is not None
    assert "me@example.com" not in cleaned
    assert "example.com" not in cleaned
    assert "1234 5678 9012" not in cleaned
    assert "XXXX" in cleaned
    assert applied == {"email", "url", "phone", "long_number"}
    assert "  " not in cleaned


def test_phone_redaction_requires_at_least_seven_actual_digits() -> None:
    positive, positive_applied = normalize_and_redact_narrative(
        "Call +1 (212) 555-1212 about this complaint"
    )
    negative, negative_applied = normalize_and_redact_narrative(
        "Reference 1.......2 remains ordinary punctuation"
    )

    assert positive is not None
    assert "[REDACTED_PHONE]" in positive
    assert "phone" in positive_applied
    assert negative == "Reference 1.......2 remains ordinary punctuation"
    assert "phone" not in negative_applied


def test_cleaning_reconciles_mutually_exclusive_rejections(tmp_path: Path) -> None:
    input_path = tmp_path / "input.csv"
    rows = [
        row("1", narrative="  Valid\n complaint with XXXX  ", product=" Credit card "),
        row(None, date_received=None, narrative=None, product=None, issue=None),
        row("2", date_received="07/20/2026"),
        row("3", product="   "),
        row("4", issue=None),
        row("5", narrative=" https://example.com XXXX "),
        row("1", narrative="Valid complaint with XXXX", product="Credit card"),
    ]
    write_input(input_path, rows)

    report = clean_cfpb(config(tmp_path, input_path))

    assert report["counts"] == {
        "input_rows": 7,
        "retained_rows": 1,
        "rejected_rows": 6,
        "chunks_processed": 4,
        "reconciliation_valid": True,
    }
    assert report["rejection_reasons"] == {
        "invalid_complaint_id": 1,
        "invalid_date_received": 1,
        "missing_product": 1,
        "missing_issue": 1,
        "missing_or_unusable_narrative": 1,
        "duplicate_identical": 1,
    }
    assert report["optional_category_null_counts"] == {
        "Sub-product": 1,
        "Sub-issue": 1,
    }
    output = pd.read_csv(tmp_path / "complaints_cleaned.csv", dtype="string")
    assert output.columns.tolist() == list(CLEANED_COLUMNS)
    assert output.loc[0, "Date received"] == "2026-07-20"
    assert output.loc[0, "Product"] == "Credit card"
    assert output.loc[0, "Consumer complaint narrative"] == "Valid complaint with XXXX"


def test_identical_duplicate_is_detected_across_chunks(tmp_path: Path) -> None:
    input_path = tmp_path / "input.csv"
    write_input(input_path, [row("10"), row("11"), row("10")])

    report = clean_cfpb(config(tmp_path, input_path, chunk_size=2))

    assert report["counts"]["retained_rows"] == 2
    assert report["rejection_reasons"]["duplicate_identical"] == 1


def test_optional_null_counts_accumulate_across_chunks(tmp_path: Path) -> None:
    input_path = tmp_path / "input.csv"
    write_input(
        input_path,
        [
            row("1", sub_product=None, sub_issue="Known"),
            row("2", sub_product=" ", sub_issue=None),
            row("3", sub_product="Known", sub_issue=None),
        ],
    )

    report = clean_cfpb(config(tmp_path, input_path, chunk_size=2))

    assert report["counts"]["chunks_processed"] == 2
    assert report["optional_category_null_counts"] == {
        "Sub-product": 2,
        "Sub-issue": 2,
    }


def test_conflicting_duplicate_aborts_without_publishing_files(tmp_path: Path) -> None:
    input_path = tmp_path / "input.csv"
    write_input(input_path, [row("10"), row("11"), row("10", issue="Different issue")])
    cleaning_config = config(tmp_path, input_path, chunk_size=2)

    with pytest.raises(ConflictingDuplicateError, match="run was aborted") as caught:
        clean_cfpb(cleaning_config)

    assert "10" not in str(caught.value)
    assert not cleaning_config.output_path.exists()
    assert not cleaning_config.report_path.exists()
    assert list(tmp_path.glob("*.tmp")) == []
    assert list(tmp_path.glob(".*.tmp")) == []


def test_required_columns_are_validated_before_output(tmp_path: Path) -> None:
    input_path = tmp_path / "input.csv"
    pd.DataFrame([{"Complaint ID": "1"}]).to_csv(input_path, index=False)
    cleaning_config = config(tmp_path, input_path)

    with pytest.raises(RequiredColumnsError, match="missing required columns"):
        clean_cfpb(cleaning_config)

    assert not cleaning_config.output_path.exists()
    assert not cleaning_config.report_path.exists()


def test_overwrite_is_protected_and_explicit_overwrite_replaces(tmp_path: Path) -> None:
    input_path = tmp_path / "input.csv"
    write_input(input_path, [row("1")])
    cleaning_config = config(tmp_path, input_path)
    original = clean_cfpb(cleaning_config)
    write_input(input_path, [row("2")])

    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        clean_cfpb(cleaning_config)

    report = clean_cfpb(config(tmp_path, input_path, overwrite=True))

    assert report["counts"]["retained_rows"] == 1
    assert report["run_id"] != original["run_id"]
    assert json.loads(cleaning_config.report_path.read_text(encoding="utf-8"))["status"] == "completed"
    assert cleaning_config.output_path.read_text(encoding="utf-8").startswith("Complaint ID,")


@pytest.mark.parametrize(
    ("complaint_id", "accepted"),
    [
        (None, False),
        ("", False),
        ("   ", False),
        ("0", False),
        ("-1", False),
        ("letters", False),
        ("1.5", False),
        ("42", True),
    ],
)
def test_complaint_id_positive_decimal_rule(
    tmp_path: Path,
    complaint_id: str | None,
    accepted: bool,
) -> None:
    case_path = tmp_path / ("accepted" if accepted else f"rejected-{len(list(tmp_path.iterdir()))}")
    case_path.mkdir()
    input_path = case_path / "input.csv"
    write_input(input_path, [row(complaint_id)])

    report = clean_cfpb(config(case_path, input_path))

    assert report["counts"]["retained_rows"] == int(accepted)
    assert report["rejection_reasons"]["invalid_complaint_id"] == int(not accepted)


@pytest.mark.parametrize(
    ("date_received", "accepted", "diagnostic_category"),
    [
        ("2026-07-20T00:00:00.000Z", True, "accepted_millisecond_utc_timestamp"),
        ("2026-07-20", True, "accepted_plain_iso_date"),
        ("2011-12-01", True, "accepted_plain_iso_date"),
        ("2026-07-20", True, "accepted_plain_iso_date"),
        ("2026-07-20T00:00:00.0Z", False, "invalid_date_shape"),
        ("2026-07-20T00:00:00.000000Z", False, "invalid_date_shape"),
        ("2026-07-20T00:00:00Z", False, "invalid_date_shape"),
        ("2026-07-20T00:00:00.000", False, "invalid_date_shape"),
        ("2020-01-01T25:00:00.000Z", False, "impossible_calendar_date"),
        ("2020-01-01T24:00:00.000Z", False, "impossible_calendar_date"),
        ("2020-01-01T00:60:00.000Z", False, "impossible_calendar_date"),
        ("2020-01-01T00:00:60.000Z", False, "impossible_calendar_date"),
        ("2020-01-01T23:59:59.999Z", True, "accepted_millisecond_utc_timestamp"),
        ("2026-07-20t00:00:00.000Z", False, "invalid_date_shape"),
        ("2026-07-20T00:00:00.000z", False, "invalid_date_shape"),
        ("2026-07-20T00:00:00.000+00:00", False, "invalid_date_shape"),
        ("07/20/2026", False, "invalid_date_shape"),
        (" 2026-07-20", False, "whitespace_bearing_date"),
        ("2026-07-20 ", False, "whitespace_bearing_date"),
        ("2026-02-30T00:00:00.000Z", False, "impossible_calendar_date"),
        ("2026-02-30", False, "impossible_calendar_date"),
        ("2026.07.20", False, "invalid_date_shape"),
        ("2026-7-20", False, "invalid_date_shape"),
        ("2011-11-30", False, "out_of_profile_range_date"),
        ("2026-07-21", False, "out_of_profile_range_date"),
    ],
)
def test_date_received_allowlist_is_strict(
    tmp_path: Path,
    date_received: str,
    accepted: bool,
    diagnostic_category: str,
) -> None:
    input_path = tmp_path / "input.csv"
    write_input(input_path, [row("1", date_received=date_received)])

    report = clean_cfpb(config(tmp_path, input_path))

    assert report["counts"]["retained_rows"] == int(accepted)
    assert report["rejection_reasons"]["invalid_date_received"] == int(not accepted)
    assert report["date_format_counts"][diagnostic_category] == 1
    assert report["date_format_counts"]["total_accepted_dates"] == int(accepted)
    assert report["date_format_counts"]["total_classified_dates"] == 1
    if accepted:
        output = pd.read_csv(tmp_path / "complaints_cleaned.csv", dtype="string")
        assert output.loc[0, "Date received"] == date_received[:10]


@pytest.mark.parametrize(
    "date_received",
    [
        "2020-01-01T25:00:00.000Z",
        "2020-01-01T24:00:00.000Z",
        "2020-01-01T00:60:00.000Z",
        "2020-01-01T00:00:60.000Z",
    ],
)
def test_timestamp_clock_components_are_semantically_rejected(
    tmp_path: Path,
    date_received: str,
) -> None:
    assert TIMESTAMP_DATE_RE.fullmatch(date_received)
    input_path = tmp_path / "input.csv"
    write_input(input_path, [row("1", date_received=date_received)])

    report = clean_cfpb(config(tmp_path, input_path))

    assert report["counts"]["retained_rows"] == 0
    assert report["counts"]["rejected_rows"] == 1
    assert report["counts"]["input_rows"] == (
        report["counts"]["retained_rows"] + report["counts"]["rejected_rows"]
    )
    assert report["rejection_reasons"]["invalid_date_received"] == 1
    assert report["date_format_counts"]["impossible_calendar_date"] == 1
    assert report["date_format_counts"]["invalid_date_shape"] == 0
    assert report["date_format_counts"]["accepted_millisecond_utc_timestamp"] == 0
    assert report["date_format_counts"]["accepted_plain_iso_date"] == 0
    assert report["date_format_counts"]["total_accepted_dates"] == 0
    assert report["date_format_counts"]["total_classified_dates"] == 1
    assert date_received not in json.dumps(report)


def test_date_diagnostics_distinguish_null_empty_and_whitespace() -> None:
    values = pd.Series([pd.NA, "", "   "], dtype="string")

    _, valid, diagnostics = classify_and_parse_dates(values)

    assert not valid.any()
    assert diagnostics == {
        "accepted_millisecond_utc_timestamp": 0,
        "accepted_plain_iso_date": 0,
        "null_date": 1,
        "exact_empty_date": 1,
        "whitespace_bearing_date": 1,
        "invalid_date_shape": 0,
        "impossible_calendar_date": 0,
        "out_of_profile_range_date": 0,
    }


@pytest.mark.parametrize("chunk_size", [1, 2])
def test_both_date_formats_reconcile_within_and_across_chunks(
    tmp_path: Path,
    chunk_size: int,
) -> None:
    input_path = tmp_path / "input.csv"
    write_input(
        input_path,
        [
            row("1", date_received="2026-07-20T12:34:56.789Z"),
            row("2", date_received="2011-12-01"),
        ],
    )

    report = clean_cfpb(config(tmp_path, input_path, chunk_size=chunk_size))

    assert report["date_format_counts"] == {
        "accepted_millisecond_utc_timestamp": 1,
        "accepted_plain_iso_date": 1,
        "null_date": 0,
        "exact_empty_date": 0,
        "whitespace_bearing_date": 0,
        "invalid_date_shape": 0,
        "impossible_calendar_date": 0,
        "out_of_profile_range_date": 0,
        "total_accepted_dates": 2,
        "total_classified_dates": 2,
    }
    assert report["counts"]["input_rows"] == 2
    assert report["counts"]["retained_rows"] == 2
    assert report["counts"]["rejected_rows"] == 0
    output = pd.read_csv(tmp_path / "complaints_cleaned.csv", dtype="string")
    assert output["Date received"].tolist() == ["2026-07-20", "2011-12-01"]


def test_date_diagnostics_are_independent_of_rejection_precedence(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "input.csv"
    write_input(
        input_path,
        [
            row(None, date_received="2011-12-01"),
            row("invalid", date_received="07/20/2026"),
            row("1", date_received="2026-07-20T00:00:00.000Z"),
        ],
    )

    report = clean_cfpb(config(tmp_path, input_path))

    assert report["rejection_reasons"]["invalid_complaint_id"] == 2
    assert report["rejection_reasons"]["invalid_date_received"] == 0
    assert report["date_format_counts"]["accepted_plain_iso_date"] == 1
    assert report["date_format_counts"]["accepted_millisecond_utc_timestamp"] == 1
    assert report["date_format_counts"]["invalid_date_shape"] == 1
    assert report["date_format_counts"]["total_accepted_dates"] == 2
    assert report["date_format_counts"]["total_classified_dates"] == 3
    assert report["counts"] == {
        "input_rows": 3,
        "retained_rows": 1,
        "rejected_rows": 2,
        "chunks_processed": 2,
        "reconciliation_valid": True,
    }


def test_failure_while_publishing_csv_leaves_no_completed_pair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "input.csv"
    write_input(input_path, [row("1")])
    cleaning_config = config(tmp_path, input_path)
    real_replace = os.replace

    def fail_csv_publish(source: str | Path, destination: str | Path) -> None:
        if Path(destination) == cleaning_config.output_path:
            raise OSError("synthetic CSV publication failure")
        real_replace(source, destination)

    monkeypatch.setattr("scripts.cfpb_cleaning.os.replace", fail_csv_publish)

    with pytest.raises(PublicationError, match="previous local artifacts were restored"):
        clean_cfpb(cleaning_config)

    assert not cleaning_config.output_path.exists()
    assert not cleaning_config.report_path.exists()
    assert_no_publication_locks(tmp_path)


def test_failure_while_publishing_report_leaves_no_completion_marker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "input.csv"
    write_input(input_path, [row("1")])
    cleaning_config = config(tmp_path, input_path)
    real_replace = os.replace

    def fail_report_publish(source: str | Path, destination: str | Path) -> None:
        if Path(destination) == cleaning_config.report_path:
            raise OSError("synthetic report publication failure")
        real_replace(source, destination)

    monkeypatch.setattr("scripts.cfpb_cleaning.os.replace", fail_report_publish)

    with pytest.raises(PublicationError, match="previous local artifacts were restored"):
        clean_cfpb(cleaning_config)

    assert not cleaning_config.output_path.exists()
    assert not cleaning_config.report_path.exists()
    assert_no_publication_locks(tmp_path)


def test_shared_report_lock_blocks_different_output_run(tmp_path: Path) -> None:
    first_input = tmp_path / "first-input.csv"
    second_input = tmp_path / "second-input.csv"
    write_input(first_input, [row("1")])
    write_input(second_input, [row("2")])
    shared_report = tmp_path / "shared-report.json"
    first_output = tmp_path / "first.csv"
    second_output = tmp_path / "second.csv"
    first_locks = _publication_lock_paths(first_output, shared_report)
    acquired = _acquire_publication_locks(first_locks, "synthetic-first-run")
    try:
        with pytest.raises(RecoveryRequiredError) as caught:
            clean_cfpb(
                CleaningConfig(
                    second_input,
                    second_output,
                    shared_report,
                    chunk_size=1,
                )
            )
        assert_private_error(caught.value)
        assert shared_report.with_name(f".{shared_report.name}.publish.lock").exists()
        assert not second_output.with_name(f".{second_output.name}.publish.lock").exists()
        assert not second_output.exists()
        assert not shared_report.exists()
    finally:
        _release_publication_locks(acquired, "synthetic-first-run")
    assert_no_publication_locks(tmp_path)


def test_partial_lock_acquisition_releases_only_current_run_lock(tmp_path: Path) -> None:
    output = tmp_path / "z-output.csv"
    report = tmp_path / "a-report.json"
    lock_paths = _publication_lock_paths(output, report)
    assert len(lock_paths) == 2
    foreign_lock = lock_paths[1]
    foreign_lock.write_text("foreign-run", encoding="utf-8")

    with pytest.raises(RecoveryRequiredError):
        _acquire_publication_locks(lock_paths, "current-run")

    assert not lock_paths[0].exists()
    assert foreign_lock.read_text(encoding="utf-8") == "foreign-run"


def test_lock_order_is_deterministic_and_deduplicated(tmp_path: Path) -> None:
    first = tmp_path / "z.csv"
    second = tmp_path / "a.json"

    forward = _publication_lock_paths(first, second)
    reverse = _publication_lock_paths(second, first)

    assert forward == reverse
    assert forward == tuple(
        sorted(forward, key=lambda path: os.path.normcase(str(path.resolve())))
    )
    assert len(_publication_lock_paths(first, first)) == 1


def test_overwrite_report_failure_restores_previous_matching_pair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "input.csv"
    write_input(input_path, [row("1", narrative="Original synthetic complaint")])
    original_config = config(tmp_path, input_path)
    original_report = clean_cfpb(original_config)
    original_csv_bytes = original_config.output_path.read_bytes()
    original_report_text = original_config.report_path.read_text(encoding="utf-8")
    write_input(input_path, [row("2", narrative="Replacement synthetic complaint")])
    real_replace = os.replace
    failed = False

    def fail_new_report_once(source: str | Path, destination: str | Path) -> None:
        nonlocal failed
        if (
            not failed
            and Path(source).suffix == ".tmp"
            and Path(destination) == original_config.report_path
        ):
            failed = True
            raise OSError("synthetic replacement report failure")
        real_replace(source, destination)

    monkeypatch.setattr("scripts.cfpb_cleaning.os.replace", fail_new_report_once)

    with pytest.raises(PublicationError, match="previous local artifacts were restored"):
        clean_cfpb(config(tmp_path, input_path, overwrite=True))

    restored_report = validate_completed_pair(
        original_config.output_path,
        original_config.report_path,
    )
    assert restored_report["run_id"] == original_report["run_id"]
    assert original_config.output_path.read_bytes() == original_csv_bytes
    assert original_config.report_path.read_text(encoding="utf-8") == original_report_text
    assert list(tmp_path.glob("*.backup")) == []
    assert list(tmp_path.glob(".*.backup")) == []
    assert_no_publication_locks(tmp_path)


@pytest.mark.parametrize(
    "failure_point",
    ["move_old_report", "move_old_csv", "publish_new_csv", "publish_new_report"],
)
def test_overwrite_filesystem_failures_restore_exact_previous_pair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_point: str,
) -> None:
    input_path, cleaning_config, original_report = create_valid_pair(tmp_path)
    original_csv = cleaning_config.output_path.read_bytes()
    original_report_text = cleaning_config.report_path.read_text(encoding="utf-8")
    sentinel = tmp_path / "unrelated.keep"
    sentinel.write_text("preserve", encoding="utf-8")
    write_input(input_path, [row("2", narrative="Replacement synthetic complaint")])
    real_replace = os.replace
    failed = False

    def injected_replace(source: str | Path, destination: str | Path) -> None:
        nonlocal failed
        source_path = Path(source)
        destination_path = Path(destination)
        should_fail = {
            "move_old_report": source_path == cleaning_config.report_path,
            "move_old_csv": source_path == cleaning_config.output_path,
            "publish_new_csv": (
                source_path.suffix == ".tmp"
                and destination_path == cleaning_config.output_path
            ),
            "publish_new_report": (
                source_path.suffix == ".tmp"
                and destination_path == cleaning_config.report_path
            ),
        }[failure_point]
        if should_fail and not failed:
            failed = True
            raise OSError("synthetic publication operation failure")
        real_replace(source, destination)

    monkeypatch.setattr("scripts.cfpb_cleaning.os.replace", injected_replace)

    with pytest.raises(PublicationError) as caught:
        clean_cfpb(config(tmp_path, input_path, overwrite=True))

    assert_private_error(caught.value)
    restored = validate_completed_pair(
        cleaning_config.output_path,
        cleaning_config.report_path,
    )
    assert restored["run_id"] == original_report["run_id"]
    assert cleaning_config.output_path.read_bytes() == original_csv
    assert cleaning_config.report_path.read_text(encoding="utf-8") == original_report_text
    assert sentinel.read_text(encoding="utf-8") == "preserve"
    assert list(tmp_path.glob(".*.backup")) == []
    assert_no_publication_locks(tmp_path)


def test_successful_overwrite_replaces_pair_and_removes_current_run_backups(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "input.csv"
    write_input(input_path, [row("1", narrative="Original synthetic complaint")])
    cleaning_config = config(tmp_path, input_path)
    original_report = clean_cfpb(cleaning_config)
    write_input(input_path, [row("2", narrative="Replacement synthetic complaint")])

    replacement_report = clean_cfpb(config(tmp_path, input_path, overwrite=True))
    validated = validate_completed_pair(
        cleaning_config.output_path,
        cleaning_config.report_path,
    )

    assert replacement_report["run_id"] != original_report["run_id"]
    assert validated["run_id"] == replacement_report["run_id"]
    assert list(tmp_path.glob(".*.backup")) == []
    assert_no_publication_locks(tmp_path)


def test_production_recovery_validates_restored_pair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path, cleaning_config, original_report = create_valid_pair(tmp_path)
    write_input(input_path, [row("2", narrative="Replacement synthetic complaint")])
    real_validate = validate_completed_pair
    real_replace = os.replace
    validation_calls = 0
    failed_publish = False

    def counting_validate(output: Path, report: Path) -> dict[str, object]:
        nonlocal validation_calls
        validation_calls += 1
        return real_validate(output, report)

    def fail_report_once(source: str | Path, destination: str | Path) -> None:
        nonlocal failed_publish
        if (
            not failed_publish
            and Path(source).suffix == ".tmp"
            and Path(destination) == cleaning_config.report_path
        ):
            failed_publish = True
            raise OSError("synthetic report failure")
        real_replace(source, destination)

    monkeypatch.setattr("scripts.cfpb_cleaning.validate_completed_pair", counting_validate)
    monkeypatch.setattr("scripts.cfpb_cleaning.os.replace", fail_report_once)

    with pytest.raises(PublicationError):
        clean_cfpb(config(tmp_path, input_path, overwrite=True))

    assert validation_calls == 2
    restored = real_validate(cleaning_config.output_path, cleaning_config.report_path)
    assert restored["run_id"] == original_report["run_id"]
    assert_no_publication_locks(tmp_path)


def test_new_pair_validation_failure_restores_previous_pair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path, cleaning_config, original_report = create_valid_pair(tmp_path)
    write_input(input_path, [row("2", narrative="Replacement synthetic complaint")])
    real_validate = validate_completed_pair
    validation_calls = 0

    def fail_new_validation(output: Path, report: Path) -> dict[str, object]:
        nonlocal validation_calls
        validation_calls += 1
        if validation_calls == 2:
            raise PairValidationError("synthetic new-pair validation failure")
        return real_validate(output, report)

    monkeypatch.setattr("scripts.cfpb_cleaning.validate_completed_pair", fail_new_validation)

    with pytest.raises(PublicationError):
        clean_cfpb(config(tmp_path, input_path, overwrite=True))

    assert validation_calls == 3
    restored = real_validate(cleaning_config.output_path, cleaning_config.report_path)
    assert restored["run_id"] == original_report["run_id"]
    assert list(tmp_path.glob(".*.backup")) == []
    assert_no_publication_locks(tmp_path)


@pytest.mark.parametrize("restore_target", ["csv", "report"])
def test_restore_copy_failure_preserves_recovery_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    restore_target: str,
) -> None:
    input_path, cleaning_config, _ = create_valid_pair(tmp_path)
    write_input(input_path, [row("2", narrative="Replacement synthetic complaint")])
    real_replace = os.replace
    real_copy = shutil.copy2
    failed_publish = False

    def fail_report_once(source: str | Path, destination: str | Path) -> None:
        nonlocal failed_publish
        if (
            not failed_publish
            and Path(source).suffix == ".tmp"
            and Path(destination) == cleaning_config.report_path
        ):
            failed_publish = True
            raise OSError("synthetic report publication failure")
        real_replace(source, destination)

    def fail_restore_copy(source: str | Path, destination: str | Path) -> None:
        destination_path = Path(destination)
        if (
            restore_target == "csv"
            and destination_path == cleaning_config.output_path
        ) or (
            restore_target == "report"
            and destination_path == cleaning_config.report_path
        ):
            raise OSError("synthetic restoration copy failure")
        real_copy(source, destination)

    monkeypatch.setattr("scripts.cfpb_cleaning.os.replace", fail_report_once)
    monkeypatch.setattr("scripts.cfpb_cleaning.shutil.copy2", fail_restore_copy)

    with pytest.raises(RecoveryRequiredError) as caught:
        clean_cfpb(config(tmp_path, input_path, overwrite=True))

    assert_private_error(caught.value)
    assert len(list(tmp_path.glob(".*.backup"))) == 2
    assert_no_publication_locks(tmp_path)


def test_restored_pair_validation_failure_preserves_recovery_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path, cleaning_config, _ = create_valid_pair(tmp_path)
    write_input(input_path, [row("2", narrative="Replacement synthetic complaint")])
    real_validate = validate_completed_pair
    real_replace = os.replace
    validation_calls = 0
    failed_publish = False
    replacement_run_id = "restored-validation-failure-run"
    monkeypatch.setattr(
        "scripts.cfpb_cleaning.uuid.uuid4",
        lambda: type("SyntheticUuid", (), {"hex": replacement_run_id})(),
    )

    def fail_restored_validation(output: Path, report: Path) -> dict[str, object]:
        nonlocal validation_calls
        validation_calls += 1
        if validation_calls == 2:
            raise PairValidationError("synthetic restored-pair validation failure")
        return real_validate(output, report)

    def fail_report_once(source: str | Path, destination: str | Path) -> None:
        nonlocal failed_publish
        if (
            not failed_publish
            and Path(source).suffix == ".tmp"
            and Path(destination) == cleaning_config.report_path
        ):
            failed_publish = True
            raise OSError("synthetic report publication failure")
        real_replace(source, destination)

    monkeypatch.setattr("scripts.cfpb_cleaning.validate_completed_pair", fail_restored_validation)
    monkeypatch.setattr("scripts.cfpb_cleaning.os.replace", fail_report_once)

    with pytest.raises(RecoveryRequiredError) as caught:
        clean_cfpb(config(tmp_path, input_path, overwrite=True))

    assert_private_error(caught.value)
    assert validation_calls == 2
    assert set(tmp_path.glob(".*.backup")) == {
        _backup_path(cleaning_config.output_path, replacement_run_id),
        _backup_path(cleaning_config.report_path, replacement_run_id),
    }
    assert_no_publication_locks(tmp_path)


@pytest.mark.parametrize(
    (
        "output_name",
        "report_name",
        "failed_backup_kind",
        "remaining_backup_kinds",
    ),
    [
        ("complaints.csv", "cleaning.json", "report", ("csv", "report")),
        ("complaints.csv", "cleaning.json", "csv", ("csv",)),
        ("a.csv", "z.json", "csv", ("csv", "report")),
        ("a.csv", "z.json", "report", ("report",)),
    ],
)
def test_backup_cleanup_failure_preserves_valid_new_pair_and_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    output_name: str,
    report_name: str,
    failed_backup_kind: str,
    remaining_backup_kinds: tuple[str, ...],
) -> None:
    input_path, cleaning_config, original_report = create_valid_pair(
        tmp_path,
        output_name=output_name,
        report_name=report_name,
    )
    write_input(input_path, [row("2", narrative="Replacement synthetic complaint")])
    real_unlink = os.unlink
    failed = False
    replacement_run_id = "backup-cleanup-failure-run"
    monkeypatch.setattr(
        "scripts.cfpb_cleaning.uuid.uuid4",
        lambda: type("SyntheticUuid", (), {"hex": replacement_run_id})(),
    )

    def fail_selected_backup(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        *,
        dir_fd: int | None = None,
    ) -> None:
        nonlocal failed
        path_object = Path(path)
        is_target = (
            path_object.name.endswith(".backup")
            and (
                (
                    failed_backup_kind == "csv"
                    and cleaning_config.output_path.name in path_object.name
                )
                or (
                    failed_backup_kind == "report"
                    and cleaning_config.report_path.name in path_object.name
                )
            )
        )
        if is_target and not failed:
            failed = True
            raise OSError("synthetic backup cleanup failure")
        if dir_fd is None:
            real_unlink(path)
        else:
            real_unlink(path, dir_fd=dir_fd)

    monkeypatch.setattr(os, "unlink", fail_selected_backup)

    with pytest.raises(
        RecoveryRequiredError,
        match="valid but backup cleanup is incomplete",
    ) as caught:
        clean_cfpb(
            config(
                tmp_path,
                input_path,
                output_path=cleaning_config.output_path,
                report_path=cleaning_config.report_path,
                overwrite=True,
            )
        )

    assert_private_error(caught.value)
    validated_new = validate_completed_pair(
        cleaning_config.output_path,
        cleaning_config.report_path,
    )
    assert validated_new["run_id"] == replacement_run_id
    assert validated_new["run_id"] != original_report["run_id"]
    backup_by_kind = {
        "csv": _backup_path(cleaning_config.output_path, replacement_run_id),
        "report": _backup_path(cleaning_config.report_path, replacement_run_id),
    }
    assert set(tmp_path.glob(".*.backup")) == {
        backup_by_kind[kind] for kind in remaining_backup_kinds
    }
    assert_no_publication_locks(tmp_path)
    with pytest.raises(RecoveryRequiredError) as retry_caught:
        clean_cfpb(
            config(
                tmp_path,
                input_path,
                output_path=cleaning_config.output_path,
                report_path=cleaning_config.report_path,
                overwrite=True,
            )
        )
    assert_private_error(retry_caught.value)
    assert set(tmp_path.glob(".*.backup")) == {
        backup_by_kind[kind] for kind in remaining_backup_kinds
    }
    assert_no_publication_locks(tmp_path)


@pytest.mark.parametrize("recovery_state", ["backup", "lock"])
def test_startup_refuses_existing_recovery_state(
    tmp_path: Path,
    recovery_state: str,
) -> None:
    input_path = tmp_path / "input.csv"
    write_input(input_path, [row("1")])
    cleaning_config = config(tmp_path, input_path)
    if recovery_state == "backup":
        artifact = cleaning_config.output_path.with_name(
            f".{cleaning_config.output_path.name}.older-run.backup"
        )
    else:
        artifact = cleaning_config.output_path.with_name(
            f".{cleaning_config.output_path.name}.publish.lock"
        )
    artifact.write_text("synthetic recovery state", encoding="utf-8")

    with pytest.raises(RecoveryRequiredError):
        clean_cfpb(cleaning_config)

    assert artifact.exists()
    assert not cleaning_config.output_path.exists()
    assert not cleaning_config.report_path.exists()


@pytest.mark.parametrize("invalid_state", ["missing_csv", "missing_report", "malformed", "mismatch"])
def test_invalid_previous_state_is_rejected_before_backup_moves(
    tmp_path: Path,
    invalid_state: str,
) -> None:
    _, cleaning_config, _ = create_valid_pair(tmp_path)
    if invalid_state == "missing_csv":
        cleaning_config.output_path.unlink()
    elif invalid_state == "missing_report":
        cleaning_config.report_path.unlink()
    elif invalid_state == "malformed":
        cleaning_config.report_path.write_text("{", encoding="utf-8")
    else:
        data = json.loads(cleaning_config.report_path.read_text(encoding="utf-8"))
        data["completion"]["csv_sha256"] = "0" * 64
        cleaning_config.report_path.write_text(json.dumps(data), encoding="utf-8")
    before = {
        path.name: path.read_bytes()
        for path in (cleaning_config.output_path, cleaning_config.report_path)
        if path.exists()
    }

    with pytest.raises(RecoveryRequiredError) as caught:
        clean_cfpb(
            config(
                tmp_path,
                cleaning_config.input_path,
                overwrite=True,
            )
        )

    assert_private_error(caught.value)
    after = {
        path.name: path.read_bytes()
        for path in (cleaning_config.output_path, cleaning_config.report_path)
        if path.exists()
    }
    assert after == before
    assert set(tmp_path.glob(".*.backup")) == set()
    assert_no_publication_locks(tmp_path)


def test_foreign_completion_marker_is_preserved_and_refused(tmp_path: Path) -> None:
    input_path, first_config, first_report = create_valid_pair(
        tmp_path,
        output_name="first.csv",
        report_name="shared-report.json",
    )
    original_csv = first_config.output_path.read_bytes()
    original_report = first_config.report_path.read_text(encoding="utf-8")
    second_output = tmp_path / "second.csv"

    with pytest.raises(
        RecoveryRequiredError,
        match="foreign completion marker",
    ) as caught:
        clean_cfpb(
            config(
                tmp_path,
                input_path,
                output_path=second_output,
                report_path=first_config.report_path,
                overwrite=True,
            )
        )

    assert_private_error(caught.value)
    assert first_config.output_path.read_bytes() == original_csv
    assert first_config.report_path.read_text(encoding="utf-8") == original_report
    assert validate_completed_pair(
        first_config.output_path,
        first_config.report_path,
    )["run_id"] == first_report["run_id"]
    assert not second_output.exists()
    assert set(tmp_path.glob(".*.backup")) == set()
    assert_no_publication_locks(tmp_path)


@pytest.mark.parametrize(
    "mismatch",
    ["hash", "size", "run_id", "row_count", "filename", "schema"],
)
def test_completed_pair_validation_rejects_metadata_mismatch(
    tmp_path: Path,
    mismatch: str,
) -> None:
    input_path = tmp_path / "input.csv"
    write_input(input_path, [row("1")])
    cleaning_config = config(tmp_path, input_path)
    clean_cfpb(cleaning_config)
    report = json.loads(cleaning_config.report_path.read_text(encoding="utf-8"))

    if mismatch == "hash":
        report["completion"]["csv_sha256"] = "0" * 64
    elif mismatch == "size":
        report["completion"]["csv_size_bytes"] += 1
    elif mismatch == "run_id":
        report["completion"]["run_id"] = "different-synthetic-run"
    elif mismatch == "row_count":
        report["completion"]["retained_row_count"] += 1
    elif mismatch == "filename":
        report["completion"]["csv_file_name"] = "different.csv"
    else:
        report["schema"]["cleaned_columns"] = ["wrong"]
    cleaning_config.report_path.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(PairValidationError):
        validate_completed_pair(
            cleaning_config.output_path,
            cleaning_config.report_path,
        )


def test_new_reports_use_version_two_and_validate_date_counts(tmp_path: Path) -> None:
    _, cleaning_config, _ = create_valid_pair(tmp_path)
    report = json.loads(cleaning_config.report_path.read_text(encoding="utf-8"))

    assert report["report_schema_version"] == 2
    assert validate_completed_pair(
        cleaning_config.output_path,
        cleaning_config.report_path,
    )["report_schema_version"] == 2


@pytest.mark.parametrize(
    ("csv_path", "report_path", "run_id"),
    [
        (
            Path("data/interim/cfpb/complaints_cleaned.csv"),
            Path("data/cfpb_cleaning_full_report.json"),
            "ae691665a9bd4ee68eff41991f5e4075",
        ),
        (
            Path("data/interim/cfpb/complaints_cleaned_smoke.csv"),
            Path("data/cfpb_cleaning_report.json"),
            "a41f53c53c7841289a15d3c07bb192c4",
        ),
    ],
)
def test_approved_legacy_pairs_validate(
    csv_path: Path,
    report_path: Path,
    run_id: str,
) -> None:
    report = validate_completed_pair(csv_path, report_path)
    assert report["completion"]["run_id"] == run_id


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_date_counts",
        "missing_counter",
        "non_integer_counter",
        "negative_counter",
        "inconsistent_classified",
        "inconsistent_accepted",
        "input_row_mismatch",
        "unsupported_version",
        "unmarked_unrecognized",
    ],
)
def test_report_schema_version_two_enforcement(
    tmp_path: Path,
    mutation: str,
) -> None:
    _, cleaning_config, _ = create_valid_pair(tmp_path)
    report = json.loads(cleaning_config.report_path.read_text(encoding="utf-8"))
    if mutation == "missing_date_counts":
        report.pop("date_format_counts")
    elif mutation == "missing_counter":
        report["date_format_counts"].pop("total_classified_dates")
    elif mutation == "non_integer_counter":
        report["date_format_counts"]["null_date"] = True
    elif mutation == "negative_counter":
        report["date_format_counts"]["null_date"] = -1
    elif mutation == "inconsistent_classified":
        report["date_format_counts"]["total_classified_dates"] += 1
    elif mutation == "inconsistent_accepted":
        report["date_format_counts"]["total_accepted_dates"] += 1
    elif mutation == "input_row_mismatch":
        report["counts"]["input_rows"] += 1
    elif mutation == "unsupported_version":
        report["report_schema_version"] = 99
    else:
        report.pop("report_schema_version")
        report["run_id"] = "unrecognized-synthetic-run"
        report["completion"]["run_id"] = "unrecognized-synthetic-run"
    cleaning_config.report_path.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(PairValidationError):
        validate_completed_pair(
            cleaning_config.output_path,
            cleaning_config.report_path,
        )


@pytest.mark.parametrize(
    "invalid_pair",
    [
        "missing_csv",
        "missing_report",
        "incomplete_status",
        "truncated_csv",
        "schema_mismatch",
    ],
)
def test_completed_pair_validation_rejects_missing_incomplete_or_corrupt_pair(
    tmp_path: Path,
    invalid_pair: str,
) -> None:
    _, cleaning_config, _ = create_valid_pair(tmp_path)
    if invalid_pair == "missing_csv":
        cleaning_config.output_path.unlink()
    elif invalid_pair == "missing_report":
        cleaning_config.report_path.unlink()
    elif invalid_pair == "incomplete_status":
        report = json.loads(cleaning_config.report_path.read_text(encoding="utf-8"))
        report["completion"]["status"] = "incomplete"
        cleaning_config.report_path.write_text(json.dumps(report), encoding="utf-8")
    elif invalid_pair == "truncated_csv":
        with cleaning_config.output_path.open("r+b") as output:
            output.truncate(max(1, cleaning_config.output_path.stat().st_size // 2))
    else:
        cleaning_config.output_path.write_text(
            "wrong,header\nsynthetic,value\n",
            encoding="utf-8",
        )

    with pytest.raises(PairValidationError):
        validate_completed_pair(
            cleaning_config.output_path,
            cleaning_config.report_path,
        )


@pytest.mark.parametrize(
    ("malformed_target", "malformed_value"),
    [
        ("top", []),
        ("top", None),
        ("top", "text"),
        ("completion", []),
        ("completion", None),
        ("completion", "text"),
        ("counts", []),
        ("counts", None),
        ("counts", "text"),
        ("schema", []),
        ("schema", None),
        ("schema", "text"),
        ("missing_completion", None),
        ("missing_counts", None),
        ("missing_schema", None),
    ],
)
def test_completed_pair_validation_rejects_malformed_report_structures(
    tmp_path: Path,
    malformed_target: str,
    malformed_value: object,
) -> None:
    _, cleaning_config, _ = create_valid_pair(tmp_path)
    if malformed_target == "top":
        report: object = malformed_value
    else:
        report = json.loads(cleaning_config.report_path.read_text(encoding="utf-8"))
        assert isinstance(report, dict)
        if malformed_target.startswith("missing_"):
            report.pop(malformed_target.removeprefix("missing_"))
        else:
            report[malformed_target] = malformed_value
    cleaning_config.report_path.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(PairValidationError):
        validate_completed_pair(
            cleaning_config.output_path,
            cleaning_config.report_path,
        )


def test_completed_pair_validation_rejects_malformed_json(tmp_path: Path) -> None:
    _, cleaning_config, _ = create_valid_pair(tmp_path)
    cleaning_config.report_path.write_text("{", encoding="utf-8")

    with pytest.raises(PairValidationError):
        validate_completed_pair(
            cleaning_config.output_path,
            cleaning_config.report_path,
        )


def test_max_rows_and_max_chunks_bound_processing(tmp_path: Path) -> None:
    input_path = tmp_path / "input.csv"
    write_input(input_path, [row(str(number)) for number in range(1, 7)])

    max_rows_report = clean_cfpb(config(tmp_path, input_path, max_rows=3))
    assert max_rows_report["counts"]["input_rows"] == 3

    second_output = tmp_path / "second.csv"
    second_report = tmp_path / "second.json"
    max_chunks_report = clean_cfpb(
        config(
            tmp_path,
            input_path,
            output_path=second_output,
            report_path=second_report,
            max_chunks=2,
        )
    )
    assert max_chunks_report["counts"]["input_rows"] == 4
    assert max_chunks_report["counts"]["chunks_processed"] == 2


def test_report_contains_aggregate_data_without_row_values(tmp_path: Path) -> None:
    input_path = tmp_path / "input.csv"
    secret_narrative = "Unique synthetic narrative token"
    write_input(input_path, [row("987654", narrative=secret_narrative)])

    clean_cfpb(config(tmp_path, input_path))
    report_text = (tmp_path / "cleaning_report.json").read_text(encoding="utf-8")

    assert secret_narrative not in report_text
    assert "987654" not in report_text
    assert str(tmp_path) not in report_text
