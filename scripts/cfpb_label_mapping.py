"""Deterministic CFPB Product/Issue mapping and chunked training dataset v1 builder."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import unicodedata
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

import pandas as pd

ALLOWED_DEPARTMENTS: Final[tuple[str, ...]] = (
    "transfer_payment",
    "account_support",
    "card_atm",
    "fraud_security",
    "loan_credit",
    "general_support",
)
CLEANED_COLUMNS: Final[tuple[str, ...]] = (
    "Complaint ID",
    "Date received",
    "Consumer complaint narrative",
    "Product",
    "Issue",
    "Sub-product",
    "Sub-issue",
)
INPUT_COLUMNS: Final[tuple[str, ...]] = (
    "Consumer complaint narrative",
    "Product",
    "Issue",
)
OUTPUT_COLUMNS: Final[tuple[str, ...]] = (
    "Consumer complaint narrative",
    "department_label",
)
EXPECTED_ROWS: Final[int] = 3_822_576
EXPECTED_CLEANING_RUN_ID: Final[str] = "e1996a2c34d0457fa08b83864b4f1a9d"
DATASET_VERSION: Final[str] = "v1"
MAPPING_VERSION: Final[str] = "v1"
METHODS: Final[tuple[str, ...]] = (
    "exact_product_issue",
    "product_fallback",
    "general_support",
)


class MappingError(RuntimeError):
    """Raised when mapping or dataset publication cannot complete safely."""


@dataclass(frozen=True)
class MappingPolicy:
    mapping_version: str
    exact_rules: dict[tuple[str, str], str]
    product_fallbacks: dict[str, str]
    intentionally_unresolved_products: frozenset[str]


@dataclass(frozen=True)
class BuildConfig:
    input_path: Path
    cleaning_report_path: Path
    mapping_path: Path
    output_path: Path
    manifest_path: Path
    chunk_size: int = 100_000
    expected_rows: int = EXPECTED_ROWS
    expected_cleaning_run_id: str = EXPECTED_CLEANING_RUN_ID
    dataset_version: str = DATASET_VERSION
    mapping_version: str = MAPPING_VERSION

    def validate(self) -> None:
        if self.chunk_size <= 0:
            raise ValueError("chunk_size must be greater than zero")
        if self.expected_rows < 0:
            raise ValueError("expected_rows cannot be negative")
        if self.output_path.resolve() == self.manifest_path.resolve():
            raise ValueError("output and manifest paths must differ")
        if self.output_path.exists() or self.manifest_path.exists():
            raise FileExistsError("Refusing to overwrite existing Day 7 output")


@dataclass
class BuildCounters:
    rows: int
    chunks: int
    label_counts: Counter[str]
    method_counts: Counter[str]
    missing_product: int
    missing_issue: int
    unknown_products: Counter[str]
    unresolved_known_products: Counter[str]


def normalize_category(value: object) -> str | None:
    """Normalize taxonomy values without fuzzy or substring matching."""
    if value is None or value is pd.NA or pd.isna(value):
        return None
    normalized = unicodedata.normalize("NFKC", str(value))
    normalized = re.sub(r"\s+", " ", normalized.strip())
    return normalized.casefold() or None


def _validate_department(value: object) -> str:
    if not isinstance(value, str) or value not in ALLOWED_DEPARTMENTS:
        raise MappingError("Mapping policy contains an unsupported department ID")
    return value


def load_mapping_policy(
    path: Path, expected_version: str = MAPPING_VERSION
) -> MappingPolicy:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise MappingError("Mapping policy is missing or invalid JSON") from error
    if (
        not isinstance(raw, dict)
        or raw.get("mapping_schema_version") != 1
        or raw.get("mapping_version") != expected_version
    ):
        raise MappingError("Mapping policy version is not approved")
    departments = raw.get("departments")
    if not isinstance(departments, dict) or set(departments) != set(
        ALLOWED_DEPARTMENTS
    ):
        raise MappingError("Mapping policy must define exactly six departments")

    exact_rules: dict[tuple[str, str], str] = {}
    for rule in raw.get("exact_product_issue_rules", []):
        if not isinstance(rule, dict):
            raise MappingError("Exact mapping rule is invalid")
        product = normalize_category(rule.get("product"))
        issue = normalize_category(rule.get("issue"))
        if product is None or issue is None:
            raise MappingError("Exact mapping rule has an empty Product or Issue")
        key = (product, issue)
        if key in exact_rules:
            raise MappingError("Mapping policy contains a duplicate exact rule")
        exact_rules[key] = _validate_department(rule.get("department_id"))

    product_fallbacks: dict[str, str] = {}
    for rule in raw.get("product_fallbacks", []):
        if not isinstance(rule, dict):
            raise MappingError("Product fallback rule is invalid")
        product = normalize_category(rule.get("product"))
        if product is None:
            raise MappingError("Product fallback has an empty Product")
        if product in product_fallbacks:
            raise MappingError("Mapping policy contains a duplicate Product fallback")
        product_fallbacks[product] = _validate_department(rule.get("department_id"))
    intentionally_unresolved: set[str] = set()
    for product_value in raw.get("intentionally_unresolved_products", []):
        product = normalize_category(product_value)
        if product is None:
            raise MappingError("Intentionally unresolved Product is empty")
        if product in intentionally_unresolved:
            raise MappingError("Mapping policy repeats an unresolved Product")
        if product in product_fallbacks:
            raise MappingError(
                "Resolved Product cannot also be intentionally unresolved"
            )
        intentionally_unresolved.add(product)
    return MappingPolicy(
        expected_version,
        exact_rules,
        product_fallbacks,
        frozenset(intentionally_unresolved),
    )


def map_department(
    product: object,
    issue: object,
    policy: MappingPolicy,
) -> tuple[str, str]:
    """Map using Product/Issue only; narrative text is never accepted."""
    normalized_product = normalize_category(product)
    normalized_issue = normalize_category(issue)
    if normalized_product is not None and normalized_issue is not None:
        exact = policy.exact_rules.get((normalized_product, normalized_issue))
        if exact is not None:
            return exact, "exact_product_issue"
    if normalized_product is not None:
        fallback = policy.product_fallbacks.get(normalized_product)
        if fallback is not None:
            return fallback, "product_fallback"
    return "general_support", "general_support"


def _strict_cleaning_report(
    path: Path, expected_run_id: str, expected_rows: int
) -> None:
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise MappingError("Corrected cleaning report is missing or invalid") from error
    if (
        not isinstance(report, dict)
        or report.get("report_schema_version") != 2
        or report.get("status") != "completed"
        or report.get("run_id") != expected_run_id
        or report.get("counts", {}).get("retained_rows") != expected_rows
    ):
        raise MappingError(
            "Corrected cleaning report does not match the approved input"
        )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _percentage(count: int, total: int) -> float:
    return round(count * 100 / total, 6) if total else 0.0


def _remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def _cleanup(paths: tuple[Path, ...], original_error: Exception) -> None:
    failures: list[str] = []
    for path in paths:
        try:
            _remove_path(path)
        except OSError as cleanup_error:
            failures.append(f"{path.name}: {cleanup_error}")
    if failures:
        raise MappingError(
            f"Day 7 cleanup failed: {'; '.join(failures)}"
        ) from original_error


def _validate_output_header(path: Path) -> None:
    with path.open("r", encoding="utf-8", newline="") as source:
        header = next(csv.reader(source), None)
    if header != list(OUTPUT_COLUMNS):
        raise MappingError("Training output schema validation failed")


def build_training_dataset(config: BuildConfig) -> dict[str, object]:
    """Build and atomically publish narrative/label v1 plus aggregate metadata."""
    config.validate()
    if not config.input_path.is_file():
        raise FileNotFoundError(f"Cleaned input not found: {config.input_path.name}")
    _strict_cleaning_report(
        config.cleaning_report_path,
        config.expected_cleaning_run_id,
        config.expected_rows,
    )
    policy = load_mapping_policy(config.mapping_path, config.mapping_version)
    header = pd.read_csv(config.input_path, nrows=0).columns.tolist()
    if header != list(CLEANED_COLUMNS):
        raise MappingError(
            "Cleaned input schema does not match the approved seven columns"
        )

    token = uuid.uuid4().hex
    output_temp = config.output_path.with_name(
        f".{config.output_path.name}.{token}.tmp"
    )
    manifest_temp = config.manifest_path.with_name(
        f".{config.manifest_path.name}.{token}.tmp"
    )
    output_published = False
    rows = 0
    chunks = 0
    label_counts: Counter[str] = Counter()
    method_counts: Counter[str] = Counter()
    missing_product = 0
    missing_issue = 0
    unknown_products: Counter[str] = Counter()
    unresolved_known_products: Counter[str] = Counter()

    config.output_path.parent.mkdir(parents=True, exist_ok=True)
    config.manifest_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        reader = pd.read_csv(
            config.input_path,
            usecols=list(INPUT_COLUMNS),
            dtype="string",
            chunksize=config.chunk_size,
            keep_default_na=True,
            low_memory=False,
            on_bad_lines="error",
        )
        first = True
        for chunk in reader:
            if chunk.empty:
                continue
            chunks += 1
            rows += len(chunk)
            narratives = chunk["Consumer complaint narrative"]
            if narratives.isna().any():
                raise MappingError("Cleaned input contains a missing narrative")
            products = chunk["Product"]
            issues = chunk["Issue"]
            missing_product += int(products.isna().sum())
            missing_issue += int(issues.isna().sum())

            labels: list[str] = []
            methods: list[str] = []
            for product, issue in zip(products, issues, strict=True):
                label, method = map_department(product, issue, policy)
                labels.append(label)
                methods.append(method)
                normalized_product = normalize_category(product)
                if method == "general_support" and normalized_product is not None:
                    display_product = str(product)
                    if normalized_product in policy.intentionally_unresolved_products:
                        unresolved_known_products[display_product] += 1
                    else:
                        unknown_products[display_product] += 1
            if any(label not in ALLOWED_DEPARTMENTS for label in labels):
                raise MappingError("Mapping produced an unsupported department ID")
            label_counts.update(labels)
            method_counts.update(methods)
            output = pd.DataFrame(
                {
                    OUTPUT_COLUMNS[0]: narratives,
                    OUTPUT_COLUMNS[1]: labels,
                }
            )
            output.to_csv(
                output_temp,
                mode="w" if first else "a",
                header=first,
                index=False,
                encoding="utf-8",
                lineterminator="\n",
            )
            first = False

        if rows != config.expected_rows:
            raise MappingError(
                f"Row reconciliation failed: expected {config.expected_rows}, got {rows}"
            )
        if sum(label_counts.values()) != rows or sum(method_counts.values()) != rows:
            raise MappingError("Label or mapping-method reconciliation failed")
        if set(label_counts) - set(ALLOWED_DEPARTMENTS):
            raise MappingError("Label distribution contains an unsupported department")
        _validate_output_header(output_temp)
        output_size = output_temp.stat().st_size
        output_sha256 = _file_sha256(output_temp)
        created_at = datetime.now(timezone.utc).isoformat()
        manifest: dict[str, object] = {
            "manifest_schema_version": 1,
            "status": "completed",
            "dataset_version": config.dataset_version,
            "mapping_version": policy.mapping_version,
            "created_at_utc": created_at,
            "source": {
                "cleaning_run_id": config.expected_cleaning_run_id,
                "cleaned_file_name": config.input_path.name,
                "mapping_file_name": config.mapping_path.name,
            },
            "output": {
                "file_name": config.output_path.name,
                "schema": list(OUTPUT_COLUMNS),
                "rows": rows,
                "size_bytes": output_size,
                "sha256": output_sha256,
            },
            "processing": {
                "input_rows": rows,
                "output_rows": rows,
                "dropped_rows": 0,
                "chunks_processed": chunks,
                "chunk_size": config.chunk_size,
                "row_reconciliation_valid": True,
            },
            "label_counts": {
                label: int(label_counts.get(label, 0)) for label in ALLOWED_DEPARTMENTS
            },
            "label_percentages": {
                label: _percentage(label_counts.get(label, 0), rows)
                for label in ALLOWED_DEPARTMENTS
            },
            "mapping_method_counts": {
                method: int(method_counts.get(method, 0)) for method in METHODS
            },
            "mapping_method_percentages": {
                method: _percentage(method_counts.get(method, 0), rows)
                for method in METHODS
            },
            "missing_values": {
                "Product": missing_product,
                "Issue": missing_issue,
                "Consumer complaint narrative": 0,
            },
            "fallback_audit": {
                "unknown_products": dict(sorted(unknown_products.items())),
                "intentionally_unresolved_products": dict(
                    sorted(unresolved_known_products.items())
                ),
            },
            "labeling_integrity": {
                "label_source_fields": ["Product", "Issue"],
                "narrative_used_for_labeling": False,
                "one_label_per_row": True,
                "allowed_label_set_valid": True,
            },
            "reproducibility_command": (
                "python scripts/cfpb_label_mapping.py "
                "--input data/interim/cfpb/complaints_cleaned_corrected.csv "
                "--cleaning-report data/cfpb_cleaning_corrected_report.json "
                "--mapping data/mapping/cfpb_department_mapping_v1.json "
                "--output data/interim/cfpb/cfpb_training_v1.csv "
                "--manifest data/processed/cfpb_training_v1_manifest.json "
                "--chunk-size 100000"
            ),
            "privacy": {
                "aggregate_only_manifest": True,
                "contains_narratives": False,
                "contains_complaint_ids": False,
            },
        }
        manifest_temp.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        os.replace(output_temp, config.output_path)
        output_published = True
        os.replace(manifest_temp, config.manifest_path)
        return manifest
    except Exception as error:
        cleanup_paths = [output_temp, manifest_temp]
        if output_published:
            cleanup_paths.append(config.output_path)
        _cleanup(tuple(cleanup_paths), error)
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build deterministic CFPB department-labeled dataset v1"
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--cleaning-report", type=Path, required=True)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--chunk-size", type=int, default=100_000)
    parser.add_argument("--expected-rows", type=int, default=EXPECTED_ROWS)
    parser.add_argument("--expected-cleaning-run-id", default=EXPECTED_CLEANING_RUN_ID)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = BuildConfig(
        input_path=args.input,
        cleaning_report_path=args.cleaning_report,
        mapping_path=args.mapping,
        output_path=args.output,
        manifest_path=args.manifest,
        chunk_size=args.chunk_size,
        expected_rows=args.expected_rows,
        expected_cleaning_run_id=args.expected_cleaning_run_id,
    )
    try:
        manifest = build_training_dataset(config)
    except (MappingError, FileExistsError, FileNotFoundError, ValueError) as error:
        print(f"Day 7 dataset build failed: {error}")
        return 1
    except (OSError, RuntimeError, TypeError):
        print("Day 7 dataset build failed: unexpected processing error")
        return 1
    processing = manifest["processing"]
    print(
        "Day 7 dataset completed: "
        f"rows={processing['output_rows']:,}, "
        f"chunks={processing['chunks_processed']:,}, "
        f"version={manifest['dataset_version']}"
    )
    print(f"Wrote training dataset to {config.output_path}")
    print(f"Wrote aggregate manifest to {config.manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
