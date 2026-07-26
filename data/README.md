# Data Directory

## Raw CFPB snapshot

Download the free official Consumer Complaint Database archive from:

```text
https://files.consumerfinance.gov/ccdb/complaints.csv.zip
```

Place it at `data/raw/cfpb/complaints.csv.zip` and extract `complaints.csv` beside it. `data/raw/` and archive/CSV formats are ignored by Git. Never force-add the raw archive, extracted CSV, complaint narratives, or complaint-level records.

The Day 3 snapshot downloaded on 20 July 2026 has archive SHA-256:

```text
2bdb13b1e412c6b659a94f74874d03ef6f610543b0d8e6538c7e30d1dd3d8eea
```

Validate and profile it from the repository root:

```powershell
python scripts/profile_cfpb.py
```

The profiler requires the dependency declared in `requirements-data.txt`; the verified Day 3 run used the already-installed pandas 2.2.3. The command verifies the ZIP CRC, checks the extracted size, and processes the CSV in 100,000-row chunks. It writes aggregate-only metadata to `data/cfpb_snapshot_profile.json`. See `docs/dataset_profile.md` and `docs/data_dictionary.md` for the reviewed Day 3 results.

## Directory policy

- `raw/`: ignored immutable downloads and extracted working copies.
- `mapping/`: future reviewed deterministic mappings, created only on the scheduled day.
- `processed/`: future small, reproducible, privacy-reviewed artifacts only.
- `interim/`: ignored local generated datasets and processing state, including the full Day 5 cleaned CSV.

## Day 5 cleaning

The deterministic Day 5 cleaner reads only the seven approved columns and processes the CSV in configurable chunks. It uses pandas plus a temporary disk-backed SQLite index for global Complaint ID deduplication. It does not map departments, translate or sample narratives, engineer features, split data, or train a model.

Bounded one-chunk smoke test from the repository root:

```powershell
python scripts/clean_cfpb.py `
  --input data/raw/cfpb/complaints.csv `
  --output data/interim/cfpb/complaints_cleaned_smoke.csv `
  --report data/cfpb_cleaning_report.json `
  --chunk-size 100000 `
  --max-chunks 1
```

Preserved diagnostic full run (immutable validation evidence; do not rerun or overwrite):

```powershell
python scripts/clean_cfpb.py `
  --input data/raw/cfpb/complaints.csv `
  --output data/interim/cfpb/complaints_cleaned.csv `
  --report data/cfpb_cleaning_full_report.json `
  --chunk-size 100000
```

The diagnostic pair uses `data/interim/cfpb/complaints_cleaned.csv` and `data/cfpb_cleaning_full_report.json`. It exposed a snapshot-wide date-format incompatibility and is preserved unchanged as immutable historical validation evidence. The cleaner refuses to overwrite either destination by default; `--overwrite` is reserved for an explicitly reviewed replacement of an existing matching pair. It writes run-specific temporary files, calculates the completed CSV's streaming SHA-256 and size, publishes the CSV, and publishes its completed report last. The two final renames are not transactionally atomic: the report is the completion marker, and a CSV is valid only when the report metadata validates its run ID, filename, hash, size, schema, and retained-row count.

Both final destinations are protected by stable, exclusively created locks acquired in deterministic path order. During overwrite, an existing pair must validate before either artifact moves; the old report is backed up first and the old CSV second. A report that names a different CSV is a foreign completion marker and causes a recovery-required refusal without being moved or deleted. A handled failure removes only the current run's published artifacts and restores the old CSV first and old report last. Production validation must confirm the restored pair against its recorded metadata. Current-run backups are deleted only after the replacement pair validates; cleanup failure leaves the new valid pair and remaining recovery evidence intact. Existing recovery backups or either publication lock cause a safe failure rather than automatic deletion. A conflicting duplicate Complaint ID aborts without publishing a new pair or row-level diagnostic.

`data/interim/cfpb/complaints_cleaned_smoke.csv` and `data/cfpb_cleaning_report.json` are preserved immutable smoke validation evidence. The smoke report must not be reused as the completion marker for another CSV. Do not move, delete, rename, archive, or overwrite either smoke-pair artifact.

The diagnostic, corrected, and smoke cleaned CSVs, SQLite state, and temporary files remain ignored and local. Only their aggregate reports are eligible generated Day 5 artifacts; every report must contain aggregate information only. The cleaned narratives are PII-reduced, not anonymized, and must never be committed or imported into Firestore.

The corrected two-format full run completed successfully with these destinations:

```powershell
python scripts/clean_cfpb.py `
  --input data/raw/cfpb/complaints.csv `
  --output data/interim/cfpb/complaints_cleaned_corrected.csv `
  --report data/cfpb_cleaning_corrected_report.json `
  --chunk-size 100000
```

The corrected run must not reuse or replace either the diagnostic full pair or the preserved smoke pair.

The final corrected pair has run ID `e1996a2c34d0457fa08b83864b4f1a9d` and `report_schema_version` 2. It processed 17,034,951 input rows in 171 chunks, retained 3,822,576 rows, rejected 13,212,375 rows, and passed production completed-pair validation. The corrected CSV SHA-256 is `41d2337fa2f2f4840eeb3475229a8347b67c3e4a14949846363e14ea13eee023`; the corrected report SHA-256 is `e923cc07cc72674990a2d40d456ad8814efb985a3fa22c7478e39d35fd88c88e`.

Raw and interim CSV files remain ignored and untracked. In particular, the approximately 4.5 GB corrected CSV must not be committed; only the aggregate-only corrected JSON report is eligible for tracking.
