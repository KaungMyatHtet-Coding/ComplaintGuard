# CFPB Dataset Profile

## Snapshot identity

This Day 3 profile describes the official CFPB Consumer Complaint Database archive downloaded on 20 July 2026. The raw archive and extracted CSV are local-only under `data/raw/cfpb/`; Git ignores that directory. The archive is retained as the immutable compressed snapshot, and the extracted CSV is a working copy.

| Property | Observed value |
|---|---:|
| Archive | `data/raw/cfpb/complaints.csv.zip` |
| Archive size | 1,420,663,360 bytes |
| SHA-256 | `2bdb13b1e412c6b659a94f74874d03ef6f610543b0d8e6538c7e30d1dd3d8eea` |
| ZIP validation | `zipfile.ZipFile.testzip()` returned `None` |
| ZIP member | `complaints.csv` |
| Member CRC32 | `8b13cd44` |
| Extracted size | 9,097,134,981 bytes |
| Rows | 17,034,951 |
| Columns | 16 |
| Date received range | 2011-12-01 to 2026-07-20 |
| Complaint ID range | 1 to 24,372,463 |

The official download endpoint is `https://files.consumerfinance.gov/ccdb/complaints.csv.zip`. This is a changing archive, so reproducing this exact snapshot requires matching the SHA-256 above rather than downloading the endpoint later.

## Profiling method

`scripts/profile_cfpb.py` reads the extracted CSV in 100,000-row chunks with Pandas `StringDtype`. It processed 171 chunks using Python 3.12.0 and pandas 2.2.3. Treating source fields as strings preserves ZIP codes and identifiers during profiling. Dates and complaint IDs are parsed only for aggregate ranges.

The generated metadata is `data/cfpb_snapshot_profile.json`. It contains schema, missing-value counts, date and ID bounds, and aggregate counts for safe non-narrative categories. It contains no complaint-level rows and no narrative values.

Run from the repository root:

```powershell
python scripts/profile_cfpb.py
```

## Missing-value profile

| Column | Missing | Missing % |
|---|---:|---:|
| Date received | 0 | 0.0000 |
| Product | 188 | 0.0011 |
| Sub-product | 235,505 | 1.3825 |
| Issue | 248 | 0.0015 |
| Sub-issue | 929,418 | 5.4559 |
| Consumer complaint narrative | 13,211,538 | 77.5555 |
| Company public response | 8,010,319 | 47.0228 |
| Company | 0 | 0.0000 |
| State | 62,823 | 0.3688 |
| ZIP code | 2,289 | 0.0134 |
| Tags | 16,244,349 | 95.3589 |
| Submitted via | 0 | 0.0000 |
| Date sent to company | 102,934 | 0.6043 |
| Company response to consumer | 465,209 | 2.7309 |
| Timely response? | 0 | 0.0000 |
| Complaint ID | 2,135 | 0.0125 |

There are 3,823,413 rows with a non-null consumer narrative. This is an availability count only; Day 5 will decide how missing narratives and other invalid rows are handled. No duplicate analysis or cleaning decision is made on Day 3.

## Safe categorical summary

- Product has 23 observed non-null categories. The largest is `Credit reporting or other personal consumer reports` with 11,506,476 rows.
- Issue has 180 observed non-null categories. The largest is `Incorrect information on your report` with 7,591,442 rows.
- Submitted via has 6 categories; Web accounts for 16,399,692 rows.
- Company response to consumer has 8 observed non-null categories.
- Timely response? contains Yes (16,930,607) and No (104,344).

The complete top-20 aggregate counts are in the JSON profile. These are snapshot descriptions, not cleaned distributions or model results.

## Intended project columns

The minimum later classification dataset is expected to use:

- `Consumer complaint narrative` as model input text.
- `Product` and `Issue` as inputs to the deterministic department-label mapping.
- `Complaint ID` as a provenance and deduplication identifier, not a model feature.

`Sub-product` and `Sub-issue` are retained as optional mapping and error-analysis context. `Date received`, `Submitted via`, `Company response to consumer`, and `Timely response?` are retained for later aggregate EDA. Company, location, tag, public-response, and sent-date fields are not planned model features. No column has been removed from the raw snapshot.

## Initial mapping discussion

The plan requires a deterministic Product/Issue-to-department mapping with stable labels. Day 3 establishes only the mapping inputs and review principles:

- Use `Product` first and `Issue` where a product spans multiple support functions.
- Preserve the six stable IDs defined in `AGENTS.md`.
- Route ambiguous or unmapped combinations to `general_support`.
- Review class coverage and imbalance before freezing the mapping on its scheduled day.
- Do not infer training labels from narrative text, which would leak model input into the target.

No mapping table, cleaned data, sample, feature, or model artifact was created on Day 3.

## Limitations and privacy

The public database is updated over time, source categories change, and complaint narratives are consumer-provided. Missingness is substantial for narratives and tags. Counts describe this snapshot only and do not establish representativeness, truth of allegations, or model suitability. Raw narratives and complaint-level records must remain local and must not be pasted into documentation, logs, commits, demonstrations, or issue trackers.
