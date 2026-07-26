"""Memory-safe aggregate EDA for the corrected CFPB complaint corpus."""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import textwrap
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Final

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd

matplotlib.use("Agg", force=True)


CLEANED_COLUMNS: Final[tuple[str, ...]] = (
    "Complaint ID",
    "Date received",
    "Consumer complaint narrative",
    "Product",
    "Issue",
    "Sub-product",
    "Sub-issue",
)
EDA_COLUMNS: Final[tuple[str, ...]] = (
    "Date received",
    "Consumer complaint narrative",
    "Product",
    "Issue",
)
EXPECTED_RETAINED_ROWS: Final[int] = 3_822_576
EXPECTED_CLEANING_RUN_ID: Final[str] = "e1996a2c34d0457fa08b83864b4f1a9d"
SNAPSHOT_MIN: Final[str] = "2011-12-01"
SNAPSHOT_MAX: Final[str] = "2026-07-20"
NARRATIVE_BUCKETS: Final[tuple[tuple[str, int, int | None], ...]] = (
    ("0-249", 0, 249),
    ("250-499", 250, 499),
    ("500-999", 500, 999),
    ("1000-1999", 1000, 1999),
    ("2000+", 2000, None),
)


class EDAError(RuntimeError):
    """Raised when aggregate EDA cannot be completed safely."""


@dataclass(frozen=True)
class EDAConfig:
    input_path: Path
    cleaning_report_path: Path
    output_dir: Path
    chart_dir: Path
    chunk_size: int = 100_000
    expected_rows: int = EXPECTED_RETAINED_ROWS
    expected_run_id: str = EXPECTED_CLEANING_RUN_ID

    def validate(self) -> None:
        if self.chunk_size <= 0:
            raise ValueError("chunk_size must be greater than zero")
        if self.expected_rows < 0:
            raise ValueError("expected_rows cannot be negative")
        if self.output_dir.resolve() == self.chart_dir.resolve():
            raise ValueError("aggregate and chart directories must differ")
        if self.output_dir.exists() or self.chart_dir.exists():
            raise FileExistsError("Refusing to overwrite existing EDA output")


@dataclass
class Aggregates:
    rows: int
    chunks: int
    minimum_date: str | None
    maximum_date: str | None
    years: Counter[str]
    months: Counter[str]
    products: Counter[str]
    issues: Counter[str]
    product_issue_pairs: Counter[tuple[str, str]]
    narrative_lengths: Counter[int]
    narrative_characters: int


def _strict_cleaning_report(path: Path, expected_run_id: str) -> dict[str, object]:
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EDAError("Corrected cleaning report is missing or invalid") from error
    if (
        not isinstance(report, dict)
        or report.get("report_schema_version") != 2
        or report.get("status") != "completed"
        or report.get("run_id") != expected_run_id
    ):
        raise EDAError("Corrected cleaning report does not match the approved run")
    return report


def aggregate_csv(config: EDAConfig) -> Aggregates:
    """Read the cleaned CSV once and retain aggregate counters only."""
    config.validate()
    if not config.input_path.is_file():
        raise FileNotFoundError(f"EDA input not found: {config.input_path.name}")
    report = _strict_cleaning_report(
        config.cleaning_report_path, config.expected_run_id
    )
    recorded_rows = report.get("counts", {}).get("retained_rows")  # type: ignore[union-attr]
    if recorded_rows != config.expected_rows:
        raise EDAError("Expected row count does not match the cleaning report")
    header = pd.read_csv(config.input_path, nrows=0).columns.tolist()
    if header != list(CLEANED_COLUMNS):
        raise EDAError("Cleaned input schema does not match the approved seven columns")

    rows = 0
    chunks = 0
    minimum_date: str | None = None
    maximum_date: str | None = None
    years: Counter[str] = Counter()
    months: Counter[str] = Counter()
    products: Counter[str] = Counter()
    issues: Counter[str] = Counter()
    pairs: Counter[tuple[str, str]] = Counter()
    lengths: Counter[int] = Counter()
    characters = 0

    reader = pd.read_csv(
        config.input_path,
        usecols=list(EDA_COLUMNS),
        dtype="string",
        chunksize=config.chunk_size,
        keep_default_na=True,
        low_memory=False,
        on_bad_lines="error",
    )
    for chunk in reader:
        if chunk.empty:
            continue
        chunks += 1
        rows += len(chunk)
        dates = chunk["Date received"]
        if dates.isna().any() or not dates.str.fullmatch(r"\d{4}-\d{2}-\d{2}").all():
            raise EDAError("Cleaned input contains a missing or noncanonical date")
        parsed_dates = pd.to_datetime(dates, format="%Y-%m-%d", errors="coerce")
        if parsed_dates.isna().any():
            raise EDAError("Cleaned input contains an impossible calendar date")
        canonical_dates = parsed_dates.dt.strftime("%Y-%m-%d")
        chunk_min = str(canonical_dates.min())
        chunk_max = str(canonical_dates.max())
        if chunk_min < SNAPSHOT_MIN or chunk_max > SNAPSHOT_MAX:
            raise EDAError("Cleaned input date falls outside approved snapshot bounds")
        minimum_date = (
            chunk_min
            if minimum_date is None or chunk_min < minimum_date
            else minimum_date
        )
        maximum_date = (
            chunk_max
            if maximum_date is None or chunk_max > maximum_date
            else maximum_date
        )
        years.update(canonical_dates.str.slice(0, 4).value_counts().to_dict())
        months.update(canonical_dates.str.slice(0, 7).value_counts().to_dict())

        product = chunk["Product"]
        issue = chunk["Issue"]
        narrative = chunk["Consumer complaint narrative"]
        if product.isna().any() or issue.isna().any() or narrative.isna().any():
            raise EDAError("Cleaned input contains a missing required EDA value")
        products.update(product.value_counts().to_dict())
        issues.update(issue.value_counts().to_dict())
        pairs.update(zip(product.astype(str), issue.astype(str), strict=True))
        chunk_lengths = narrative.str.len()
        lengths.update(chunk_lengths.value_counts().to_dict())
        characters += int(chunk_lengths.sum())

    if rows != config.expected_rows:
        raise EDAError(
            f"Processed-row reconciliation failed: expected {config.expected_rows}, got {rows}"
        )
    for name, counter in (
        ("year", years),
        ("month", months),
        ("product", products),
        ("issue", issues),
        ("product/issue", pairs),
        ("narrative length", lengths),
    ):
        if sum(counter.values()) != rows:
            raise EDAError(f"{name} aggregate reconciliation failed")
    return Aggregates(
        rows,
        chunks,
        minimum_date,
        maximum_date,
        years,
        months,
        products,
        issues,
        pairs,
        lengths,
        characters,
    )


def _ranked(counter: Counter[object], total: int) -> list[dict[str, object]]:
    ordered = sorted(counter.items(), key=lambda item: (-item[1], str(item[0])))
    return [
        {
            "rank": rank,
            "category": str(category),
            "count": int(count),
            "percentage": round(count * 100 / total, 6) if total else 0.0,
        }
        for rank, (category, count) in enumerate(ordered, start=1)
    ]


def _quantile(lengths: Counter[int], total: int, probability: float) -> int | None:
    """Return the lower nearest-rank value at floor((n - 1) * p) + 1."""
    if total == 0:
        return None
    target = max(1, int((total - 1) * probability) + 1)
    cumulative = 0
    for length, count in sorted(lengths.items()):
        cumulative += count
        if cumulative >= target:
            return int(length)
    raise EDAError("Narrative quantile reconciliation failed")


def build_tables(aggregates: Aggregates) -> dict[str, list[dict[str, object]]]:
    total = aggregates.rows
    year_rows = [
        {"year": key, "count": int(value), "percentage": round(value * 100 / total, 6)}
        for key, value in sorted(aggregates.years.items())
    ]
    month_rows = [
        {"month": key, "count": int(value), "percentage": round(value * 100 / total, 6)}
        for key, value in sorted(aggregates.months.items())
    ]
    bucket_rows: list[dict[str, object]] = []
    for label, lower, upper in NARRATIVE_BUCKETS:
        count = sum(
            value
            for length, value in aggregates.narrative_lengths.items()
            if length >= lower and (upper is None or length <= upper)
        )
        bucket_rows.append(
            {
                "bucket": label,
                "count": int(count),
                "percentage": round(count * 100 / total, 6) if total else 0.0,
            }
        )
    pair_counter = Counter(
        {
            f"{product} — {issue}": count
            for (product, issue), count in aggregates.product_issue_pairs.items()
        }
    )
    products = _ranked(aggregates.products, total)
    issues = _ranked(aggregates.issues, total)
    pairs = _ranked(pair_counter, total)
    concentration = [
        {
            "dimension": dimension,
            "top_1_percentage": rows[0]["percentage"] if rows else 0.0,
            "top_5_percentage": round(
                sum(float(row["percentage"]) for row in rows[:5]), 6
            ),
            "category_count": len(rows),
        }
        for dimension, rows in (("Product", products), ("Issue", issues))
    ]
    statistics = [
        {
            "count": total,
            "minimum": min(aggregates.narrative_lengths, default=None),
            "mean": round(aggregates.narrative_characters / total, 3)
            if total
            else None,
            "median": _quantile(aggregates.narrative_lengths, total, 0.5),
            "p90": _quantile(aggregates.narrative_lengths, total, 0.9),
            "p95": _quantile(aggregates.narrative_lengths, total, 0.95),
            "maximum": max(aggregates.narrative_lengths, default=None),
        }
    ]
    overview = [
        {
            "retained_complaints": total,
            "minimum_date": aggregates.minimum_date,
            "maximum_date": aggregates.maximum_date,
            "chunks_processed": aggregates.chunks,
        }
    ]
    return {
        "overview": overview,
        "complaints_by_year": year_rows,
        "complaints_by_month": month_rows,
        "products": products,
        "issues": issues,
        "narrative_length_buckets": bucket_rows,
        "narrative_length_statistics": statistics,
        "product_issue_pairs": pairs,
        "concentration": concentration,
    }


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        raise EDAError(f"Aggregate table is empty: {path.stem}")
    with path.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _save_chart(path: Path, title: str, source_note: str) -> None:
    plt.title(title)
    plt.figtext(0.01, 0.01, source_note, fontsize=7, color="#555555")
    plt.tight_layout(rect=(0, 0.04, 1, 1))
    plt.savefig(path, dpi=180, bbox_inches="tight")
    plt.close()


def _wrapped_categories(
    rows: list[dict[str, object]],
    width: int,
) -> list[str]:
    return [textwrap.fill(str(row["category"]), width=width) for row in rows]


def render_charts(
    tables: dict[str, list[dict[str, object]]], chart_dir: Path, run_id: str
) -> None:
    chart_dir.mkdir(parents=True, exist_ok=True)
    source = f"Source: CFPB corrected aggregate; cleaning run {run_id}"

    years = tables["complaints_by_year"]
    plt.figure(figsize=(10, 5))
    plt.bar(
        [str(row["year"]) for row in years],
        [int(row["count"]) for row in years],
        color="#2878B5",
    )
    plt.xlabel("Year")
    plt.ylabel("Retained complaints")
    plt.xticks(rotation=45)
    plt.ylim(bottom=0)
    maximum_date = str(tables["overview"][0]["maximum_date"])
    plt.text(
        0.99,
        0.96,
        f"2026 is partial through {maximum_date}",
        transform=plt.gca().transAxes,
        horizontalalignment="right",
        verticalalignment="top",
        fontsize=9,
        color="#444444",
    )
    _save_chart(
        chart_dir / "01_complaints_by_year.png",
        "Retained complaint volume by year",
        source,
    )

    months = tables["complaints_by_month"]
    plt.figure(figsize=(12, 5))
    plt.plot(
        [str(row["month"]) for row in months],
        [int(row["count"]) for row in months],
        color="#2878B5",
    )
    plt.xlabel("Month")
    plt.ylabel("Retained complaints")
    tick_step = max(1, len(months) // 12)
    plt.xticks(
        range(0, len(months), tick_step),
        [str(months[index]["month"]) for index in range(0, len(months), tick_step)],
        rotation=45,
    )
    plt.ylim(bottom=0)
    _save_chart(
        chart_dir / "02_monthly_complaint_trend.png",
        "Monthly retained complaint trend",
        source,
    )

    for filename, title, table_name, color in (
        ("03_top_products.png", "Top financial products", "products", "#3A923A"),
        ("04_top_issues.png", "Top complaint issues", "issues", "#E1812C"),
    ):
        rows = list(reversed(tables[table_name][:10]))
        plt.figure(figsize=(11, 6))
        plt.barh(
            _wrapped_categories(rows, 48),
            [float(row["percentage"]) for row in rows],
            color=color,
        )
        plt.xlabel("Share of retained complaints (%)")
        plt.xlim(left=0)
        _save_chart(chart_dir / filename, title, source)

    buckets = tables["narrative_length_buckets"]
    plt.figure(figsize=(9, 5))
    plt.bar(
        [str(row["bucket"]) for row in buckets],
        [float(row["percentage"]) for row in buckets],
        color="#6F4E7C",
    )
    plt.xlabel("Narrative length (characters)")
    plt.ylabel("Share of retained complaints (%)")
    plt.ylim(bottom=0)
    _save_chart(
        chart_dir / "05_narrative_length_distribution.png",
        "Narrative-length distribution",
        source,
    )

    pairs = list(reversed(tables["product_issue_pairs"][:12]))
    plt.figure(figsize=(14, 8))
    plt.barh(
        _wrapped_categories(pairs, 58),
        [float(row["percentage"]) for row in pairs],
        color="#C44E52",
    )
    plt.xlabel("Share of retained complaints (%)")
    plt.xlim(left=0)
    _save_chart(
        chart_dir / "06_top_product_issue_pairs.png",
        "Top Product–Issue joint categories",
        source,
    )


def build_findings(tables: dict[str, list[dict[str, object]]]) -> list[dict[str, str]]:
    years = tables["complaints_by_year"]
    months = tables["complaints_by_month"]
    products = tables["products"]
    issues = tables["issues"]
    buckets = tables["narrative_length_buckets"]
    pairs = tables["product_issue_pairs"]
    peak_year = max(years, key=lambda row: int(row["count"]))
    peak_month = max(months, key=lambda row: int(row["count"]))
    largest_bucket = max(buckets, key=lambda row: int(row["count"]))
    return [
        {
            "chart": "01_complaints_by_year.png",
            "finding": f"{peak_year['year']} has the highest retained annual volume ({peak_year['count']:,}).",
        },
        {
            "chart": "02_monthly_complaint_trend.png",
            "finding": f"{peak_month['month']} is the highest retained month ({peak_month['count']:,}); changes describe submissions, not population complaint rates.",
        },
        {
            "chart": "03_top_products.png",
            "finding": f"The leading product is {products[0]['category']} ({products[0]['percentage']:.2f}%), showing strong product imbalance.",
        },
        {
            "chart": "04_top_issues.png",
            "finding": f"The leading issue is {issues[0]['category']} ({issues[0]['percentage']:.2f}%), while many issue categories form a long tail.",
        },
        {
            "chart": "05_narrative_length_distribution.png",
            "finding": f"The largest narrative-length bucket is {largest_bucket['bucket']} characters ({largest_bucket['percentage']:.2f}%).",
        },
        {
            "chart": "06_top_product_issue_pairs.png",
            "finding": f"The leading Product–Issue pair is {pairs[0]['category']} ({pairs[0]['percentage']:.2f}%), showing strong concentration in the leading joint category.",
        },
    ]


def _validate_staged_packages(
    aggregate_dir: Path,
    chart_dir: Path,
    tables: dict[str, list[dict[str, object]]],
) -> None:
    expected_tables = {f"{name}.csv" for name in tables}
    actual_tables = {path.name for path in aggregate_dir.glob("*.csv")}
    if actual_tables != expected_tables:
        raise EDAError("Staged aggregate-table package is incomplete")
    metadata_path = aggregate_dir / "eda_metadata.json"
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EDAError("Staged completion metadata is missing or invalid") from error
    if metadata.get("status") != "completed":
        raise EDAError("Staged completion metadata is not completed")
    expected_charts = set(metadata.get("charts", []))
    actual_charts = {
        path.name for path in chart_dir.glob("*.png") if path.stat().st_size > 0
    }
    if actual_charts != expected_charts or len(actual_charts) != 6:
        raise EDAError("Staged chart package is incomplete")


def _publish_directory(source: Path, destination: Path) -> None:
    os.replace(source, destination)


def _after_first_publication() -> None:
    """Test hook at the safe point where charts exist but metadata is not public."""


def _remove_directory(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


def _rollback_publication(
    *,
    aggregate_temp: Path,
    chart_temp: Path,
    output_dir: Path,
    chart_dir: Path,
    aggregate_published: bool,
    chart_published: bool,
    original_error: Exception,
) -> None:
    cleanup_failures: list[str] = []
    paths = (
        (output_dir, aggregate_published),
        (chart_dir, chart_published),
        (aggregate_temp, True),
        (chart_temp, True),
    )
    for path, eligible in paths:
        if not eligible:
            continue
        try:
            _remove_directory(path)
        except OSError as cleanup_error:
            cleanup_failures.append(f"{path.name}: {cleanup_error}")
    if cleanup_failures:
        details = "; ".join(cleanup_failures)
        raise EDAError(f"EDA rollback or cleanup failed: {details}") from original_error


def run_eda(config: EDAConfig) -> dict[str, object]:
    """Publish charts first and authoritative completed metadata last."""
    timer = perf_counter()
    aggregates = aggregate_csv(config)
    tables = build_tables(aggregates)
    token = uuid.uuid4().hex
    aggregate_temp = config.output_dir.with_name(
        f".{config.output_dir.name}.{token}.tmp"
    )
    chart_temp = config.chart_dir.with_name(f".{config.chart_dir.name}.{token}.tmp")
    config.output_dir.parent.mkdir(parents=True, exist_ok=True)
    config.chart_dir.parent.mkdir(parents=True, exist_ok=True)
    aggregate_published = False
    chart_published = False
    try:
        aggregate_temp.mkdir()
        for name, rows in tables.items():
            _write_csv(aggregate_temp / f"{name}.csv", rows)
        render_charts(tables, chart_temp, config.expected_run_id)
        findings = build_findings(tables)
        metadata: dict[str, object] = {
            "eda_schema_version": 1,
            "status": "completed",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "source": {
                "cleaning_run_id": config.expected_run_id,
                "cleaned_file_name": config.input_path.name,
                "expected_rows": config.expected_rows,
            },
            "processing": {
                "rows_processed": aggregates.rows,
                "chunks_processed": aggregates.chunks,
                "chunk_size": config.chunk_size,
                "minimum_date": aggregates.minimum_date,
                "maximum_date": aggregates.maximum_date,
                "row_reconciliation_valid": True,
            },
            "tables": sorted(f"{name}.csv" for name in tables),
            "charts": sorted(path.name for path in chart_temp.glob("*.png")),
            "findings": findings,
            "privacy": {
                "aggregate_only": True,
                "contains_narratives": False,
                "contains_complaint_ids": False,
            },
            "elapsed_seconds": round(perf_counter() - timer, 3),
        }
        (aggregate_temp / "eda_metadata.json").write_text(
            json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
        )
        _validate_staged_packages(aggregate_temp, chart_temp, tables)
        _publish_directory(chart_temp, config.chart_dir)
        chart_published = True
        _after_first_publication()
        _publish_directory(aggregate_temp, config.output_dir)
        aggregate_published = True
        return metadata
    except Exception as error:
        _rollback_publication(
            aggregate_temp=aggregate_temp,
            chart_temp=chart_temp,
            output_dir=config.output_dir,
            chart_dir=config.chart_dir,
            aggregate_published=aggregate_published,
            chart_published=chart_published,
            original_error=error,
        )
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create aggregate-only CFPB EDA outputs"
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--cleaning-report", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--chart-dir", type=Path, required=True)
    parser.add_argument("--chunk-size", type=int, default=100_000)
    parser.add_argument("--expected-rows", type=int, default=EXPECTED_RETAINED_ROWS)
    parser.add_argument("--expected-run-id", default=EXPECTED_CLEANING_RUN_ID)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = EDAConfig(
        input_path=args.input,
        cleaning_report_path=args.cleaning_report,
        output_dir=args.output_dir,
        chart_dir=args.chart_dir,
        chunk_size=args.chunk_size,
        expected_rows=args.expected_rows,
        expected_run_id=args.expected_run_id,
    )
    try:
        metadata = run_eda(config)
    except (EDAError, FileExistsError, FileNotFoundError, ValueError) as error:
        print(f"EDA failed: {error}")
        return 1
    except (OSError, RuntimeError, TypeError):
        print("EDA failed: unexpected aggregate-processing error")
        return 1
    processing = metadata["processing"]
    print(
        "EDA completed: "
        f"rows={processing['rows_processed']:,}, "
        f"chunks={processing['chunks_processed']:,}, "
        f"charts={len(metadata['charts'])}"
    )
    print(f"Wrote aggregate tables to {config.output_dir}")
    print(f"Wrote charts to {config.chart_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
