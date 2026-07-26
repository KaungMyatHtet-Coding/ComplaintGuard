from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from scripts.cfpb_label_mapping import (
    ALLOWED_DEPARTMENTS,
    CLEANED_COLUMNS,
    OUTPUT_COLUMNS,
    BuildConfig,
    MappingError,
    build_training_dataset,
    load_mapping_policy,
    map_department,
    normalize_category,
)

MAPPING_PATH = (
    Path(__file__).parents[2] / "data" / "mapping" / "cfpb_department_mapping_v1.json"
)


def synthetic_row(
    row_id: str,
    narrative: str,
    product: str | None,
    issue: str | None,
) -> dict[str, str | None]:
    return {
        "Complaint ID": row_id,
        "Date received": "2020-01-01",
        "Consumer complaint narrative": narrative,
        "Product": product,
        "Issue": issue,
        "Sub-product": None,
        "Sub-issue": None,
    }


def prepare(
    tmp_path: Path,
    rows: list[dict[str, str | None]],
    *,
    chunk_size: int = 2,
) -> BuildConfig:
    input_path = tmp_path / "synthetic_cleaned.csv"
    pd.DataFrame(rows, columns=CLEANED_COLUMNS).to_csv(input_path, index=False)
    report_path = tmp_path / "cleaning_report.json"
    report_path.write_text(
        json.dumps(
            {
                "report_schema_version": 2,
                "status": "completed",
                "run_id": "synthetic-cleaning-run",
                "counts": {"retained_rows": len(rows)},
            }
        ),
        encoding="utf-8",
    )
    return BuildConfig(
        input_path=input_path,
        cleaning_report_path=report_path,
        mapping_path=MAPPING_PATH,
        output_path=tmp_path / "training_v1.csv",
        manifest_path=tmp_path / "training_v1_manifest.json",
        chunk_size=chunk_size,
        expected_rows=len(rows),
        expected_cleaning_run_id="synthetic-cleaning-run",
    )


@pytest.mark.parametrize(
    ("product", "issue", "expected"),
    [
        (
            "Money transfer, virtual currency, or money service",
            "Other transaction problem",
            "transfer_payment",
        ),
        ("Checking or savings account", "Managing an account", "account_support"),
        ("Credit card", "Fees or interest", "card_atm"),
        (
            "Credit reporting or other personal consumer reports",
            "Incorrect information on your report",
            "fraud_security",
        ),
        ("Mortgage", "Trouble during payment process", "loan_credit"),
        ("Unmapped synthetic product", "Unmapped synthetic issue", "general_support"),
    ],
)
def test_all_six_department_labels(
    product: str,
    issue: str,
    expected: str,
) -> None:
    policy = load_mapping_policy(MAPPING_PATH)
    label, _ = map_department(product, issue, policy)
    assert label == expected
    assert label in ALLOWED_DEPARTMENTS


def test_exact_pair_precedes_product_fallback() -> None:
    policy = load_mapping_policy(MAPPING_PATH)
    label, method = map_department(
        "Money transfer, virtual currency, or money service",
        "Fraud or scam",
        policy,
    )
    assert (label, method) == ("fraud_security", "exact_product_issue")


def test_product_fallback_is_reported() -> None:
    policy = load_mapping_policy(MAPPING_PATH)
    label, method = map_department(
        "Money transfer, virtual currency, or money service",
        "Other transaction problem",
        policy,
    )
    assert (label, method) == ("transfer_payment", "product_fallback")


@pytest.mark.parametrize(
    ("product", "issue"),
    [
        (None, "Synthetic issue"),
        ("Synthetic unknown product", "Synthetic unknown issue"),
        ("Debt collection", "Communication tactics"),
    ],
)
def test_general_support_fallback(product: str | None, issue: str) -> None:
    policy = load_mapping_policy(MAPPING_PATH)
    assert map_department(product, issue, policy) == (
        "general_support",
        "general_support",
    )


def test_missing_issue_uses_known_product_fallback() -> None:
    policy = load_mapping_policy(MAPPING_PATH)
    assert map_department("Mortgage", None, policy) == (
        "loan_credit",
        "product_fallback",
    )


def test_normalization_is_nfkc_trimmed_collapsed_and_casefolded() -> None:
    policy = load_mapping_policy(MAPPING_PATH)
    assert normalize_category("  CREDIT   CARD  ") == "credit card"
    assert map_department("  CREDIT   CARD  ", " Fees or interest ", policy) == (
        "card_atm",
        "product_fallback",
    )


def test_label_is_independent_of_narrative_text(tmp_path: Path) -> None:
    rows = [
        synthetic_row(
            "synthetic-1",
            "First fully synthetic narrative.",
            "Mortgage",
            "Trouble during payment process",
        ),
        synthetic_row(
            "synthetic-2",
            "Completely different synthetic words.",
            "Mortgage",
            "Trouble during payment process",
        ),
    ]
    config = prepare(tmp_path, rows, chunk_size=1)
    build_training_dataset(config)
    output = pd.read_csv(config.output_path)
    assert output["department_label"].tolist() == ["loan_credit", "loan_credit"]


def test_chunk_boundaries_schema_versions_and_reconciliation(tmp_path: Path) -> None:
    rows = [
        synthetic_row(
            "synthetic-1", "Synthetic transfer text.", "Money transfers", "Fees"
        ),
        synthetic_row(
            "synthetic-2",
            "Synthetic account text.",
            "Checking or savings account",
            "Managing an account",
        ),
        synthetic_row(
            "synthetic-3",
            "Synthetic fallback text.",
            "Synthetic unknown product",
            "Synthetic unknown issue",
        ),
    ]
    config = prepare(tmp_path, rows, chunk_size=1)
    manifest = build_training_dataset(config)
    output = pd.read_csv(config.output_path)
    assert output.columns.tolist() == list(OUTPUT_COLUMNS)
    assert len(output) == 3
    assert manifest["dataset_version"] == "v1"
    assert manifest["mapping_version"] == "v1"
    assert manifest["processing"]["chunks_processed"] == 3
    assert manifest["processing"]["row_reconciliation_valid"] is True
    assert sum(manifest["label_counts"].values()) == 3
    assert sum(manifest["mapping_method_counts"].values()) == 3
    assert set(manifest["label_counts"]) == set(ALLOWED_DEPARTMENTS)
    assert manifest["labeling_integrity"]["one_label_per_row"] is True
    assert manifest["labeling_integrity"]["allowed_label_set_valid"] is True


def test_missing_values_are_counted_without_row_loss(tmp_path: Path) -> None:
    rows = [
        synthetic_row(
            "synthetic-1", "Synthetic missing product.", None, "Synthetic issue"
        ),
        synthetic_row("synthetic-2", "Synthetic missing issue.", "Mortgage", None),
    ]
    config = prepare(tmp_path, rows)
    manifest = build_training_dataset(config)
    assert manifest["missing_values"]["Product"] == 1
    assert manifest["missing_values"]["Issue"] == 1
    assert manifest["processing"]["output_rows"] == 2


def test_fallback_audit_distinguishes_unresolved_from_unknown(tmp_path: Path) -> None:
    rows = [
        synthetic_row(
            "synthetic-1",
            "Synthetic unresolved taxonomy.",
            "Debt collection",
            "Communication tactics",
        ),
        synthetic_row(
            "synthetic-2",
            "Synthetic unknown taxonomy.",
            "Synthetic unknown product",
            "Synthetic unknown issue",
        ),
    ]
    config = prepare(tmp_path, rows)
    manifest = build_training_dataset(config)
    assert manifest["fallback_audit"] == {
        "unknown_products": {"Synthetic unknown product": 1},
        "intentionally_unresolved_products": {"Debt collection": 1},
    }


def test_manifest_is_aggregate_only_and_omits_ids_and_narratives(
    tmp_path: Path,
) -> None:
    narrative = "Unique synthetic narrative that must not enter metadata."
    config = prepare(
        tmp_path,
        [synthetic_row("synthetic-private-id", narrative, "Mortgage", "Fees")],
    )
    manifest = build_training_dataset(config)
    manifest_text = config.manifest_path.read_text(encoding="utf-8")
    assert manifest["privacy"] == {
        "aggregate_only_manifest": True,
        "contains_narratives": False,
        "contains_complaint_ids": False,
    }
    assert narrative not in manifest_text
    assert "synthetic-private-id" not in manifest_text
    assert "Complaint ID" not in manifest_text


def test_exact_schema_is_required(tmp_path: Path) -> None:
    config = prepare(
        tmp_path,
        [synthetic_row("synthetic-1", "Synthetic.", "Mortgage", "Fees")],
    )
    frame = pd.read_csv(config.input_path)
    frame.drop(columns=["Sub-issue"]).to_csv(config.input_path, index=False)
    with pytest.raises(MappingError, match="seven columns"):
        build_training_dataset(config)


def test_missing_narrative_fails_without_publication(tmp_path: Path) -> None:
    config = prepare(
        tmp_path,
        [synthetic_row("synthetic-1", None, "Mortgage", "Fees")],  # type: ignore[arg-type]
    )
    with pytest.raises(MappingError, match="missing narrative"):
        build_training_dataset(config)
    assert not config.output_path.exists()
    assert not config.manifest_path.exists()


def test_second_publication_failure_rolls_back_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = prepare(
        tmp_path,
        [synthetic_row("synthetic-1", "Synthetic.", "Mortgage", "Fees")],
    )
    real_replace = __import__("scripts.cfpb_label_mapping", fromlist=["os"]).os.replace
    calls = 0

    def fail_second(source: Path, destination: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("synthetic manifest publication failure")
        real_replace(source, destination)

    monkeypatch.setattr("scripts.cfpb_label_mapping.os.replace", fail_second)
    with pytest.raises(OSError, match="manifest publication failure"):
        build_training_dataset(config)
    assert calls == 2
    assert not config.output_path.exists()
    assert not config.manifest_path.exists()
    assert list(tmp_path.glob(".*.tmp")) == []


def test_existing_destination_is_never_overwritten(tmp_path: Path) -> None:
    config = prepare(
        tmp_path,
        [synthetic_row("synthetic-1", "Synthetic.", "Mortgage", "Fees")],
    )
    config.output_path.write_text("owner evidence", encoding="utf-8")
    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        build_training_dataset(config)
    assert config.output_path.read_text(encoding="utf-8") == "owner evidence"
