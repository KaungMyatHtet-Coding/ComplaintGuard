"""Create privacy-safe aggregate metadata for the raw CFPB complaint archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

SAFE_DISTRIBUTIONS = (
    "Product",
    "Issue",
    "Submitted via",
    "Company response to consumer",
    "Timely response?",
)
DATE_COLUMNS = ("Date received", "Date sent to company")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def profile(archive: Path, csv_path: Path, chunk_size: int) -> dict[str, object]:
    with zipfile.ZipFile(archive) as bundle:
        bad_member = bundle.testzip()
        members = bundle.infolist()
    if bad_member is not None:
        raise ValueError(f"Archive failed CRC validation at {bad_member!r}")
    if len(members) != 1 or members[0].filename != csv_path.name:
        raise ValueError("Expected one complaints.csv member")
    if csv_path.stat().st_size != members[0].file_size:
        raise ValueError("Extracted CSV size differs from ZIP member metadata")

    row_count = 0
    columns: list[str] = []
    missing: Counter[str] = Counter()
    distributions = {column: Counter() for column in SAFE_DISTRIBUTIONS}
    date_min: dict[str, pd.Timestamp | None] = {column: None for column in DATE_COLUMNS}
    date_max: dict[str, pd.Timestamp | None] = {column: None for column in DATE_COLUMNS}
    complaint_id_min: int | None = None
    complaint_id_max: int | None = None
    chunks = 0

    reader = pd.read_csv(
        csv_path,
        chunksize=chunk_size,
        dtype="string",
        keep_default_na=True,
        low_memory=False,
    )
    for chunk in reader:
        chunks += 1
        if not columns:
            columns = chunk.columns.tolist()
        row_count += len(chunk)
        missing.update(chunk.isna().sum().astype(int).to_dict())
        for column in SAFE_DISTRIBUTIONS:
            distributions[column].update(
                chunk[column].dropna().value_counts().to_dict()
            )
        for column in DATE_COLUMNS:
            values = pd.to_datetime(
                chunk[column], format="mixed", errors="coerce", utc=True
            )
            current_min, current_max = values.min(), values.max()
            if pd.notna(current_min):
                date_min[column] = (
                    current_min
                    if date_min[column] is None
                    else min(date_min[column], current_min)
                )
                date_max[column] = (
                    current_max
                    if date_max[column] is None
                    else max(date_max[column], current_max)
                )
        ids = (
            pd.to_numeric(chunk["Complaint ID"], errors="coerce")
            .dropna()
            .astype("int64")
        )
        if not ids.empty:
            complaint_id_min = (
                int(ids.min())
                if complaint_id_min is None
                else min(complaint_id_min, int(ids.min()))
            )
            complaint_id_max = (
                int(ids.max())
                if complaint_id_max is None
                else max(complaint_id_max, int(ids.max()))
            )

    def top_counts(counter: Counter[str], limit: int = 20) -> list[dict[str, object]]:
        return [
            {"value": value, "count": int(count)}
            for value, count in counter.most_common(limit)
        ]

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": "scripts/profile_cfpb.py",
        "python_version": platform.python_version(),
        "pandas_version": pd.__version__,
        "archive": {
            "path": archive.as_posix(),
            "size_bytes": archive.stat().st_size,
            "sha256": sha256(archive),
            "zip_testzip_result": bad_member,
            "member": members[0].filename,
            "member_compressed_bytes": members[0].compress_size,
            "member_uncompressed_bytes": members[0].file_size,
            "member_crc32": f"{members[0].CRC:08x}",
        },
        "csv": {
            "path": csv_path.as_posix(),
            "size_bytes": csv_path.stat().st_size,
            "row_count": row_count,
            "column_count": len(columns),
            "columns": columns,
            "chunk_size": chunk_size,
            "chunks_processed": chunks,
            "parser_dtype": "pandas StringDtype for lossless profiling",
            "logical_types": {
                column: (
                    "date"
                    if column in DATE_COLUMNS
                    else "integer identifier"
                    if column == "Complaint ID"
                    else "text"
                    if column
                    in ("Consumer complaint narrative", "Company public response")
                    else "string identifier"
                    if column == "ZIP code"
                    else "string/categorical"
                )
                for column in columns
            },
            "missing": {
                column: {
                    "count": int(missing[column]),
                    "percent": round(100 * missing[column] / row_count, 4),
                }
                for column in columns
            },
            "date_range": {
                column: {
                    "min": date_min[column].date().isoformat()
                    if date_min[column] is not None
                    else None,
                    "max": date_max[column].date().isoformat()
                    if date_max[column] is not None
                    else None,
                }
                for column in DATE_COLUMNS
            },
            "complaint_id_range": {"min": complaint_id_min, "max": complaint_id_max},
            "safe_distributions": {
                column: {
                    "distinct_non_null": len(distributions[column]),
                    "top_20": top_counts(distributions[column]),
                }
                for column in SAFE_DISTRIBUTIONS
            },
        },
        "privacy": {
            "complaint_level_records_written": False,
            "narrative_values_written": False,
            "notes": "Only aggregate counts and non-narrative categorical labels are emitted.",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--archive", type=Path, default=Path("data/raw/cfpb/complaints.csv.zip")
    )
    parser.add_argument(
        "--csv", type=Path, default=Path("data/raw/cfpb/complaints.csv")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("data/cfpb_snapshot_profile.json")
    )
    parser.add_argument("--chunk-size", type=int, default=100_000)
    args = parser.parse_args()
    result = profile(args.archive, args.csv, args.chunk_size)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote aggregate profile to {args.output}")
    print(
        f"Rows: {result['csv']['row_count']:,}; chunks: {result['csv']['chunks_processed']}"
    )


if __name__ == "__main__":
    main()
