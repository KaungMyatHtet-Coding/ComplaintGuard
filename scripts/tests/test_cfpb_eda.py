from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pandas as pd
import pytest

from scripts.cfpb_eda import (
    CLEANED_COLUMNS,
    Aggregates,
    EDAConfig,
    EDAError,
    aggregate_csv,
    build_tables,
    run_eda,
)


def synthetic_row(
    row_id: str,
    date: str,
    product: str,
    issue: str,
    narrative: str,
) -> dict[str, str | None]:
    return {
        "Complaint ID": row_id,
        "Date received": date,
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
) -> EDAConfig:
    input_path = tmp_path / "synthetic.csv"
    pd.DataFrame(rows, columns=CLEANED_COLUMNS).to_csv(input_path, index=False)
    report_path = tmp_path / "cleaning.json"
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
    return EDAConfig(
        input_path=input_path,
        cleaning_report_path=report_path,
        output_dir=tmp_path / "aggregates",
        chart_dir=tmp_path / "charts",
        chunk_size=chunk_size,
        expected_rows=len(rows),
        expected_run_id="synthetic-cleaning-run",
    )


def sample_rows() -> list[dict[str, str | None]]:
    return [
        synthetic_row("1", "2020-01-01", "Cards", "Billing", "A" * 100),
        synthetic_row("2", "2020-02-01", "Cards", "Fees", "B" * 300),
        synthetic_row("3", "2021-01-01", "Loans", "Billing", "C" * 800),
    ]


def test_chunk_aggregation_year_month_categories_and_lengths(tmp_path: Path) -> None:
    aggregates = aggregate_csv(prepare(tmp_path, sample_rows(), chunk_size=1))
    tables = build_tables(aggregates)
    assert aggregates.rows == 3
    assert aggregates.chunks == 3
    assert aggregates.years == {"2020": 2, "2021": 1}
    assert aggregates.months == {"2020-01": 1, "2020-02": 1, "2021-01": 1}
    assert aggregates.products == {"Cards": 2, "Loans": 1}
    assert aggregates.issues == {"Billing": 2, "Fees": 1}
    assert sum(row["count"] for row in tables["narrative_length_buckets"]) == 3


def test_percentages_and_deterministic_tie_order(tmp_path: Path) -> None:
    rows = [
        synthetic_row("1", "2020-01-01", "Zulu", "Issue Z", "A"),
        synthetic_row("2", "2020-01-02", "Alpha", "Issue A", "B"),
    ]
    tables = build_tables(aggregate_csv(prepare(tmp_path, rows)))
    assert sum(float(row["percentage"]) for row in tables["products"]) == pytest.approx(
        100
    )
    assert [row["category"] for row in tables["products"]] == ["Alpha", "Zulu"]
    assert [row["category"] for row in tables["issues"]] == ["Issue A", "Issue Z"]


def test_required_schema_is_exact(tmp_path: Path) -> None:
    config = prepare(tmp_path, sample_rows())
    frame = pd.read_csv(config.input_path)
    frame.drop(columns=["Sub-issue"]).to_csv(config.input_path, index=False)
    with pytest.raises(EDAError, match="seven columns"):
        aggregate_csv(config)


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        ("Date received", "2020/01/01", "noncanonical date"),
        ("Date received", "2027-01-01", "outside approved"),
        ("Product", None, "missing required"),
        ("Issue", None, "missing required"),
        ("Consumer complaint narrative", None, "missing required"),
    ],
)
def test_invalid_cleaned_values_fail(
    tmp_path: Path,
    column: str,
    value: str | None,
    message: str,
) -> None:
    rows = sample_rows()
    rows[0][column] = value
    with pytest.raises(EDAError, match=message):
        aggregate_csv(prepare(tmp_path, rows))


def test_valid_leap_day_is_accepted(tmp_path: Path) -> None:
    rows = [synthetic_row("1", "2020-02-29", "Product", "Issue", "Text")]
    aggregates = aggregate_csv(prepare(tmp_path, rows))
    assert aggregates.years == {"2020": 1}
    assert aggregates.months == {"2020-02": 1}


@pytest.mark.parametrize(
    "date",
    [
        "2019-02-29",
        "2020-02-30",
        "2020-13-01",
        "2020-01-32",
    ],
)
def test_impossible_calendar_dates_fail_without_publication(
    tmp_path: Path, date: str
) -> None:
    rows = [synthetic_row("1", date, "Product", "Issue", "Text")]
    config = prepare(tmp_path, rows)
    with pytest.raises(EDAError, match="impossible calendar date"):
        run_eda(config)
    assert not config.output_dir.exists()
    assert not config.chart_dir.exists()


@pytest.mark.parametrize(
    ("date", "message"),
    [
        ("2020/02/29", "noncanonical date"),
        ("2011-11-30", "outside approved"),
        ("2026-07-21", "outside approved"),
    ],
)
def test_malformed_or_out_of_bounds_dates_fail_without_publication(
    tmp_path: Path, date: str, message: str
) -> None:
    rows = [synthetic_row("1", date, "Product", "Issue", "Text")]
    config = prepare(tmp_path, rows)
    with pytest.raises(EDAError, match=message):
        run_eda(config)
    assert not config.output_dir.exists()
    assert not config.chart_dir.exists()


def test_processed_row_mismatch_fails(tmp_path: Path) -> None:
    config = prepare(tmp_path, sample_rows())
    object.__setattr__(config, "expected_rows", 4)
    with pytest.raises(EDAError, match="cleaning report"):
        aggregate_csv(config)


def test_empty_input_reconciles_when_expected_zero(tmp_path: Path) -> None:
    aggregates = aggregate_csv(prepare(tmp_path, []))
    assert aggregates.rows == 0
    assert aggregates.chunks == 0


def test_run_publishes_aggregate_only_outputs(tmp_path: Path) -> None:
    config = prepare(tmp_path, sample_rows())
    metadata = run_eda(config)
    assert metadata["privacy"] == {
        "aggregate_only": True,
        "contains_narratives": False,
        "contains_complaint_ids": False,
    }
    report_text = (config.output_dir / "eda_metadata.json").read_text(encoding="utf-8")
    assert "A" * 100 not in report_text
    assert '"Complaint ID"' not in report_text
    assert len(list(config.chart_dir.glob("*.png"))) == 6


def test_narrative_length_bucket_boundaries(tmp_path: Path) -> None:
    lengths = [249, 250, 499, 500, 999, 1000, 1999, 2000]
    rows = [
        synthetic_row(str(index), "2020-01-01", "Product", "Issue", "X" * length)
        for index, length in enumerate(lengths, start=1)
    ]
    tables = build_tables(aggregate_csv(prepare(tmp_path, rows)))
    assert {
        row["bucket"]: row["count"] for row in tables["narrative_length_buckets"]
    } == {
        "0-249": 1,
        "250-499": 2,
        "500-999": 2,
        "1000-1999": 2,
        "2000+": 1,
    }


def test_descriptive_statistics_use_lower_nearest_rank() -> None:
    aggregates = Aggregates(
        rows=4,
        chunks=2,
        minimum_date="2020-01-01",
        maximum_date="2020-01-04",
        years=Counter({"2020": 4}),
        months=Counter({"2020-01": 4}),
        products=Counter({"Product": 4}),
        issues=Counter({"Issue": 4}),
        product_issue_pairs=Counter({("Product", "Issue"): 4}),
        narrative_lengths=Counter({1: 1, 2: 1, 3: 1, 10: 1}),
        narrative_characters=16,
    )
    statistics = build_tables(aggregates)["narrative_length_statistics"][0]
    assert statistics == {
        "count": 4,
        "minimum": 1,
        "mean": 4.0,
        "median": 2,
        "p90": 3,
        "p95": 3,
        "maximum": 10,
    }


def test_render_failure_publishes_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = prepare(tmp_path, sample_rows())

    def fail_render(*args: object, **kwargs: object) -> None:
        raise RuntimeError("synthetic chart failure")

    monkeypatch.setattr("scripts.cfpb_eda.render_charts", fail_render)
    with pytest.raises(RuntimeError, match="synthetic chart failure"):
        run_eda(config)
    assert not config.output_dir.exists()
    assert not config.chart_dir.exists()
    assert list(tmp_path.glob(".*.tmp")) == []


def test_staged_validation_failure_publishes_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = prepare(tmp_path, sample_rows())

    def fail_validation(*args: object, **kwargs: object) -> None:
        raise EDAError("synthetic staged validation failure")

    monkeypatch.setattr("scripts.cfpb_eda._validate_staged_packages", fail_validation)
    with pytest.raises(EDAError, match="staged validation failure"):
        run_eda(config)
    assert not config.output_dir.exists()
    assert not config.chart_dir.exists()
    assert list(tmp_path.glob(".*.tmp")) == []


def test_failure_after_chart_publication_rolls_back_without_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = prepare(tmp_path, sample_rows())

    def fail_after_first() -> None:
        assert config.chart_dir.is_dir()
        assert not (config.output_dir / "eda_metadata.json").exists()
        raise RuntimeError("synthetic post-chart failure")

    monkeypatch.setattr("scripts.cfpb_eda._after_first_publication", fail_after_first)
    with pytest.raises(RuntimeError, match="post-chart failure"):
        run_eda(config)
    assert not config.output_dir.exists()
    assert not config.chart_dir.exists()
    assert list(tmp_path.glob(".*.tmp")) == []


def test_second_publication_failure_rolls_back_without_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = prepare(tmp_path, sample_rows())
    real_publish = __import__(
        "scripts.cfpb_eda", fromlist=["_publish_directory"]
    )._publish_directory
    calls = 0

    def fail_second(source: Path, destination: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("synthetic second publication failure")
        real_publish(source, destination)

    monkeypatch.setattr("scripts.cfpb_eda._publish_directory", fail_second)
    with pytest.raises(OSError, match="second publication failure"):
        run_eda(config)
    assert calls == 2
    assert not config.output_dir.exists()
    assert not config.chart_dir.exists()
    assert list(tmp_path.glob(".*.tmp")) == []


def test_rollback_failure_is_surfaced_without_authoritative_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = prepare(tmp_path, sample_rows())

    def fail_after_first() -> None:
        raise RuntimeError("synthetic publication failure")

    real_remove = __import__(
        "scripts.cfpb_eda", fromlist=["_remove_directory"]
    )._remove_directory

    def fail_chart_rollback(path: Path) -> None:
        if path == config.chart_dir:
            raise OSError("synthetic rollback failure")
        real_remove(path)

    monkeypatch.setattr("scripts.cfpb_eda._after_first_publication", fail_after_first)
    monkeypatch.setattr("scripts.cfpb_eda._remove_directory", fail_chart_rollback)
    with pytest.raises(EDAError, match="rollback or cleanup failed"):
        run_eda(config)
    assert not (config.output_dir / "eda_metadata.json").exists()
    assert config.chart_dir.is_dir()


def test_completion_metadata_is_published_after_charts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = prepare(tmp_path, sample_rows())
    real_publish = __import__(
        "scripts.cfpb_eda", fromlist=["_publish_directory"]
    )._publish_directory
    observations: list[tuple[Path, bool, bool]] = []

    def observe_publish(source: Path, destination: Path) -> None:
        observations.append(
            (
                destination,
                config.chart_dir.exists(),
                (config.output_dir / "eda_metadata.json").exists(),
            )
        )
        real_publish(source, destination)

    monkeypatch.setattr("scripts.cfpb_eda._publish_directory", observe_publish)
    run_eda(config)
    assert observations == [
        (config.chart_dir, False, False),
        (config.output_dir, True, False),
    ]
    metadata = json.loads(
        (config.output_dir / "eda_metadata.json").read_text(encoding="utf-8")
    )
    assert metadata["status"] == "completed"
    assert config.chart_dir.is_dir()
