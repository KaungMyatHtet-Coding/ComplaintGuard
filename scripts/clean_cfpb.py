"""Command-line entry point for the ComplaintGuard Day 5 cleaner."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import pandas as pd
from cfpb_cleaning import CleaningConfig, CleaningError, clean_cfpb


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Clean the CFPB complaints CSV in bounded chunks without logging row data."
    )
    parser.add_argument("--input", type=Path, required=True, help="Source CFPB CSV")
    parser.add_argument(
        "--output", type=Path, required=True, help="Ignored cleaned CSV destination"
    )
    parser.add_argument(
        "--report", type=Path, required=True, help="Aggregate-only JSON report"
    )
    parser.add_argument("--chunk-size", type=int, default=100_000)
    bounds = parser.add_mutually_exclusive_group()
    bounds.add_argument("--max-rows", type=int)
    bounds.add_argument("--max-chunks", type=int)
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace destinations with report-last validation and recovery backups",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = CleaningConfig(
        input_path=args.input,
        output_path=args.output,
        report_path=args.report,
        chunk_size=args.chunk_size,
        max_rows=args.max_rows,
        max_chunks=args.max_chunks,
        overwrite=args.overwrite,
    )
    try:
        report = clean_cfpb(config)
    except (CleaningError, FileExistsError, FileNotFoundError, ValueError) as error:
        print(f"Cleaning failed: {error}")
        return 1
    except (OSError, sqlite3.Error, UnicodeError, pd.errors.ParserError):
        print(
            "Cleaning failed: unexpected processing error; no row-level details were emitted"
        )
        return 1
    counts = report["counts"]
    print(
        "Cleaning completed: "
        f"input={counts['input_rows']:,}, retained={counts['retained_rows']:,}, "
        f"rejected={counts['rejected_rows']:,}, chunks={counts['chunks_processed']:,}"
    )
    print(f"Wrote cleaned CSV to {config.output_path}")
    print(f"Wrote aggregate report to {config.report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
