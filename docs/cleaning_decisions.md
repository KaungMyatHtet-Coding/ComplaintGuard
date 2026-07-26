# Day 5 CFPB Cleaning Decisions

## Scope and boundaries

Day 5 produces a deterministic, local CSV cleaning pipeline for the immutable CFPB snapshot. The final successful full-dataset pair is `data/interim/cfpb/complaints_cleaned_corrected.csv` with `data/cfpb_cleaning_corrected_report.json`. The historical corpus, complaint-level outputs, real narratives, rejected rows, and processing state must not be committed or imported into Firestore.

Day 5 does not perform sampling, class balancing, translation, department mapping, feature engineering, tokenization, train/test splitting, EDA, or model training. `Complaint ID` is retained only for provenance and deduplication and must never become an ML feature.

## Cleaned schema

The output column order is fixed:

1. `Complaint ID`
2. `Date received`
3. `Consumer complaint narrative`
4. `Product`
5. `Issue`
6. `Sub-product`
7. `Sub-issue`

All other source fields are excluded to minimize privacy exposure and avoid unrelated or leakage-prone features.

## Required fields and mutually exclusive rejection order

Each input row is assigned at most one pre-deduplication rejection reason, using this precedence:

1. `invalid_complaint_id`: missing, non-decimal, zero, or negative Complaint ID.
2. `invalid_date_received`: not accepted by the explicit raw-date allowlist, impossible on the calendar, or outside the approved immutable-snapshot range.
3. `missing_product`: null, empty, or boundary-whitespace-only Product.
4. `missing_issue`: null, empty, or boundary-whitespace-only Issue.
5. `missing_or_unusable_narrative`: null, empty, whitespace-only, URL/masking/redaction-only, or without remaining alphanumeric content.
6. `duplicate_identical`: a later row whose Complaint ID and canonical cleaned content match the first occurrence.

Successful runs enforce:

```text
input rows = retained rows + sum of mutually exclusive rejection categories
```

`Sub-product` and `Sub-issue` are optional. Empty values become null. Product, Issue, Sub-product, and Sub-issue receive boundary trimming only; spelling, case, and internal whitespace are preserved.

## Narrative normalization and PII reduction

Narratives are normalized with Unicode NFKC, line breaks and repeated Unicode whitespace are collapsed to one ASCII space, and boundary whitespace is removed. The cleaner does not lowercase, stem, tokenize, remove stop words, or change punctuation generally.

Conservative patterns are applied in this order:

1. HTTP(S) and `www.` URLs are removed.
2. Obvious email addresses become `[REDACTED_EMAIL]`.
3. Digit sequences containing at least nine digits, with optional spaces or hyphens, become `[REDACTED_NUMBER]`.
4. Phone-like candidates using digits and common separators become `[REDACTED_PHONE]` only when the matched value contains at least seven actual digits.

The rules run in this fixed order, so a plain long digit/space/hyphen sequence may be classified as `long_number` before the phone rule is reached. Ordinary punctuation with fewer than seven digits is not a phone match. CFPB masking tokens such as `XXXX` are preserved. Redaction-category counts are aggregate counts of affected input narratives per category, including narratives whose rows may later be rejected; they are not counts of individual matches or retained rows.

The result is **PII-reduced, not anonymized**. Regex patterns cannot guarantee removal of every direct or indirect identifier, and the cleaned narrative corpus remains sensitive local data.

## Dates and duplicate IDs

The complete read-only audit found two and only two raw `Date received` representations: 2,176,818 values shaped as `YYYY-MM-DDTHH:MM:SS.mmmZ` and 14,858,133 values shaped as `YYYY-MM-DD`. The first 100,000-row smoke chunk contained only timestamps and was therefore not representative of the complete snapshot.

The production allowlist checks formats in deterministic order:

1. A full-match `YYYY-MM-DDTHH:MM:SS.mmmZ` with uppercase `T` and `Z`, exactly two digits for each clock component, and exactly three fractional digits, parsed strictly as `%Y-%m-%dT%H:%M:%S.%fZ`.
2. A full-match `YYYY-MM-DD`, parsed strictly as `%Y-%m-%d`.

Timestamp-shaped values receive explicit clock validation before pandas parsing: hour must be 0 through 23, minute 0 through 59, and second 0 through 59. Leap seconds and `24:00:00` are rejected as impossible clock/calendar values and cannot be normalized or retained.

No inferred, mixed, day-first, or fallback parsing is used. Dates are not trimmed: null, exact empty, whitespace-bearing, shape-invalid, impossible-calendar, and out-of-profile-range values are rejected as distinct diagnostic categories. Calendar dates must fall inclusively between the immutable snapshot bounds `2011-12-01` and `2026-07-20`. The timestamp's validated time and UTC marker are discarded, and both accepted inputs are emitted canonically as `YYYY-MM-DD`.

Date-format diagnostics classify every input row before row-rejection precedence is applied. The aggregate report records accepted timestamp, accepted plain-date, null, empty, whitespace-bearing, invalid-shape, impossible-calendar, out-of-range, total-accepted, and total-classified counts. These date diagnostics reconcile independently and are not row-rejection counts: an invalid Complaint ID remains the row's rejection reason even when its date is invalid.

Complaint IDs are canonical positive decimal strings matching `[1-9]\d*`.

A temporary SQLite database provides deduplication across all chunks without keeping millions of identifiers in memory. The canonical digest covers every cleaned output field except Complaint ID. An identical duplicate retains the first raw-file occurrence. If an ID has conflicting canonical content, the run aborts with aggregate-only wording that reveals no ID or row content.

## Publication, validation, and recovery

The cleaner validates configuration and required columns before creating processing state. It then derives stable publication-lock paths for both the final CSV and final report, deduplicates them, and acquires them by exclusive creation in deterministic sorted-path order. Every lock contains the unpredictable current run ID. Failure to acquire any lock releases only locks already acquired and still owned by that run; foreign locks are preserved. The cleaner writes the CSV, SQLite state, and aggregate JSON report to unique paths containing the run ID. Existing destinations are protected unless `--overwrite` is explicit.

After cleaning and reconciliation, the temporary CSV is streamed in bounded blocks to calculate its SHA-256 and byte size. The completed report records the run ID, `completed` status, final CSV filename, CSV SHA-256, CSV byte size, and retained-row count. The report also records the same retained count in its aggregate counts.

New reports use `report_schema_version` 2. Completed-pair validation requires the complete date-counter object, non-negative integer values that exclude booleans, exact accepted and classified totals, and equality between total classified dates and input rows. Unversioned or version-1 compatibility is limited to the exact immutable diagnostic and smoke pairs identified by their approved run ID, CSV SHA-256, report SHA-256, and retained-row count; no other unversioned report is accepted.

The CSV and report use separate final paths, so their two renames are not transactionally atomic. The report is the final completion marker:

1. A pair is valid only when both files exist and the completed report's run ID, filename, SHA-256, size, retained-row count, aggregate retained count, and approved CSV schema all validate against the CSV.
2. Before overwrite moves anything, both existing final artifacts must validate as a matching completed pair. Missing, malformed, incomplete, mismatched, or one-sided state is preserved and causes a recovery-required refusal. A report naming a different CSV is a foreign completion marker and is never moved, deleted, or overwritten automatically.
3. For overwrite, the validated previous report completion marker is moved to a current-run backup before its CSV is moved. This prevents a replacement CSV from appearing valid under an old report. Backups use run-specific names.
4. The new CSV is published first and its report is published last.
5. The published pair is streamed and validated before current-run backups are removed.
6. A handled publication failure removes only new artifacts proven to belong to the current run. Recovery copies the old CSV from its backup first and the old report last, calls the production completed-pair validator, and compares the restored metadata with the previously recorded identity. Restoration is reported successful only after that validation passes.
7. If restoration or restored-pair validation fails, remaining backups are preserved and the run raises an aggregate-only recovery-required error.
8. Backup cleanup occurs only after the new pair validates. A cleanup failure does not roll back or delete that valid new pair; remaining recovery evidence is preserved, locks are released by their owning run, and the next run refuses until the evidence is explicitly resolved.
9. Existing backups or either publication lock from an interrupted run cause a safe recovery-required failure. The cleaner never removes backups belonging to another run and releases a lock only when its stored run ID matches.

An interrupted run can leave ignored temporary files, locks, or recoverable backups, but it cannot leave a valid new pair under an old completion marker. An incomplete CSV without a matching completed report is invalid and must not be consumed. Hard interruption is not transactionally recoverable across the two destinations; retained locks or backups deliberately force owner-reviewed recovery instead of automatic deletion or overwrite.

The tracked JSON report may include completion metadata, configuration, schema, aggregate counts, mutually exclusive rejection counts, retained `Sub-product`/`Sub-issue` null counts, redaction counts, Product and Issue distributions, timing, and input file integrity metadata. It never contains Complaint IDs, narratives, row-level values, identifiers, rejected contents, or personal absolute paths.

## Completed Day 5 evidence

The corrected full run completed with run ID `e1996a2c34d0457fa08b83864b4f1a9d`, processed 17,034,951 input rows in 171 chunks, retained 3,822,576 rows, rejected 13,212,375 rows, and passed production completed-pair validation. Its corrected CSV SHA-256 is `41d2337fa2f2f4840eeb3475229a8347b67c3e4a14949846363e14ea13eee023`, and its corrected report SHA-256 is `e923cc07cc72674990a2d40d456ad8814efb985a3fa22c7478e39d35fd88c88e`.

The earlier diagnostic pair (`data/interim/cfpb/complaints_cleaned.csv` with `data/cfpb_cleaning_full_report.json`) and smoke pair (`data/interim/cfpb/complaints_cleaned_smoke.csv` with `data/cfpb_cleaning_report.json`) remain immutable historical validation evidence. Their cleaned CSVs remain ignored and untracked; their aggregate reports contain no complaint-level values.

## Known limitations

- The strict date format is tied to this validated CFPB CSV snapshot.
- CSV is slower and larger than Parquet but avoids adding a Day 5 dependency.
- Regex PII reduction has false-positive and false-negative risk.
- Unicode NFKC can intentionally fold compatibility characters.
- A bounded smoke report describes only the processed bound, not the complete dataset.
- Day 6 remains deferred until separately authorized after the controlled Day 5 commit.
